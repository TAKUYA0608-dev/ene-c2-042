"""ENE-C2-042 — pre_process node: InputValidation (S-1 normalisation + S-2 access-scope gate).

S-1 (``execute``) = **input normalisation** (NFKC, strip control characters) and parse of the DER
enrollment application + asset records into ``{program, operator, assets, eligibility_ref}``.

Prompt-injection, unauthorised/over-scope callers, and oversize input are rejected here at the
**execute level** as a **degraded** path — the untrusted asset body is discarded
(``validated_input="{}"``, ``user_input`` cleared) and a degraded ``SUCCESS + error_code``
(``INJECTION_REJECTED`` / ``UNAUTHORIZED_INPUT`` / ``INPUT_TOO_LONG``) routes through the zero-asset
safe branch + HumanApprovalGate. Injection is **not** left
to S-3 defer only: it is detected in ``execute()`` and the body is never processed. The S-3 output
gate keeps its injection-echo neutralisation as **defense-in-depth**.

S-2 (``_extra_security_gate_input``) = **no-op** per SDK 1.0.0: the hook MUST NOT raise and MUST NOT
short-circuit with ``status=ERROR``. A ``status=ERROR`` return skips ``__call__`` → ``main`` / ``post_process``
so the safe envelope, DRAFT disclaimer, and S-4 terminal audit would never run.

``status`` uses ``AgentStatus.SUCCESS.value`` (SDK 1.0.0: string form for routing; degraded is SUCCESS,
never ERROR).
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.utils.audit import emit_trace_event

_MAX_INPUT = 40_000
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_INJECTION_MARKERS = (
    "ignore previous",
    "ignore all previous",
    "disregard the above",
    "system prompt",
    "you are now",
    "###system",
    "<|im_start|>",
)


def _nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "")


def _clean(text: str) -> str:
    """S-1 normalisation: strip control characters from a normalised string."""
    return _CONTROL.sub("", text)


class PreProcessNode(FunctionNode):
    """Validate the DER application and extract the enrollment/asset slots."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_input(self, state: dict[str, Any]) -> dict[str, Any]:
        """S-2 access-scope gate — **no-op** (SDK 1.0.0).

        MUST NOT raise and MUST NOT short-circuit with ``status=ERROR``: doing so skips main /
        post_process (safe envelope, DRAFT disclaimer, S-4 audit). Prompt-injection,
        over-scope, and oversize rejection are all degraded ``SUCCESS + error_code`` paths in
        ``execute()`` (``INJECTION_REJECTED`` / ``UNAUTHORIZED_INPUT`` / ``INPUT_TOO_LONG``) — the
        untrusted asset body is discarded and the zero-asset safe branch runs through the
        HumanApprovalGate. The framework's default S-2 masking still applies. Returns the state
        unchanged.
        """
        return dict(state)

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("user_input", "") or ""
        input_context = state.get("input_context", {}) or {}  # read-only [C1]
        enriched = json.dumps(
            {
                "source": "DistributedEnergyResourceFlexibilityEnrollmentEligibilityAgent",
                "channel": input_context.get("channel", "unknown"),
            },
            ensure_ascii=False,
        )

        # S-2 (execute-level degraded): prompt-injection / over-scope / oversize callers are rejected
        # here — NOT via a status=ERROR short-circuit. The untrusted asset body is discarded
        # (validated_input="{}", user_input cleared) and a degraded SUCCESS + error_code is returned so
        # the zero-asset safe branch + post_process (disclaimer / redaction / S-4 audit) always run.
        # Injection is detected here, never processed — not deferred
        # to S-3.
        reject = self._scope_reject(raw, input_context)
        if reject:
            emit_trace_event("input_validation.rejected", {"reason": reject}, state)
            return {
                "validated_input": "{}",
                "input_format": "rejected",
                "enriched_context": enriched,
                "user_input": "",
                "error_code": reject,
                "error_message": "input rejected at input-security gate; asset body not processed",
                "status": AgentStatus.SUCCESS.value,
            }

        if not raw.strip():
            emit_trace_event("input_validation.rejected", {"reason": "empty_input"}, state)
            return {
                "validated_input": "{}",
                "input_format": "empty",
                "enriched_context": enriched,
                "error_code": "INPUT_REJECTED",
                "status": AgentStatus.SUCCESS.value,
            }

        scope, fmt = self._parse(_clean(_nfkc(raw)).strip())
        emit_trace_event(
            "input_validation.validated",
            {"input_format": fmt, "program": scope.get("program"), "asset_count": len(scope.get("assets", []))},
            state,
        )
        return {
            "validated_input": json.dumps(scope, ensure_ascii=False),
            "input_format": fmt,
            "enriched_context": enriched,
            "status": AgentStatus.SUCCESS.value,
        }

    def _scope_reject(self, raw: str, input_context: dict[str, Any]) -> str | None:
        """Execute-level degraded decision: injection / over-size / unauthorised → error_code (else None).

        Prompt-injection is detected on the NFKC-normalised, lower-cased input so the untrusted body is
        never processed. Returns the ``error_code`` string or ``None`` to proceed.
        """
        if any(marker in _nfkc(raw).lower() for marker in _INJECTION_MARKERS):
            return "INJECTION_REJECTED"
        if len(raw) > _MAX_INPUT:
            return "INPUT_TOO_LONG"
        if input_context.get("authorized") is False:
            return "UNAUTHORIZED_INPUT"
        return None

    def _parse(self, text: str) -> tuple[dict[str, Any], str]:
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                assets = obj.get("assets") or obj.get("resources") or []
                if not isinstance(assets, list):
                    assets = []
                return {
                    "program": _norm(obj.get("program")),
                    "operator": _norm(obj.get("operator")),
                    "eligibility_ref": _norm(obj.get("eligibility_ref")),
                    "assets": [_norm_asset(a) for a in assets if isinstance(a, dict)],
                }, "json"
        except (ValueError, TypeError):
            pass
        # Free-text application without structured assets → parseable but 0 assets (→ NO_DATA downstream).
        return {
            "program": None,
            "operator": None,
            "eligibility_ref": None,
            "assets": [],
            "note": _clean(text)[:2000],
        }, "text"


def _norm(v: Any) -> Any:
    return _clean(_nfkc(str(v))) if isinstance(v, str) else v


def _norm_asset(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": _norm(a.get("asset_id")),
        "asset_type": _norm(a.get("asset_type")),
        "rated_kw": a.get("rated_kw"),
        "controllable": bool(a.get("controllable", False)),
        "telemetry": bool(a.get("telemetry", False)),
        "area": _norm(a.get("area")),
    }
