"""ENE-C2-042 — post_process node: HumanApprovalGate (S-3 output gate + S-4 audit).

S-3 (``_extra_security_gate_output``): the **injection defence lives here** — block any output that echoes
prompt-injection markers (grounded deliverables never contain them), verify citation completeness for a
grounded deliverable, and preserve the mandatory DRAFT / advisory disclaimer. Per SDK 1.0.0 this hook
receives the ``execute()`` result delta and MAY raise to block.

``execute``: assembles the final envelope, routes every material decision to an authorised portfolio
manager (``human_review_required``), appends the DRAFT disclaimer, and emits the S-4 terminal audit
(asset/decision counts + portfolio-fit only — no meter/customer PII). Runs on both the full deliverable
and the out-of-scope safe branch.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.utils.audit import emit_trace_event

_DISCLAIMER = (
    "【DRAFT / 参考】本 deliverable は公開された DER フレキシビリティ登録要件と提供された資産データに基づく"
    "意思決定支援（advisory）であり、適格性判定・容量シナリオ評価・portfolio plan の DRAFT です。"
    "実際の enrollment 実行・市場登録・給電最適化（dispatch）・フレキシビリティ起動・系統運用は一切行いません。"
    "最終的な enrollment / market commitment / portfolio 判断、および gap / 例外の owner 確定は、"
    "認可済み portfolio manager が HumanApprovalGate で行ってください。"
)
_INJECTION_MARKERS = (
    "ignore previous",
    "ignore all previous",
    "disregard the above",
    "system prompt",
    "you are now",
    "###system",
    "<|im_start|>",
)


class PostProcessNode(FunctionNode):
    """HumanApprovalGate: verify citations, block injection echoes, append DRAFT disclaimer, emit audit."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_output(self, result: dict[str, Any]) -> dict[str, Any]:
        """S-3 output gate — injection-echo block + DRAFT-disclaimer preservation.

        SDK 1.0.0 contract: receives the **result dict from `execute()`**; returns the (possibly
        filtered) result. MAY raise to block an output that echoes an injection marker or is missing
        the mandatory DRAFT/advisory disclaimer.
        """
        out = result.get("formatted_output", "")
        if out:
            low = out.lower()
            if any(marker in low for marker in _INJECTION_MARKERS):
                raise ValueError("S-3: prompt-injection marker echoed in output")
            if "DRAFT" not in out and "参考" not in out:
                raise ValueError("S-3: mandatory DRAFT/advisory disclaimer missing from output")
        return dict(result)

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        report: dict[str, Any] = json.loads(state.get("result", "{}") or "{}")
        status_kind = report.get("status_kind")
        grounded = status_kind == "deliverable"

        citations = report.get("citations", [])
        decisions = report.get("enrollment_decisions", [])
        # S-3 citation completeness — evaluated **per decision**, not per submission. A grounded
        # deliverable is citation-complete only when *every* enrollment decision carries a non-empty
        # source citation. The previous `bool(citations)` check passed as long as *any* decision was
        # grounded, so a mixed submission (a recognised asset alongside an unknown / unsupported asset
        # whose classification has `source=None`) was silently marked complete even though one decision
        # had no citation — contradicting the S-3 guarantee.
        citation_complete = (not grounded) or (bool(decisions) and all(d.get("citation") for d in decisions))
        # HumanApprovalGate: every grounded enrollment/portfolio decision is routed to an authorised
        # human — the agent never finalises a material decision itself.
        human_review_required = grounded

        formatted = {
            "status_kind": status_kind,
            "enrollment_decisions": report.get("enrollment_decisions", []),
            "portfolio_plan": report.get("portfolio_plan", {}),
            "portfolio_fit": report.get("portfolio_fit"),
            "assumptions": report.get("assumptions", []),
            "exceptions": report.get("exceptions", []),
            "candidate_approver": report.get("candidate_approver"),
            "citations": citations,
            "citation_complete": citation_complete,
            "human_review_required": human_review_required,
            "message": report.get("message"),
            "draft": True,
            "disclaimer": _DISCLAIMER,
        }
        emit_trace_event(
            "human_approval_gate.complete",
            {
                "status_kind": status_kind,
                "decision_count": len(report.get("enrollment_decisions", [])),
                "citation_complete": citation_complete,
                "human_review_required": human_review_required,
                "portfolio_fit": report.get("portfolio_fit"),
                "error_code": state.get("error_code"),
            },
            state,
        )
        return {
            "formatted_output": json.dumps(formatted, ensure_ascii=False),
            "disclaimer": _DISCLAIMER,
            "human_review_required": human_review_required,
            "audit_logged": True,
            "status": AgentStatus.SUCCESS.value,
        }
