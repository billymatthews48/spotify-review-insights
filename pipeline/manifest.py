"""run_manifest.json: one file tying the source checksum, code version, configuration, prompts, model IDs,
settings, run IDs and output checksums together. No model calls."""

import hashlib
import json
import subprocess
from pathlib import Path

from . import common, group, memo, runtime, verify
from .enrich import open_state


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(state, cache, out_path, output_globs):
    cfg = runtime.load_config()
    root = common.ROOT
    conn = open_state(state, cache)
    meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    runs = [{"run_id": r[0], "stage": r[1], "phase": json.loads(r[2]).get("phase"), "started_at_unix": r[3]}
            for r in conn.execute("SELECT run_id, stage, detail, at FROM run_log WHERE event='start' ORDER BY seq")]
    conn.close()
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout.strip())
    except OSError:
        head, dirty = None, None
    lc = runtime.label_config(cfg)
    try:  # only files that are actually published in the repository
        tracked = set(subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True).stdout.split("\0"))
    except OSError:
        tracked = None
    outputs = {}
    for pattern in output_globs:
        for f in sorted(root.glob(pattern)):
            rel = f.relative_to(root).as_posix()
            if tracked is not None and rel not in tracked:
                continue
            if f.is_file() and f.resolve() != Path(out_path).resolve():  # never hash the manifest itself
                outputs[f.relative_to(root).as_posix()] = {"sha256": _sha(f), "bytes": f.stat().st_size}
    manifest = {
        "source": {"file": Path(meta["input_path"]).name, "sha256": meta["input_sha256"], "bytes": int(meta["input_bytes"]),
                   "parsed_rows_sha256": common.read_json(common.OUT_DIR / "ingestion.json")["parsed_rows_sha256"],
                   "scope_size": meta["scope_size"]},
        "code_version": {"git_head_when_manifest_written": head, "working_tree_dirty": dirty,
                         "note": "The pipeline code was first committed after the run; fixes made during the run "
                                 "(cache-fill query, interrupt handler, grouping query, HTTP 499 retry) are listed in "
                                 "the README run log."},
        "config": {"file": "config/run_config.json", "sha256": _sha(root / "config/run_config.json"),
                   "snapshot": cfg},
        "rates": {"file": "config/rates.csv", "sha256": _sha(root / "config/rates.csv")},
        "prompts": {f.name: _sha(f) for f in sorted((root / "prompts").glob("*")) if f.is_file()},
        "models": {"enrich_labels": cfg["enrich"]["model"],
                   "enrich_quotes": f"{cfg['quote']['model']} (reasoning {cfg['quote']['reasoning_effort']})",
                   "verify": f"{cfg['verify']['model']} (reasoning {cfg['verify']['reasoning_effort']})",
                   "group_discover": f"{cfg['group']['model_discover']} (reasoning {cfg['group']['reasoning_effort']})",
                   "group_assign": f"{cfg['group']['model_discover']} (reasoning none)",
                   "memo": f"{cfg['memo']['model']} (reasoning {cfg['memo']['reasoning_effort']})"},
        "configs": {"label_config": lc, "verify_config": verify.verify_config(cfg),
                    "group_config": group.group_config(cfg, lc),
                    "memo_config": f"{cfg['memo']['model']}/{cfg['memo']['reasoning_effort']}+{cfg['memo']['prompt_version']}"},
        "runs": runs,
        "outputs": outputs,
    }
    common.write_json(out_path, manifest)
    return manifest
