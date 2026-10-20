"""Shared paths, hashing, storage and file helpers. No model calls."""

import hashlib
import importlib.util
import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
OUT_DIR = ROOT / "out"
DB_PATH = STATE_DIR / "pipeline.sqlite"
MANIFEST_PATH = ROOT / "tools" / "manifest.json"
CHECKER_PATH = ROOT / "tools" / "check_submission.py"

FIELDS = ("review_id", "review_text", "review_rating", "review_likes", "app_version", "review_timestamp")
SAMPLE_SEED = "berkeley-fall-2026-assignment-5-v1"  # same seed the course used for golden/dev samples


def _load_checker():
    # Reuse the course's own row_sha/profile so hashes match the grader byte-for-byte.
    spec = importlib.util.spec_from_file_location("check_submission", CHECKER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()
row_sha = checker.row_sha
csv_rows = checker.csv_rows
file_sha = checker.sha


def text_sha(text):
    """Exact-text cache key component: no trimming or normalization."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sample_rank(review_id):
    """Course sampling order: lower SHA-256(seed:id) comes first (hex compares like the integer)."""
    return hashlib.sha256((SAMPLE_SEED + ":" + review_id).encode()).hexdigest()


def connect(path=DB_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: worker threads may log calls, always under the caller's write lock.
    conn = sqlite3.connect(path, timeout=60, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Rollback journal (not WAL) so one transaction spanning the state DB and the attached result
    # cache commits atomically: a batch's calls, labels and statuses land together or not at all.
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def write_json(path, value):
    """Atomic JSON write: temp file then rename, so a crash never leaves half a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(tmp, path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
