"""Thin provider adapters. Each function makes exactly ONE attempt and returns (payload, attempt_record)
or raises AttemptFailed carrying the attempt record. Retry policy lives in run_with_retries so that
every attempt, failed or not, is logged with its usage and timing.
"""

import json
import os
import random
import time

import httpx
from dotenv import load_dotenv

from . import common
from .runtime import call_cost, new_request_id

load_dotenv(common.ROOT / ".env")

JEV_URL = "https://api.typesafe.ai/v1/systemone"
# 499: seen from Jev as {"error_type": "internal_error"} during the 10k checkpoint; safe to retry.
TRANSIENT_STATUS = {408, 409, 429, 499, 500, 502, 503, 504}


class AttemptFailed(Exception):
    def __init__(self, record, transient, fatal=False):
        super().__init__(record.get("error"))
        self.record, self.transient, self.fatal = record, transient, fatal


class FatalProviderError(Exception):
    """Auth, permission or exhausted credit: stop the whole run instead of quarantining reviews."""

    def __init__(self, message, records):
        super().__init__(message)
        self.records = records


def _record(role, step, provider, model, effort, review_ids, started, **kw):
    return {"request_id": kw.pop("request_id", None) or new_request_id(provider), "role": role, "step": step,
            "provider": provider, "model": model, "effort": effort, "review_ids": review_ids,
            "started_at": started, "seconds": round(time.time() - started, 3), **kw}


class Jev:
    def __init__(self, timeout):
        key = os.environ.get("TYPESAFE_API_KEY", "").strip()
        if not key:
            raise SystemExit("TYPESAFE_API_KEY is empty: add it to .env (see .env.example).")
        self.client = httpx.Client(timeout=timeout, headers={"Authorization": f"Bearer {key}"})

    def ask(self, model, state, questions, *, role, step, review_ids, rates, label_config, attempt):
        started = time.time()
        base = dict(role=role, step=step, provider="typesafe", model=model, effort=None, review_ids=review_ids,
                    started=started, label_config=label_config, attempt=attempt)
        fault = _injected_fault(review_ids, attempt)  # system tests only; never set in normal runs
        if fault == "transient":
            raise AttemptFailed(_record(**base, outcome="failed", error="INJECTED TEST FAULT: simulated HTTP 503",
                                        usage_status="none_reported", cost_usd=0.0), transient=True)
        try:
            r = self.client.post(JEV_URL, json={"state": state, "model": model, "questions": questions})
        except (httpx.TimeoutException, httpx.TransportError) as e:
            rec = _record(**base, outcome="failed", error=f"{type(e).__name__}: {e}"[:300],
                          usage_status="unknown_possible_charge", cost_usd=0.0)
            raise AttemptFailed(rec, transient=True)
        req_id = next((v for k, v in r.headers.items() if "request-id" in k.lower()), None)
        if r.status_code != 200:
            rec = _record(**base, outcome="failed", error=f"HTTP {r.status_code}: {r.text[:200]}",
                          usage_status="none_reported", cost_usd=0.0, provider_request_id=req_id)
            raise AttemptFailed(rec, transient=r.status_code in TRANSIENT_STATUS, fatal=r.status_code in (401, 402, 403))
        body = r.json()
        usage = {"input_tokens": body.get("usage", {}).get("input_tokens"),
                 "output_tokens": body.get("usage", {}).get("output_tokens"), "cached_input_tokens": 0}
        rec = _record(**base, outcome="succeeded", error=None, input_tokens=usage["input_tokens"],
                      cached_input_tokens=0, output_tokens=usage["output_tokens"], reasoning_tokens=None,
                      usage_status="reported" if usage["input_tokens"] is not None else "missing",
                      cost_usd=call_cost(rates, model, usage), provider_request_id=req_id)
        rec["model"] = body.get("model", model)  # exact served version, e.g. jev-1.13.0
        if fault == "invalid":  # a real, billed response whose content we deliberately corrupt for the test
            body = {**body, "answers": {**body.get("answers", {}), "topic": {"choice": "INJECTED_INVALID_TOPIC"}}}
        return body, rec


def _injected_fault(review_ids, attempt):
    """PIPELINE_FAULT_INJECT='transient:<id>,invalid:<id>' fails the FIRST attempt for those review IDs.
    Used only by evals/system_tests.py to demonstrate bounded retry and invalid-output handling."""
    spec = os.environ.get("PIPELINE_FAULT_INJECT", "")
    if not spec or attempt != 1:
        return None
    for part in spec.split(","):
        kind, _, rid = part.partition(":")
        if rid in review_ids:
            return kind
    return None


class Luna:
    def __init__(self, timeout):
        from openai import OpenAI
        if not os.environ.get("OPENAI_API_KEY", "").strip():
            raise SystemExit("OPENAI_API_KEY is empty: add it to .env (see .env.example).")
        self.client = OpenAI(timeout=timeout, max_retries=0)  # retries are ours, so each attempt is logged

    def structured(self, model, effort, system, user, schema, max_output_tokens, *, role, step, review_ids, rates,
                   label_config, attempt):
        import openai
        started = time.time()
        base = dict(role=role, step=step, provider="openai", model=model, effort=effort, review_ids=review_ids,
                    started=started, label_config=label_config, attempt=attempt)
        try:
            r = self.client.responses.create(
                model=model, reasoning={"effort": effort}, max_output_tokens=max_output_tokens,
                input=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                text={"format": {"type": "json_schema", "name": schema["name"], "schema": schema["schema"], "strict": True}})
        except (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError, openai.InternalServerError) as e:
            timeout = isinstance(e, (openai.APITimeoutError, openai.APIConnectionError))
            rec = _record(**base, outcome="failed", error=f"{type(e).__name__}: {e}"[:300],
                          usage_status="unknown_possible_charge" if timeout else "none_reported", cost_usd=0.0)
            no_credit = isinstance(e, openai.RateLimitError) and "insufficient_quota" in str(e)
            raise AttemptFailed(rec, transient=not no_credit, fatal=no_credit)
        except openai.APIStatusError as e:
            rec = _record(**base, outcome="failed", error=f"HTTP {e.status_code}: {str(e)[:200]}",
                          usage_status="none_reported", cost_usd=0.0)
            raise AttemptFailed(rec, transient=False, fatal=e.status_code in (401, 402, 403))
        u = r.usage
        usage = {"input_tokens": u.input_tokens if u else None,
                 "cached_input_tokens": (u.input_tokens_details.cached_tokens if u and u.input_tokens_details else 0) or 0,
                 "output_tokens": u.output_tokens if u else None,
                 "reasoning_tokens": (u.output_tokens_details.reasoning_tokens if u and u.output_tokens_details else 0) or 0}
        common_fields = dict(input_tokens=usage["input_tokens"], cached_input_tokens=usage["cached_input_tokens"],
                             output_tokens=usage["output_tokens"], reasoning_tokens=usage["reasoning_tokens"],
                             usage_status="reported" if u else "missing", cost_usd=call_cost(rates, model, usage),
                             provider_request_id=r.id)
        if r.status != "completed":
            reason = getattr(r.incomplete_details, "reason", None) if r.incomplete_details else None
            rec = _record(**base, outcome="failed", error=f"response {r.status}: {reason}", **common_fields)
            raise AttemptFailed(rec, transient=False)  # billed, but output unusable: counts against the batch retry
        try:
            payload = json.loads(r.output_text)
        except (json.JSONDecodeError, TypeError) as e:
            rec = _record(**base, outcome="failed", error=f"invalid JSON: {e}", **common_fields)
            raise AttemptFailed(rec, transient=False)
        return payload, _record(**base, outcome="succeeded", error=None, **common_fields)


def run_with_retries(do_attempt, limits):
    """Run do_attempt(attempt_no) with bounded backoff + jitter for transient failures.
    Returns (payload or None, [attempt records], final_error). Non-transient failures stop immediately
    so the caller can apply its one invalid-output retry."""
    records = []
    tries = limits.get("transient_retries", 4)
    for n in range(tries + 1):
        try:
            payload, rec = do_attempt(len(records) + 1)
            records.append(rec)
            return payload, records, None
        except AttemptFailed as e:
            records.append(e.record)
            if e.fatal:
                raise FatalProviderError(e.record["error"], records)
            if not e.transient or n == tries:
                return None, records, e.record["error"]
            delay = min(limits["backoff_max_seconds"], limits["backoff_base_seconds"] * 2 ** n)
            time.sleep(delay * (0.5 + random.random()))
    return None, records, "exhausted"
