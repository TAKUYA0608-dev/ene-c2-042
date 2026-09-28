"""ENE-C2-042 — deterministic domain services (no framework imports).

DerEligibilityKB: a seeded knowledge base of DER (distributed energy resource) flexibility-program
eligibility rules and thresholds — one rule per asset type (battery storage / solar PV / EV charger /
demand-response load / CHP) with the minimum rated capacity, controllability / telemetry requirements,
availability class, and a source citation. Classification, portfolio-scenario evaluation, and
portfolio-fit are **deterministic** (rule/threshold matching) and auditable; the production LLM is
reserved for narrative phrasing of the deliverable only.

Advisory only: nothing here enrols, registers, dispatches, or activates any asset — it evaluates
eligibility and portfolio fit to inform an authorised human decision.
"""

from __future__ import annotations

from typing import Any

# ── program thresholds (configurable rules) ───────────────────────────────────
# The minimum aggregate flexible capacity a portfolio must reach to be program-eligible, and the
# per-grid-area capacity above which a local (feeder / substation) constraint is flagged for review.
MIN_PORTFOLIO_KW = 50.0
AREA_CONSTRAINT_KW = 500.0

# ── seeded DER eligibility rules (per asset type) ─────────────────────────────
# Each rule: {asset_class, min_rated_kw, requires_controllable, requires_telemetry, availability, source}
_RULES: dict[str, dict[str, Any]] = {
    "battery_storage": {
        "asset_class": "storage",
        "min_rated_kw": 10.0,
        "requires_controllable": True,
        "requires_telemetry": True,
        "availability": "high",
        "source": "資源エネルギー庁 DER/VPP フレキシビリティ登録要件 (蓄電池)",
    },
    "solar_pv": {
        "asset_class": "generation",
        "min_rated_kw": 10.0,
        "requires_controllable": True,
        "requires_telemetry": True,
        "availability": "variable",
        "source": "資源エネルギー庁 DER/VPP フレキシビリティ登録要件 (太陽光・出力制御)",
    },
    "ev_charger": {
        "asset_class": "flexible_load",
        "min_rated_kw": 6.0,
        "requires_controllable": True,
        "requires_telemetry": True,
        "availability": "intermittent",
        "source": "資源エネルギー庁 DER/VPP フレキシビリティ登録要件 (EV充電・スマート充電)",
    },
    "demand_response_load": {
        "asset_class": "flexible_load",
        "min_rated_kw": 50.0,
        "requires_controllable": True,
        "requires_telemetry": True,
        "availability": "contract",
        "source": "電力広域的運営推進機関 需給調整市場 DRリソース要件",
    },
    "chp": {
        "asset_class": "generation",
        "min_rated_kw": 20.0,
        "requires_controllable": True,
        "requires_telemetry": True,
        "availability": "high",
        "source": "資源エネルギー庁 DER/VPP フレキシビリティ登録要件 (コージェネ)",
    },
}

_TYPE_ALIASES = {
    "蓄電池": "battery_storage",
    "バッテリー": "battery_storage",
    "battery": "battery_storage",
    "bess": "battery_storage",
    "storage": "battery_storage",
    "太陽光": "solar_pv",
    "pv": "solar_pv",
    "solar": "solar_pv",
    "ev充電": "ev_charger",
    "evse": "ev_charger",
    "charger": "ev_charger",
    "ev": "ev_charger",
    "デマンドレスポンス": "demand_response_load",
    "負荷": "demand_response_load",
    "load": "demand_response_load",
    "dr": "demand_response_load",
    "コージェネ": "chp",
    "cogeneration": "chp",
    "chp": "chp",
}


class DerEligibilityKB:
    """Deterministic DER eligibility classification + portfolio-scenario evaluation."""

    @staticmethod
    def normalize_type(raw: str | None) -> str | None:
        low = (raw or "").strip().lower()
        if low in _RULES:
            return low
        for alias, canonical in _TYPE_ALIASES.items():
            if alias in low:
                return canonical
        return None

    @staticmethod
    def classify(asset: dict[str, Any]) -> dict[str, Any]:
        """Classify a single asset against the eligibility rules. Auditable, no LLM."""
        asset_id = str(asset.get("asset_id", "UNKNOWN"))
        atype = DerEligibilityKB.normalize_type(asset.get("asset_type"))
        rated = _to_float(asset.get("rated_kw"))
        controllable = bool(asset.get("controllable", False))
        telemetry = bool(asset.get("telemetry", False))
        area = str(asset.get("area") or "UNSPECIFIED")

        if atype is None:
            return {
                "asset_id": asset_id,
                "asset_class": "unknown",
                "eligible": False,
                "control_eligible": False,
                "constraints": ["unrecognised asset type"],
                "reason": f"asset_type '{asset.get('asset_type')}' は未対応",
                "source": None,
                "rated_kw": rated,
                "availability": "none",
                "area": area,
                "asset_type": None,
            }

        rule = _RULES[atype]
        constraints: list[str] = []
        if rated < rule["min_rated_kw"]:
            constraints.append(f"rated_kw {rated} < 最小要件 {rule['min_rated_kw']} kW")
        if rule["requires_controllable"] and not controllable:
            constraints.append("遠隔制御 (controllable) 未対応")
        if rule["requires_telemetry"] and not telemetry:
            constraints.append("計量/テレメトリ (telemetry) 未対応")

        capacity_ok = rated >= rule["min_rated_kw"]
        control_eligible = (not rule["requires_controllable"]) or controllable
        telemetry_ok = (not rule["requires_telemetry"]) or telemetry
        eligible = capacity_ok and control_eligible and telemetry_ok
        reason = "適格 (要件充足)" if eligible else "要確認: " + " / ".join(constraints)
        return {
            "asset_id": asset_id,
            "asset_class": rule["asset_class"],
            "eligible": eligible,
            "control_eligible": control_eligible,
            "constraints": constraints,
            "reason": reason,
            "source": rule["source"],
            "rated_kw": rated,
            "availability": rule["availability"],
            "area": area,
            "asset_type": atype,
        }

    @staticmethod
    def evaluate_scenarios(classified: list[dict[str, Any]]) -> dict[str, Any]:
        """Deterministic capacity / availability / local-constraint scenario evaluation."""
        eligible = [c for c in classified if c.get("eligible")]
        eligible_capacity = round(sum(_to_float(c.get("rated_kw")) for c in eligible), 2)

        # capacity scenario
        capacity_meets = eligible_capacity >= MIN_PORTFOLIO_KW
        # availability scenario — firm (high/contract) vs weather/plug-in dependent (variable/intermittent)
        firm = sum(1 for c in eligible if c.get("availability") in ("high", "contract"))
        variable = sum(1 for c in eligible if c.get("availability") in ("variable", "intermittent"))
        availability_class = (
            "firm" if firm and not variable else "mixed" if firm and variable else "variable" if variable else "none"
        )
        # local-constraint scenario — capacity concentrated in one grid area beyond the area cap
        by_area: dict[str, float] = {}
        for c in eligible:
            area = str(c.get("area") or "UNSPECIFIED")
            by_area[area] = by_area.get(area, 0.0) + _to_float(c.get("rated_kw"))
        constrained_areas = {a: round(kw, 2) for a, kw in by_area.items() if kw > AREA_CONSTRAINT_KW}

        if capacity_meets and availability_class in ("firm", "mixed") and not constrained_areas:
            portfolio_fit = "fit"
        elif not eligible:
            portfolio_fit = "review"
        elif capacity_meets and not constrained_areas:
            portfolio_fit = "partial"
        else:
            portfolio_fit = "review"

        scenarios = [
            {
                "name": "capacity",
                "eligible_capacity_kw": eligible_capacity,
                "threshold_kw": MIN_PORTFOLIO_KW,
                "meets": capacity_meets,
            },
            {"name": "availability", "class": availability_class, "firm_count": firm, "variable_count": variable},
            {"name": "local_constraint", "area_cap_kw": AREA_CONSTRAINT_KW, "constrained_areas": constrained_areas},
        ]
        return {
            "eligible_capacity_kw": eligible_capacity,
            "eligible_count": len(eligible),
            "portfolio_fit": portfolio_fit,
            "scenarios": scenarios,
        }


def _to_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0
