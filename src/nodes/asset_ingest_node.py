"""ENE-C2-042 — inner workflow step 1: asset_ingest.

Deterministic ingest/normalisation of the validated DER application into structured asset records.
Sets ``ingest_count``; **0 assets (rejected input or none supplied) routes to the out-of-scope safe
answer** — the agent never fabricates enrollment guidance for assets it was not given.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.utils.audit import emit_trace_event


class AssetIngestNode(FunctionNode):
    """Ingest and normalise DER asset records from the validated application."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        scope = json.loads(state.get("validated_input") or state.get("user_input") or "{}")
        canonical = json.dumps(scope, ensure_ascii=False)
        assets = [a for a in (scope.get("assets") or []) if isinstance(a, dict) and a.get("asset_id")]

        if state.get("error_code") or not assets:
            emit_trace_event("asset_ingest.skip", {"reason": state.get("error_code") or "no_assets"}, state)
            return {
                "validated_input": canonical,
                "ingested_assets": "[]",
                "ingest_count": 0,
                "error_code": state.get("error_code") or "NO_DATA",
                "status": AgentStatus.SUCCESS.value,
            }

        emit_trace_event("asset_ingest.complete", {"asset_count": len(assets)}, state)
        return {
            "validated_input": canonical,
            "ingested_assets": json.dumps(assets, ensure_ascii=False),
            "ingest_count": len(assets),
            "status": AgentStatus.SUCCESS.value,
        }
