#!/usr/bin/env python3
"""Negative test: detect specified alterations against a separately preserved root.

Runs the nine-step protocol from the dual-build review, prints each step's
evidence, and exits nonzero if any expectation fails. This demonstrates the
ONLY integrity property we claim:

    post-capture modification is detectable against a separately preserved
    trusted root hash, within the stated threat model — byte-integrity only,
    no attestation to truth of contents.

Usage:  python demos/root_anchor_negative_test.py             (temp dir)
        python demos/root_anchor_negative_test.py --keep DIR  (inspect files)
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.ledger import (  # noqa: E402
    append_event,
    compute_event_hash,
    read_events,
    verify_chain,
)
from app.agent.root_anchor import (  # noqa: E402
    AnchorError,
    create_root_anchor,
    verify_against_anchor,
)

failures: list[str] = []


def check(step: str, cond: bool, evidence: str) -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {step}\n       {evidence}")
    if not cond:
        failures.append(step)


def main() -> int:
    keep = "--keep" in sys.argv
    if keep:
        workdir = Path(sys.argv[-1])
        workdir.mkdir(parents=True, exist_ok=True)
    else:
        workdir = Path(tempfile.mkdtemp(prefix="anchor-demo-"))
    ledger = workdir / "ledger.jsonl"
    anchor_dir = workdir / "preserved-roots"  # conceptually: printed / notarized
    copy_ledger = workdir / "ledger-copy.jsonl"

    print(f"workspace: {workdir}\n")

    # Step 1: create a synthetic event ledger.
    for i in range(5):
        append_event(
            ledger,
            {"agent": "demo", "to_state": "RUNNING",
             "reason": f"synthetic step {i}", "detail": "SYNTHETIC DATA"},
        )
    events = read_events(ledger)
    ok, idx = verify_chain(events)
    check(
        "1. synthetic ledger created; chain internally valid",
        ok and len(events) == 5,
        f"5 events, verify_chain -> ({ok}, {idx})",
    )

    # Step 2: export and preserve the canonical manifest root (separate location).
    anchor = create_root_anchor(ledger, anchor_dir)
    anchor_file = Path(anchor["anchor_file"])
    check(
        "2. trusted root anchored separately",
        anchor_file.exists(),
        f"root={anchor['tip_hash'][:16]}… count={anchor['event_count']}",
    )

    baseline = verify_against_anchor(ledger, anchor_file)
    check(
        "2b. untouched ledger verifies MATCHED against the preserved root",
        baseline["status"] == "MATCHED",
        f"status={baseline['status']}",
    )

    # Step 3: alter one field in a COPIED ledger (simulated post-capture tamper).
    shutil.copyfile(ledger, copy_ledger)
    lines = copy_ledger.read_text(encoding="utf-8").splitlines()
    tampered_index = 2
    ev = json.loads(lines[tampered_index])
    ev["reason"] = "silently rewritten reason"
    lines[tampered_index] = json.dumps(ev, sort_keys=True, separators=(",", ":"))
    copy_ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
    check("3. one field altered in a copied ledger", True,
          f"event index {tampered_index} edited on disk")

    # Steps 4/5: run chain verification; confirm it detects the changed index.
    det_ok, det_idx = verify_chain(read_events(copy_ledger))
    check(
        "5. local chain verification detects the changed event index",
        (not det_ok) and det_idx == tampered_index,
        f"verify_chain -> valid={det_ok}, first_broken_index={det_idx} "
        f"(expected {tampered_index})",
    )

    # Steps 6/7: attacker-style full re-hash (cascaded), then compare the
    # recomputed root with the SEPARATELY PRESERVED original root.
    events_c = read_events(copy_ledger)
    prev_hash = "0" * 64
    fixed_lines = []
    for e in events_c:
        e.pop("prev_hash", None)
        e.pop("event_hash", None)
        h = compute_event_hash({**e, "prev_hash": prev_hash}, prev_hash)
        e["prev_hash"] = prev_hash
        e["event_hash"] = h
        fixed_lines.append(json.dumps(e, sort_keys=True, separators=(",", ":")))
        prev_hash = h
    copy_ledger.write_text("\n".join(fixed_lines) + "\n", encoding="utf-8")
    inner_ok, _ = verify_chain(read_events(copy_ledger))
    check(
        "6. full local re-hash makes the chain internally consistent again",
        inner_ok,
        "verify_chain passes WITHOUT the external root — this is why the root "
        "must be preserved separately",
    )

    # Step 8: mismatch MUST be detected against the preserved root.
    result = verify_against_anchor(copy_ledger, anchor_file)
    check(
        "8. recomputed root != preserved root -> divergence detected",
        result["status"] == "UNEXPLAINED_DIVERGENCE"
        and result["reason"] == "E-ANCHOR-TIP-MISMATCH",
        f"status={result['status']} reason={result['reason']} "
        f"recomputed={str(result['recomputed_root'])[:16]}… "
        f"anchored={str(result['anchored_root'])[:16]}…",
    )

    # Fail-safe refusals (every failure has a visible reason code).
    empty = workdir / "empty.jsonl"
    empty.touch()
    try:
        create_root_anchor(empty, anchor_dir)
        check("refusal: anchoring an empty ledger raises E-ANCHOR-EMPTY-LEDGER",
              False, "no exception raised")
    except AnchorError as exc:
        check("refusal: anchoring an empty ledger raises E-ANCHOR-EMPTY-LEDGER",
              exc.code == "E-ANCHOR-EMPTY-LEDGER", str(exc))

    r_missing = verify_against_anchor(ledger, workdir / "no-such-anchor.json")
    check(
        "refusal: missing anchor -> NOT_COMPARABLE + E-ANCHOR-MISSING",
        r_missing["status"] == "NOT_COMPARABLE"
        and r_missing["reason"] == "E-ANCHOR-MISSING",
        f"status={r_missing['status']} reason={r_missing['reason']}",
    )

    # Step 9: reproducibility report written next to the artifacts.
    report = workdir / "REPRODUCIBILITY.md"
    report.write_text(
        "# Root-anchor negative test run\n\n"
        "- protocol: root-anchor-1.0 / serialization canonical-json-1.0\n"
        "- ledger: ledger.jsonl, 5 synthetic events\n"
        f"- preserved root tip: {anchor['tip_hash']}\n"
        f"- tampered copy recomputed tip: {result['recomputed_root']}\n"
        f"- detection: {result['status']} ({result['reason']})\n\n"
        "Claim demonstrated (narrow): post-capture modification is detectable\n"
        "against a separately preserved trusted root, within the stated threat\n"
        "model. Byte-integrity-only; does not attest to truth, completeness,\n"
        "authorization, admissibility, or safety of contents.\n",
        encoding="utf-8",
    )
    check("9. reproducibility report written", report.exists(), str(report))

    print(f"\n{'FAILED: ' + ', '.join(failures) if failures else 'ALL CHECKS PASSED'}")
    if keep:
        print(f"artifacts kept in {workdir}")
    else:
        shutil.rmtree(workdir, ignore_errors=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
