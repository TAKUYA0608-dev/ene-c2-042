# Test Specification — ENE-C2-042

Distributed Energy Resource (DER) Flexibility Enrollment Eligibility & Portfolio Planning Agent (Cat 2).

## Test Strategy
- Coverage target: **89%+** (achieved 93%, `--cov=src` in CI)
- Test types: Unit (pre/post + inner nodes + services) / Unit (Cat 2 graph wiring) / Integration / Proof-of-Boundary
- Locally: 61 passed + 3 skipped (server import + 2 PB-7 conditional stubs) + 1 env-diff fail
  (`test_pb_invoke_order`, passes on the real SDK in CI; the local SDK stub lacks the monkeypatched
  `base_node.emit_trace_event`). CI (real SDK): 62 passed + 3 skipped.

## Framework Compliance Tests (Mandatory)

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| TC-01 | State contract: flat TypedDict | `State(AgentState)`, NotRequired primitives + JSON strings; no credentials | ✅ PASS |
| TC-02 | Execute-level degraded rejection (no ERROR short-circuit) | `_extra_security_gate_input` is a no-op; prompt-injection / unauthorised / oversize → `execute()` returns degraded `SUCCESS + error_code` (`INJECTION_REJECTED` / `UNAUTHORIZED_INPUT` / `INPUT_TOO_LONG`), asset body discarded (`validated_input="{}"`), never `status=ERROR`. Injection is detected here (marker set — deterministic, no LLM), never deferred to S-3 only | ✅ PASS |
| TC-03 | No JWT/Credential in `src/` | `gate-credential-scan`: 0 violations | ✅ PASS |
| TC-05 | S-4: no duplicate lifecycle events | only domain events emitted per node | ✅ PASS |
| TC-06 | S-2 `_security_gate_input()` not overridden | `@final`; only `_extra_*` extended | ✅ PASS |
| TC-07 | S-3 `_security_gate_output()` not overridden | `@final`; may raise via `_extra_*` | ✅ PASS |
| TC-08 | `required_trust_level` enforced | VERIFIED_EXTERNAL on all 6 FunctionNode subclasses (`check_trust_level.py` PASS) | ✅ PASS |
| TC-11 | S-4: ≥1 domain `emit_trace_event()` per `execute()` | emitted on every path (incl. skip / safe) | ✅ PASS |

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Expected Result | Result |
|-------|----------|----------------|--------|
| PB-1 | `emit_trace_event()` fires from `shared.utils.audit_logger` | No silent failures | ✅ (real SDK on CI) |
| PB-2 | Post-invoke State is primitives only | No Pydantic/dataclass | ✅ PASS |
| PB-4 | Import isolation — no Level 0 imports | AST scan: 0 violations | ✅ PASS |
| PB-6 | Invoke order S-1 → S-4 → S-2 → execute → S-3 → S-4 | Order verified | ✅ (real SDK on CI; local-stub env-diff) |
| PB-7 | *(conditional — `hitl.enabled:false`)* interrupt-propagation stub | 2 SKIPPED (hitl disabled) | ✅ (skip guard) |
| Composition | Cat 2 `GraphNode`-in-main wraps inner `BaseGraph` (cached) | gate-composition passes | ✅ (S-0 gate) |

## Business Logic Tests

| BL-ID | Test | Input | Expected Result | Result |
|-------|------|-------|----------------|--------|
| BL-01 | Enrollment deliverable | VPP application w/ battery + solar + EV | deliverable, cited, portfolio_fit=fit, human_review_required | ✅ PASS |
| BL-02 | Eligible battery classification | battery 30kW, controllable, telemetry | eligible=true, class=storage | ✅ PASS |
| BL-03 | Undersized asset → exception | EV charger 3kW (< 6kW min) | eligible=false, constraint + exception | ✅ PASS |
| BL-04 | Not-controllable / no-telemetry | battery lacking control / telemetry | eligible=false (control_eligible=false / telemetry constraint) | ✅ PASS |
| BL-05 | Portfolio fit tiers | fit / partial (all-variable) / review (none-eligible) | correct tier per scenario | ✅ PASS |
| BL-06 | Local-constraint scenario | 600kW in one area (> 500kW cap) | constrained_areas set, fit=review | ✅ PASS |
| BL-07 | Out-of-scope safe answer | free-text / no assets | `out_of_scope`, citations=[], human_review_required=false | ✅ PASS |
| BL-08 | Empty input degrades | "   " | degraded SUCCESS + error_code, still audits | ✅ PASS |
| BL-09 | S-3 injection echo blocked (defense-in-depth; primary reject is execute-level) | output echoing an injection marker | S-3 gate raises ValueError | ✅ PASS |
| BL-10 | S-3 DRAFT disclaimer preserved | grounded output missing disclaimer | S-3 gate raises ValueError | ✅ PASS |
| BL-11 | Citation completeness is **per-decision** | mixed submission: recognised battery + unknown/unsupported asset (`source=None`) | deliverable, `citation_complete=false` (one decision un-cited), unknown asset in exceptions, human_review_required | ✅ PASS |
| BL-12 | Fully-grounded deliverable is complete | every enrollment decision carries a source citation | `citation_complete=true` | ✅ PASS |

## Graph.invoke Routing Tests` short-cut)

Real `Graph().invoke()` — asserts a degraded/rejected input **reaches `post_process`** (not a `finalize`
short-circuit) so the safe envelope / DRAFT disclaimer / terminal audit always run.

| IT-ID | Path | Assertion | Result |
|-------|------|-----------|--------|
| IT-01 | Unauthorised (`input_context.authorized=False`) via `Graph().invoke()` | `status==SUCCESS.value`; `"PostProcessNode" in node_history`; envelope `status_kind=="out_of_scope"`; DRAFT/HumanApprovalGate disclaimer; no asset body in output | ✅ PASS |
| IT-02 | Oversize (> `_MAX_INPUT`) via `Graph().invoke()` | `status==SUCCESS.value`; `"PostProcessNode" in node_history`; `out_of_scope` envelope; disclaimer present; oversize canary absent from output | ✅ PASS |
| IT-03 | Injection via `Graph().invoke()` (execute-level degraded reject) | `status==SUCCESS.value`; `"PostProcessNode" in node_history`; envelope `status_kind=="out_of_scope"`; DRAFT/HumanApprovalGate disclaimer; injection marker + rejected body (canary) absent from output | ✅ PASS |
| IT-04 | Full DER application via `Graph().invoke()` | `status==SUCCESS.value`; post_process traversed; envelope `status_kind=="deliverable"` (real inner-input contract works) | ✅ PASS |
| IT-05 | Node-chain rejection evidence (unauthorised) | unauthorised via node chain → `error_code=UNAUTHORIZED_INPUT`; `audit_logged is True`; asset body absent from `validated_input` | ✅ PASS |
| IT-06 | Node-chain rejection evidence (injection) | injection via node chain → `error_code=INJECTION_REJECTED`; `audit_logged is True`; rejected injection body absent from `validated_input`; envelope `out_of_scope` | ✅ PASS |

## Test Execution Summary
- Unit (nodes + services + graph wiring) + Integration + Graph.invoke routing + PB
- Pass: 62 · Skip: 3 (server import + 2 PB-7 stubs) · env-diff: `test_pb_invoke_order` (real SDK on CI)
- Coverage: **93%**
