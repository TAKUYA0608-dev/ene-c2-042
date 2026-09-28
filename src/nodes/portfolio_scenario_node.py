"""ENE-C2-042 — inner workflow step 3: portfolio_scenario_evaluate.

Deterministic evaluation of the eligible assets across capacity / availability / local-constraint
scenarios → a portfolio-fit judgement (``fit`` / ``partial`` / ``review``). Does not overreach to a single
verdict — surfaces the per-scenario detail so an authorised human can weigh it. Skips (no-op) on
rejected / 0-asset input.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.services.service import DerEligibilityKB
from src.utils.audit import emit_trace_event


class PortfolioScenarioEvaluateNode(FunctionNode):
    """Evaluate capacity / availability / local-constraint scenarios → portfolio-fit."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("error_code") or state.get("ingest_count", 0) == 0:
            # Skip (rejected / 0-asset) — still emit a count-only S-4 event (every execute() path
            # emits at least one domain event; empty return without an event is prohibited).
            emit_trace_event("portfolio_scenario.skip", {"reason": state.get("error_code") or "no_assets"}, state)
            return {}
        classified = json.loads(state.get("eligibility") or "[]")
        scenarios = DerEligibilityKB.evaluate_scenarios(classified)
        emit_trace_event(
            "portfolio_scenario.complete",
            {"portfolio_fit": scenarios["portfolio_fit"], "eligible_capacity_kw": scenarios["eligible_capacity_kw"]},
            state,
        )
        return {"portfolio_scenarios": json.dumps(scenarios, ensure_ascii=False), "status": AgentStatus.SUCCESS.value}
