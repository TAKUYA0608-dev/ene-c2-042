"""ENE-C2-042 — Agent state (DER Flexibility Enrollment Eligibility & Portfolio Planning, Cat 2).

ADR-005: State is a flat TypedDict — never a validation/BaseModel instance. Complex fields are stored
as JSON strings (``NotRequired[str]`` + ``# JSON:``); nodes ``json.dumps`` on write / ``json.loads`` on read.

Advisory (decision-support) only: the agent classifies eligibility and evaluates portfolio scenarios to
synthesise a DRAFT enrollment/portfolio deliverable. It never performs real enrollment, market
registration, dispatch optimisation, flexibility activation, or grid operation — the final enrollment /
portfolio decision (and gap/exception owner assignment) is made by an authorised portfolio manager via
the mandatory HumanApprovalGate. Asset/meter data is treated as scoped input (S-2 access check).

All agent-specific fields are NotRequired (populated progressively; absent at empty-start invoke).
"""

from __future__ import annotations


from framework.schemas.agent_state import AgentState


class State(AgentState):
    """Agent state for the DER flexibility enrollment eligibility & portfolio planning workflow."""

    # ── pre_process (InputValidation — S-1 normalisation + S-2 access-scope gate) ─────────────
    validated_input: str  # JSON: {program, assets[], eligibility_ref, operator}
    input_format: str  # "json" | "text" | "empty" | "rejected"
    enriched_context: str  # JSON: {source, channel} (read-only caller context)

    # ── inner workflow (asset_ingest → eligibility_classify → portfolio_scenario → deliverable_synth) ─
    ingested_assets: str  # JSON: [{asset_id, asset_type, rated_kw, controllable, telemetry, area}]
    ingest_count: int  # DER assets ingested (0 → out-of-scope safe answer)
    eligibility: str  # JSON: [{asset_id, asset_class, eligible, control_eligible, constraints[], reason, source}]
    portfolio_scenarios: str  # JSON: {eligible_capacity_kw, scenarios[], portfolio_fit}
    result: str  # JSON: assembled enrollment/portfolio deliverable (inner report)

    # ── post_process (HumanApprovalGate — S-3 output gate + S-4 audit) ────────────────────────
    formatted_output: str  # JSON: final envelope (deliverable + human-review status + DRAFT disclaimer)
    disclaimer: str  # mandatory DRAFT / advisory disclaimer
    human_review_required: bool  # material decision / low confidence → portfolio-manager review
    audit_logged: bool  # True once the terminal audit event is emitted

    # ── degraded-path signalling (SUCCESS + error_code, never status=ERROR) ───────────────────
    error_code: str  # INPUT_REJECTED | INPUT_TOO_LONG | UNAUTHORIZED_INPUT | NO_DATA
    error_message: str  # operator-facing detail
