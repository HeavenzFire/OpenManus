#!/usr/bin/env python3
"""One command: deterministic verification, nonzero exit on any failure.

  python verify.py   →  runs the invariant suite + ledger self-check,
                        prints a summary, exits 0 only if everything passes.

This is the CI-usable entry point (no UI involved). It proves nothing about
the real world — see LIMITATIONS.md for exactly what it does and does not
claim.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    print("=== SYNTHETIC DEMONSTRATION VERIFIER ===")
    print("Fixtures are synthetic. No real cases, identities, or evidence.\n")

    rc = subprocess.call(
        [sys.executable, "-m", "pytest", "tests/", "-q"], cwd=ROOT
    )
    if rc != 0:
        print("\nRESULT: FAIL — invariant suite detected breakage (see above).")
        return rc

    # Negative test: root-anchor detection demo must pass end-to-end
    # (tamper detected against a separately preserved trusted root).
    rc = subprocess.call(
        [sys.executable, str(ROOT / "demos" / "root_anchor_negative_test.py")],
        cwd=ROOT,
    )
    if rc != 0:
        print("\nRESULT: FAIL — root-anchor negative test detected breakage.")
        return rc

    # Self-check: the durable audit ledger (if present) must verify.
    from app.agent import ledger

    log = ROOT / "logs" / "agent_audit.jsonl"
    events = ledger.read_events(log)
    ok, broken = ledger.verify_chain(events)
    if ok:
        print(
            f"\nLedger self-check: {len(events)} event(s), chain VALID, "
            f"tip={ledger.chain_tip(events)[:16]}…"
        )
    else:
        print(f"\nLedger self-check: CHAIN BROKEN at event #{broken} in {log}")
        return 1

    print("RESULT: PASS (within declared scope only — see LIMITATIONS.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
