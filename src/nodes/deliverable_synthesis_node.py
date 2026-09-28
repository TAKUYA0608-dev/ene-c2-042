"""ENE-C2-042 — inner workflow step 4: deliverable_synthesis.

Synthesises the DRAFT enrollment decision package + capacity/portfolio plan: per-asset eligibility
decisions (with source citation + unmet-requirement constraints), the portfolio scenario/fit summary,
assumptions, exceptions (assets needing review — owner left as candidate/placeholder), and the candidate
approver. On the 0-asset / rejected branch it emits the out-of-scope safe answer (``citations=[]``). The
final decision and owner assignment are made by the authorised human at the HumanApprovalGate.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.utils.audit import emit_trace_event

_OUT_OF_SCOPE = (
    "DER 登録申請に有効な資産データ（asset_type / rated_kw / controllable / telemetry / area）が"
    "見つかりませんでした。asset_type（蓄電池 / 太陽光 / EV充電 / デマンドレスポンス負荷 / コージェネ 等）と"
    "定格容量・制御可否を含む構造化された申請データをご提供いただくか、認可済み portfolio manager にご確認ください。"
)
_CANDIDATE_APPROVER = "candidate/placeholder — 認可済み portfolio manager が HumanApprovalGate で確定"
_ASSUMPTIONS = [
    "適格性は提供された asset_type / rated_kw / controllable / telemetry と登録要件しきい値に基づく",
    "容量・可用性・ローカル制約シナリオは申請時点のスナップショットに対する評価",
    "本 deliverable は DRAFT の意思決定支援であり、実際の enrollment 実行 / 市場登録 / 給電最適化 / 系統運用は行わない",
]


class DeliverableSynthesisNode(FunctionNode):
    """Compose the DRAFT enrollment/portfolio deliverable (or safe answer on 0-hit)."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        classified = json.loads(state.get("eligibility") or "[]")
        if state.get("error_code") or not classified:
            emit_trace_event("deliverable_synthesis.safe", {"reason": state.get("error_code") or "no_assets"}, state)
            report: dict[str, Any] = {
                "status_kind": "out_of_scope",
                "message": _OUT_OF_SCOPE,
                "enrollment_decisions": [],
                "portfolio_plan": {},
                "assumptions": [],
                "exceptions": [],
                "citations": [],
                "portfolio_fit": None,
                "draft": True,
            }
            return {"result": json.dumps(report, ensure_ascii=False), "status": AgentStatus.SUCCESS.value}

        scenarios = json.loads(state.get("portfolio_scenarios") or "{}")
        decisions: list[dict[str, Any]] = []
        citations: list[dict[str, str]] = []
        exceptions: list[dict[str, str]] = []
        for c in classified:
            decisions.append(
                {
                    "asset_id": c["asset_id"],
                    "asset_class": c["asset_class"],
                    "eligible": c["eligible"],
                    "control_eligible": c["control_eligible"],
                    "constraints": c["constraints"],
                    "reason": c["reason"],
                    "citation": c["source"],
                }
            )
            if c.get("source"):
                citations.append({"asset_id": c["asset_id"], "source": c["source"]})
            if not c["eligible"]:
                exceptions.append({"asset_id": c["asset_id"], "issue": c["reason"], "owner": _CANDIDATE_APPROVER})

        report = {
            "status_kind": "deliverable",
            "enrollment_decisions": decisions,
            "portfolio_plan": scenarios,
            "portfolio_fit": scenarios.get("portfolio_fit", "review"),
            "assumptions": _ASSUMPTIONS,
            "exceptions": exceptions,
            "candidate_approver": _CANDIDATE_APPROVER,
            "citations": citations,
            "draft": True,
        }
        emit_trace_event(
            "deliverable_synthesis.complete",
            {
                "decision_count": len(decisions),
                "citation_count": len(citations),
                "exception_count": len(exceptions),
                "portfolio_fit": scenarios.get("portfolio_fit"),
            },
            state,
        )
        return {"result": json.dumps(report, ensure_ascii=False), "status": AgentStatus.SUCCESS.value}
