"""Orchestrator plumbing shared by every stage: config, dated rates, the spend ledger with
reservations, the per-attempt call log, the run log, and bounded retry with backoff + jitter.

Code owns accounting and arithmetic here; models never see or change these numbers.
"""

import csv
import json
import threading
import time
import uuid

from . import common
from .labels import LABELS_VERSION

CONFIG_PATH = common.ROOT / "config" / "run_config.json"
RATES_PATH = common.ROOT / "config" / "rates.csv"

CALLS_SCHEMA = """
CREATE TABLE IF NOT EXISTS calls(
    request_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    role TEXT NOT NULL,
    step TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    effort TEXT,
    label_config TEXT,
    review_ids TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    outcome TEXT NOT NULL CHECK(outcome IN ('succeeded', 'failed')),
    error TEXT,
    input_tokens INTEGER,
    cached_input_tokens INTEGER,
    output_tokens INTEGER,
    reasoning_tokens INTEGER,
    usage_status TEXT NOT NULL,
    cost_usd REAL NOT NULL,
    started_at REAL NOT NULL,
    seconds REAL NOT NULL,
    provider_request_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_calls_run ON calls(run_id, role);
CREATE TABLE IF NOT EXISTS run_log(
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    at REAL NOT NULL,
    stage TEXT NOT NULL,
    event TEXT NOT NULL,
    detail TEXT NOT NULL
);
"""


def load_config(path=CONFIG_PATH):
    """Load run settings and enforce the model allowlist: every model a stage may call must be listed."""
    cfg = common.read_json(path)
    allowed = set(cfg.get("model_allowlist", []))
    used = {cfg["enrich"]["model"], cfg["quote"]["model"], cfg["verify"]["model"], cfg["group"]["model_discover"],
            cfg["memo"]["model"]}
    if not used <= allowed:
        raise SystemExit(f"run_config.json uses models outside model_allowlist: {sorted(used - allowed)}")
    return cfg


def label_config(cfg):
    """Every setting that changes enrichment output; exact-text cache reuse requires an identical string."""
    e, q = cfg["enrich"], cfg["quote"]
    return f"{e['model']}+{q['model']}/{q['reasoning_effort']}+{cfg['prompt_version']}+{cfg['schema_version']}+{LABELS_VERSION}"


def load_rates(path=RATES_PATH):
    rates = {}
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            rates[(row["model"], row["billing_item"])] = float(row["price_per_unit_usd"])
    return rates


def call_cost(rates, model, usage):
    """Mutually exclusive billing items x price per unit. Cached input is subtracted from input before
    the uncached rate; reasoning tokens are already inside output tokens and are not added again."""
    if usage is None:
        return 0.0
    inp = usage.get("input_tokens") or 0
    cached = usage.get("cached_input_tokens") or 0
    out = usage.get("output_tokens") or 0
    if (model, "input_uncached") in rates:
        return (inp - cached) * rates[(model, "input_uncached")] + cached * rates[(model, "input_cached")] \
            + out * rates[(model, "output")]
    return inp * rates[(model, "input")] + out * rates.get((model, "output"), 0.0)


class BudgetExceeded(Exception):
    pass


class Ledger:
    """One spend ledger shared by all workers. Reserve an estimated worst case before dispatch;
    stop admitting work when spent + reserved + the next reservation would pass the cap."""

    def __init__(self, cap_usd, spent_usd=0.0):
        self.cap = cap_usd
        self.spent = spent_usd
        self.reserved = 0.0
        self.lock = threading.Lock()

    def reserve(self, amount):
        with self.lock:
            if self.spent + self.reserved + amount > self.cap:
                raise BudgetExceeded(f"spent {self.spent:.4f} + reserved {self.reserved:.4f} + next {amount:.4f} > cap {self.cap:.2f}")
            self.reserved += amount
        return amount

    def settle(self, reservation, actual):
        with self.lock:
            self.reserved -= reservation
            self.spent += actual


class Recorder:
    """Writes call attempts and run events to the state DB (single writer: the main thread)."""

    def __init__(self, conn, run_id, phase):
        self.conn, self.run_id, self.phase = conn, run_id, phase
        conn.executescript(CALLS_SCHEMA)

    def call(self, rec):
        rec = {**rec, "run_id": self.run_id, "phase": rec.get("phase", self.phase)}
        cols = ["request_id", "run_id", "phase", "role", "step", "provider", "model", "effort", "label_config", "review_ids",
                "attempt", "outcome", "error", "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens",
                "usage_status", "cost_usd", "started_at", "seconds", "provider_request_id"]
        rec["review_ids"] = json.dumps(rec["review_ids"])
        self.conn.execute(f"INSERT INTO calls({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                          [rec.get(c) for c in cols])

    def event(self, stage, event, **detail):
        self.conn.execute("INSERT INTO run_log(run_id, at, stage, event, detail) VALUES (?,?,?,?,?)",
                          (self.run_id, time.time(), stage, event, json.dumps(detail, ensure_ascii=False)))
        self.conn.commit()

    def spent(self):
        row = self.conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM calls").fetchone()
        return float(row[0])


def new_run_id(prefix):
    return f"{prefix}-{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"


def new_request_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex}"
