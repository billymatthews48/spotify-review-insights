"""Shared stage context so every role logs to the same call table and spend ledger."""

import threading
from pathlib import Path

from . import enrich, runtime


class Context:
    def __init__(self, state_path, cache_path=None, phase="initial", run_prefix="run", cfg=None):
        self.state_path = Path(state_path)
        self.cache_path = Path(cache_path) if cache_path else self.state_path.with_name(self.state_path.stem + "_cache.sqlite")
        self.cfg = cfg or runtime.load_config()
        self.rates = runtime.load_rates()
        self.conn = enrich.open_state(self.state_path, self.cache_path)
        self.run_id = runtime.new_run_id(run_prefix)
        self.recorder = runtime.Recorder(self.conn, self.run_id, phase)
        self.ledger = runtime.Ledger(self.cfg["limits"]["spend_cap_usd"], self.recorder.spent())
        self.label_config = runtime.label_config(self.cfg)  # primary (Jev) config: anchors verify sample + issue catalog
        # Every label config with completed records (Jev 100k scope, plus gpt-6-luna phase 2 when present).
        self.label_configs = [r[0] for r in self.conn.execute(
            "SELECT DISTINCT label_config FROM records WHERE status='completed' AND label_config IS NOT NULL")] or [self.label_config]
        self.db_lock = threading.Lock()  # one writer at a time when stages fan out calls to threads
        self._luna = None

    @property
    def luna(self):
        if self._luna is None:
            from .providers import Luna
            self._luna = Luna(self.cfg["limits"]["request_timeout_seconds"])
        return self._luna

    def luna_call(self, role, step, model, effort, system, user, schema, max_output_tokens, review_ids, label_config=None):
        """One bounded structured call with retries; every attempt is logged in one transaction.
        Returns (payload or None, error)."""
        from .providers import FatalProviderError, run_with_retries
        reserve = 12000 * self.rates[(model, "input_uncached")] + max_output_tokens * self.rates[(model, "output")]
        reservation = self.ledger.reserve(reserve)
        records, spent = [], 0.0
        try:
            def attempt(n):
                return self.luna.structured(model, effort, system, user, schema, max_output_tokens, role=role, step=step,
                                            review_ids=review_ids, rates=self.rates, label_config=label_config, attempt=n)
            try:
                payload, records, err = run_with_retries(attempt, self.cfg["limits"])
            except FatalProviderError as e:
                records = e.records
                raise
            spent = sum(r["cost_usd"] for r in records)
            return payload, err
        finally:
            self.ledger.settle(reservation, spent)
            with self.db_lock, self.conn:
                for r in records:
                    self.recorder.call(r)

    def close(self):
        self.conn.close()
