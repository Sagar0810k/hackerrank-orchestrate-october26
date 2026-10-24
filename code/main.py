"""Ghost Data Still Exists - deletion-audit agent.

Usage (from the repository root):

    python code/main.py                      # audit dataset/deletion_requests.csv -> output.csv
    python code/main.py --input dataset/sample_deletion_requests.csv --output sample_pred.csv

Pipeline per request:
    intent -> identity -> evidence linking -> state at audit_at -> policy -> plan -> order
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit.intent import detect_intent  # noqa: E402
from audit.linker import build_contexts  # noqa: E402
from audit.loader import DATASET, REPO_ROOT, read_csv  # noqa: E402
from audit.planner import has_problems, plan  # noqa: E402
from audit.validate import validate_output  # noqa: E402

HEADER = ["case_id", "deletion_status", "steps_json"]


def _case_sort_key(case_id: str):
    head, _, num = case_id.rpartition("_")
    return (head, int(num)) if num.isdigit() else (case_id, 0)


def all_known_requests() -> List[Dict[str, str]]:
    """Every participant-visible request.  Concurrent requests are resolved
    together, so the sample requests are included as context."""
    rows = []
    for name in ("deletion_requests.csv", "sample_deletion_requests.csv"):
        path = DATASET / name
        if path.exists():
            rows.extend(read_csv(path))
    return rows


def run_pipeline(requests: List[Dict[str, str]], debug: bool = False) -> Dict[str, Tuple[str, List[Dict]]]:
    context_rows = {r["case_id"]: r for r in all_known_requests()}
    for r in requests:
        context_rows[r["case_id"]] = r
    intents = {cid: detect_intent(r["request_text"]) for cid, r in context_rows.items()}
    non_deletion = {cid for cid, i in intents.items() if not i["deletion_requested"]}
    ctxs = build_contexts(context_rows.values(), classify=has_problems, non_deletion=non_deletion)
    results: Dict[str, Tuple[str, List[Dict]]] = {}
    for r in requests:
        intent = intents[r["case_id"]]
        status, steps, decisions = plan(ctxs[r["case_id"]], bool(intent["deletion_requested"]))
        results[r["case_id"]] = (status, steps)
        if debug:
            ctx = ctxs[r["case_id"]]
            print(f"{r['case_id']}: {status} user={ctx.subject.user_id if ctx.subject else None} "
                  f"strong={sorted(ctx.strong)} weak={sorted(ctx.weak)} intent={intent['method']}")
    return results


def write_output(results: Dict[str, Tuple[str, List[Dict]]], path: Path) -> None:
    # The contract sorts rows by case_id; numeric order keeps case_99 before case_100.
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for cid in sorted(results, key=_case_sort_key):
            status, steps = results[cid]
            w.writerow([cid, status, json.dumps(steps, separators=(",", ":"), ensure_ascii=False)])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default=str(DATASET / "deletion_requests.csv"))
    ap.add_argument("--output", default=str(REPO_ROOT / "output.csv"))
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args(argv)

    requests = read_csv(Path(args.input))
    results = run_pipeline(requests, debug=args.debug)
    out = Path(args.output)
    write_output(results, out)
    ok, msgs = validate_output(out, [r["case_id"] for r in requests])
    counts: Dict[str, int] = {}
    for status, _ in results.values():
        counts[status] = counts.get(status, 0) + 1
    print(f"wrote {len(results)} rows to {out}  {counts}")
    for m in msgs[:20]:
        print("validate:", m)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
