# LIMITATIONS — read before trusting anything here

Status: **local prototype, synthetic data only.** No deployed service exists.

## What the code actually demonstrates (given synthetic fixtures)

- Illegal/invalid agent state transitions are rejected; state is left untouched.
- Every accepted transition appends one event to a SHA-256 hash-chained
  append-only ledger (`app/agent/ledger.py`, `logs/agent_audit.jsonl`).
- Post-recording edits, deletions, reordering, and naive re-hashing of the
  ledger are detected by `verify_chain()` — proven by negative tests that
  mutate the file verification actually reads.
- Appending to a chain that already fails verification is refused
  (`E-LEDGER-BROKEN`) rather than silently extending suspect history.
- If the audit sink fails, the state transition does NOT happen
  (fail-safe ordering), and nothing enters the in-memory trail.
- Max-step exhaustion is reported as UNCONFIRMED, never as success.
- Exports carry a manifest root over canonical serialization and refuse to
  imply more than byte integrity.
- Unified-field bridge (`app/agent/protocol.py`, `app/agent/publish.py`):
  local ledger/anchor evidence can be published as canonical, content-
  addressed protocol records with a closed status vocabulary (MATCHED /
  EXPECTED_VARIANCE / UNEXPLAINED_DIVERGENCE / NOT_COMPARABLE). Unknown
  statuses, empty subjects, and commit-less inputs are rejected at
  construction time; missing anchors fail closed as NOT_COMPARABLE (exit
  code 2), never as silent success.

## What it does NOT prove

| Feature | Do not claim |
|---|---|
| SHA-256 hash chain | Immutable real-world ledger, WORM storage, court-admissible proof, or blockchain-grade consensus |
| Python `hashlib` on local disk | Hardware-backed or FIPS-validated key custody |
| Reviewer IDs in fields | Real RBAC, MFA, identity assurance, or separation of duties |
| `reason`/`detail` strings | Verified human sign-off or legal consent |
| This test suite (45 tests) | Independent audit, security certification, penetration test, or production reliability |
| `manifest_root` | Proof of truth, authenticity, completeness, or source authority |
| Root anchors (`root_anchor.py`) | Protection against an attacker who can rewrite the ledger AND the anchor together — the anchor must be preserved outside the write scope (printed, notarized, published) |
| Two AI-assisted builds matching byte-for-byte | Independent audit, correctness, safety, or "comparative assurance" — both environments can share the same flawed spec; matching hashes prove only that defined inputs produced matching bytes under the recorded protocol |
| Unified-field protocol records (`protocol.py`) | Connection to, endorsement by, or membership in any real-world program. "Unified field" is a naming convention for this repo's own record format — no external system consumes these records yet, and a published record is an observation about bytes, not a fact about the world |
| `EXPECTED_VARIANCE` status | Proof that differing invocations ran the same code — it means only that the difference is confined to fields *declared* non-semantic in the protocol; adding a field to that declaration set is itself a human decision requiring review |
| `verify.py` PASS | Any claim about systems not present in this repository |

## Known structural limits

1. An attacker who controls the file can rewrite the *entire* chain
   consistently. Detection requires an externally anchored tip:
   `app/agent/root_anchor.py` now implements the software half (capture the
   chain tip into a separate anchor directory; `verify_against_anchor()`
   reports MATCHED / UNEXPLAINED_DIVERGENCE / NOT_COMPARABLE with reason
   codes). The remaining trust requirement is procedural, not technical:
   the anchor file must live outside the attacker's write scope. See
   `demos/root_anchor_negative_test.py` for the executed nine-step
   demonstration, including the full local re-hash attack being caught
   against the preserved root (`E-ANCHOR-TIP-MISMATCH`).
2. Concurrent writers are unsafe: two processes may fork the chain head.
   Single-writer assumption only.
3. Cross-agent global event ordering is not guaranteed; each agent chains
   its own transitions into one shared file without per-stream sequencing.
4. "Fail safely" is implemented for the control plane (state machine +
   ledger). There is no runtime service to fail yet.
5. Accountability cannot be enforced by code: it lives in the humans whose
   identities appear in authorization fields. All fixture reviewers are
   obviously synthetic because no real decision has been made.
