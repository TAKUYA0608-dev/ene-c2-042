# Template Design Specification — ENE-C2-042

Distributed Energy Resource (DER) Flexibility Enrollment Eligibility & Portfolio Planning Agent (Cat 2).

## Position in AgentCore Architecture

- **Agent Class**: `DistributedEnergyResourceFlexibilityEnrollmentEligibilityAgent` (module-level alias of `Graph`)
- **L1 Base**: **AgentBaseGraph** (Cat 2 — outer 5-node backbone; direct L1 inheritance, no L2)
- **Category**: Cat 2 — a multi-step domain workflow (validate → classify → scenario-evaluate → synthesise →
  human-approval) producing a DRAFT enrollment decision package + capacity/portfolio plan; ENE industry
- **Three-Layer Separation**: State = flat TypedDict; Node = L1 inheritance (`execute` override only);
  Graph = outer `AgentBaseGraph` + **`GraphNode` in the `main` slot** wrapping an inner `BaseGraph`

## Architecture Overview

Cat 2 pattern — the `main` slot is a **`GraphNode`** (`DerEnrollmentWorkflowGraphNode`, **subgraph cached**)
that wraps the inner `DerEnrollmentWorkflow` (`BaseGraph`). The inner graph is a **static linear backbone
with per-node skip guards** (conditional edges do not propagate across the subgraph boundary).

**Advisory (decision-support) only.** The agent classifies asset/control eligibility, evaluates
capacity/availability/local-constraint scenarios, and synthesises a **DRAFT** enrollment/portfolio
deliverable. It never performs real enrollment, market registration, dispatch optimisation, flexibility
activation, or grid operation — the final decision (and gap/exception owner) is an **authorised portfolio
manager** via the mandatory HumanApprovalGate.

### Node Configuration

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | schema_version, session_id, trust_level | user_input | (framework) | InitializeNode (default) |
| pre_process | `PreProcessNode` (InputValidation) — **S-1 normalisation** (NFKC + control-char strip) + parse application/asset slots + **execute-level input-security gate as a degraded path** (prompt-injection / unauthorised / over-scope / oversize → discard asset body, `validated_input="{}"`, degraded `SUCCESS + error_code` = `INJECTION_REJECTED` / `UNAUTHORIZED_INPUT` / `INPUT_TOO_LONG`; the `_extra_security_gate_input` hook is a no-op — never `status=ERROR`) | user_input | validated_input, input_format, enriched_context, error_code | FunctionNode.execute |
| main | `DerEnrollmentWorkflowGraphNode` (GraphNode) → inner workflow | validated_input | result, ingest_count, error_code, status | GraphNode |
| post_process | `PostProcessNode` (HumanApprovalGate) — **S-3 output gate** (injection/echo block + citation completeness + DRAFT disclaimer preservation) + human-review status + **S-4 audit** | result | formatted_output, disclaimer, human_review_required, audit_logged | FunctionNode.execute |
| finalize | response_metadata, total_time_ms | | (framework) | FinalizeNode (default) |

**Inner workflow (`DerEnrollmentWorkflow` : BaseGraph):**

```
START → asset_ingest → eligibility_classify → portfolio_scenario_evaluate → deliverable_synthesis → END
```

| Inner node | Responsibility |
|---|---|
| AssetIngest | deterministic ingest/normalise of the DER application + asset records → `ingest_count`; **0 assets → NO_DATA → out-of-scope safe answer** |
| EligibilityClassify | **deterministic** asset-class + control-eligibility classification against configurable rules / thresholds (min rated kW, controllability, telemetry); extracts operational constraints (skips on rejected / 0-hit) |
| PortfolioScenarioEvaluate | **deterministic** capacity / availability / local-constraint scenario evaluation → portfolio-fit (no single-verdict overreach; skips on rejected / 0-hit) |
| DeliverableSynthesis | synthesise enrollment decision package + capacity/portfolio plan — source / assumptions / exceptions / candidate approver + citations; **0-hit → out-of-scope safe answer** (`citations=[]`) |

> **Deterministic vs LLM:** classification and scenario evaluation are implemented deterministically
> (configurable rules / thresholds → auditable). The production LLM is reserved for semantic phrasing of
> the deliverable narrative; the eligibility/scenario judgement itself is rule-grounded and citable.

### Data Flow

```
START → initialize → pre_process → main(GraphNode → inner linear workflow) → post_process → finalize → END
                                     ↓ (retry, max 3)
                                   pre_process
```

Rejected / 0-asset input sets `error_code` + `ingest_count=0`; eligibility & scenario nodes no-op and
`deliverable_synthesis` emits the out-of-scope safe answer — no fabricated enrollment guidance.

### State Definition

| Field | Type | Purpose |
|-------|------|---------|
| validated_input | str (JSON) | `{program, assets[], eligibility_ref, operator}` (scoped input) |
| ingested_assets / ingest_count | str/int | normalised asset records / 0 → out-of-scope safe answer |
| eligibility | str (JSON) | `[{asset_id, asset_class, eligible, control_eligible, constraints[], reason, source}]` |
| portfolio_scenarios | str (JSON) | `{eligible_capacity_kw, scenarios[], portfolio_fit}` |
| result / formatted_output | str (JSON) | inner deliverable / final envelope |
| disclaimer / human_review_required / audit_logged | str/bool | mandatory DRAFT disclaimer + HITL routing + terminal audit |
| error_code / error_message | str | degraded path (SUCCESS + error_code, never status=ERROR) |

**State Constraints:** flat TypedDict; JSON strings for complex fields; `enriched_context` is a JSON
string (ADR-005); no credentials/secrets persisted.

## Framework Utilization

- [x] **GraphNode-in-main** (Cat 2 composition, criterion #9) — `error_strategy="propagate"`, `propagate_hitl=False`, **subgraph cached**
- [x] S-1 `required_trust_level=VERIFIED_EXTERNAL` on all `FunctionNode` subclasses
- [x] S-2 `_extra_security_gate_input()` (pre) — **no-op** (SDK 1.0.0): never raises, never returns `status=ERROR` (ERROR short-circuits `__call__` → skips main / post_process). The **input-security gate** (prompt-injection / unauthorised / over-scope / oversize) is an **execute-level degraded path**: injection is detected in `execute()` (marker set — not deferred to S-3 only), the untrusted asset body is discarded (`validated_input="{}"`, `user_input` cleared), it returns `SUCCESS + error_code` (`INJECTION_REJECTED` / `UNAUTHORIZED_INPUT` / `INPUT_TOO_LONG`), and traverses the zero-asset safe branch + post_process S-3/S-4. Input **normalisation** (NFKC / control-char strip) is in `execute()` (S-1)
- [x] S-3 `_extra_security_gate_output()` (post) — **injection-echo block (defense-in-depth) + DRAFT-disclaimer preservation**; **may raise** (SDK 1.0.0)
- [x] S-4 `emit_trace_event()` in every `execute()` (asset class / counts / capacity aggregates only — no PII); terminal audit always fires

## Import Isolation Confirmation
- [x] No `agenticstar` SDK (Level 0) import — PB-4
- [x] Import targets: `framework/`, `langgraph`, and `src.` only

## Design Decision Record

| Decision | Chosen | Rationale |
|----------|--------|-----------|
| L1 base type | AgentBaseGraph | Fixed pipeline, no autonomous loop |
| Composition | **GraphNode-in-main + inner BaseGraph (cached)** | Cat 2 multi-step domain workflow |
| Inner topology | **Linear + per-node skip guards** | Conditional edges don't propagate across the subgraph boundary |
| Security split | **injection rejected at execute-level (INJECTION_REJECTED, body discarded); S-3 echo-block is defense-in-depth** | Untrusted body never processed; degraded SUCCESS keeps post_process (disclaimer / S-3 / S-4 audit) running |
| Eligibility / scenarios | **Deterministic (rules/thresholds)** | Auditable, citable; LLM reserved for narrative phrasing |
| Advisory only + HITL | **HumanApprovalGate mandatory; owner = candidate/placeholder** | No real enrollment / dispatch / grid op; final decision + owner assignment is human |
| Rejection signalling | SUCCESS + error_code | Guarantees post_process S-3/S-4 always run (SDK 1.0.0) |

## Open Items (Stage ③ implementation MR)
- Node implementations + inner workflow graph (shipped in the implementation MR).
- Seeded `DerEligibilityKB` (DER asset-type eligibility rules/thresholds: battery / solar PV / EV charger /
  demand-response load / CHP) with source citations.
- Unit + integration + PB tests; coverage ≥ 89%.
