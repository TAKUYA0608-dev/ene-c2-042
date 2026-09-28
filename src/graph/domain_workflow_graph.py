"""ENE-C2-042 — inner domain workflow graph (Cat 2).

Instantiated by DerEnrollmentWorkflowGraphNode.get_subgraph() in graph.py. Linear topology with per-node
skip guards (the portable Cat 2 form; conditional edges don't propagate across the subgraph boundary):

    START → asset_ingest → eligibility_classify → portfolio_scenario_evaluate → deliverable_synthesis → END

On rejected / 0-asset input, asset_ingest sets ingest_count=0 (+error_code=NO_DATA); classify and
scenario nodes no-op and deliverable_synthesis emits the out-of-scope safe answer — no fabricated
enrollment guidance.
"""

from __future__ import annotations
from typing import Any

from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState

from src.nodes.asset_ingest_node import AssetIngestNode
from src.nodes.deliverable_synthesis_node import DeliverableSynthesisNode
from src.nodes.eligibility_classify_node import EligibilityClassifyNode
from src.nodes.portfolio_scenario_node import PortfolioScenarioEvaluateNode
from src.schemas.state import State


class DerEnrollmentWorkflow(BaseGraph):
    """Inner graph: asset_ingest → eligibility_classify → portfolio_scenario_evaluate → deliverable_synthesis."""

    @property
    def name(self) -> str:
        return "DerEnrollmentWorkflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        pass

    def register_nodes(self) -> None:
        # No super() — BaseGraph.register_nodes() is abstract.
        self._nodes["asset_ingest"] = AssetIngestNode()
        self._nodes["eligibility_classify"] = EligibilityClassifyNode()
        self._nodes["portfolio_scenario_evaluate"] = PortfolioScenarioEvaluateNode()
        self._nodes["deliverable_synthesis"] = DeliverableSynthesisNode()

    def add_edges(self) -> None:
        # Static linear backbone; the 0-asset / rejected skip is handled by per-node guards.
        self._sg.add_edge(START, "asset_ingest")
        self._sg.add_edge("asset_ingest", "eligibility_classify")
        self._sg.add_edge("eligibility_classify", "portfolio_scenario_evaluate")
        self._sg.add_edge("portfolio_scenario_evaluate", "deliverable_synthesis")
        self._sg.add_edge("deliverable_synthesis", END)

    def route(self, state: AgentState) -> str:
        """Required by the BaseGraph ABC. Linear topology → not wired to a conditional edge."""
        if state.get("error_code") or state.get("ingest_count", 0) == 0:
            return "deliverable_synthesis"
        return "eligibility_classify"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        return {
            "output": state.get("result"),
            "status": state.get("status"),
            "ingest_count": state.get("ingest_count", 0),
            "error_code": state.get("error_code"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
