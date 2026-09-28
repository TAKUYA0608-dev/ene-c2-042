"""ENE-C2-042 — inner workflow step 2: eligibility_classify.

Deterministic classification of each DER asset against the configurable eligibility rules / thresholds
(asset class, minimum rated capacity, controllability, telemetry) with the source citation and the
unmet-requirement constraints. Skips (no-op) on rejected / 0-asset input — the LLM in production is
reserved for narrative phrasing, not the rule-grounded eligibility verdict.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.services.service import DerEligibilityKB
from src.utils.audit import emit_trace_event


class EligibilityClassifyNode(FunctionNode):
    """Classify asset-class + control eligibility for each ingested asset."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("error_code") or state.get("ingest_count", 0) == 0:
            # Skip (rejected / 0-asset) — still emit a count-only S-4 event (every execute() path
            # emits at least one domain event; empty return without an event is prohibited).
            emit_trace_event("eligibility_classify.skip", {"reason": state.get("error_code") or "no_assets"}, state)
            return {}
        assets = json.loads(state.get("ingested_assets") or "[]")
        elig = [DerEligibilityKB.classify(a) for a in assets]
        emit_trace_event(
            "eligibility_classify.complete",
            {"count": len(elig), "eligible": sum(1 for e in elig if e["eligible"])},
            state,
        )
        return {"eligibility": json.dumps(elig, ensure_ascii=False), "status": AgentStatus.SUCCESS.value}
