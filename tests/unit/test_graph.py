# ENE-C2-042 — Unit Tests: Cat 2 graph wiring (outer GraphNode + inner workflow)

import pytest

from src.graph.domain_workflow_graph import DerEnrollmentWorkflow
from src.graph.graph import (
    DerEnrollmentWorkflowGraphNode,
    DistributedEnergyResourceFlexibilityEnrollmentEligibilityAgent,
    Graph,
)
from src.schemas.state import State


class TestOuterGraph:
    def test_registry_alias(self):
        assert DistributedEnergyResourceFlexibilityEnrollmentEligibilityAgent is Graph

    def test_name_and_state_schema(self):
        g = Graph()
        assert g.name == "DistributedEnergyResourceFlexibilityEnrollmentEligibilityAgent"
        assert g.state_schema is State

    def test_main_slot_is_graphnode(self):
        g = Graph()
        g.register_nodes()
        assert isinstance(g._nodes["main"], DerEnrollmentWorkflowGraphNode)
        for slot in ("pre_process", "main", "post_process"):
            assert slot in g._nodes

    def test_error_strategy_propagate(self):
        assert DerEnrollmentWorkflowGraphNode.error_strategy == "propagate"
        assert DerEnrollmentWorkflowGraphNode.propagate_hitl is False

    def test_get_subgraph_is_cached(self):
        node = DerEnrollmentWorkflowGraphNode()
        assert node.get_subgraph() is node.get_subgraph()

    def test_extract_input(self):
        node = DerEnrollmentWorkflowGraphNode()
        assert node.extract_input({"validated_input": "V"}) == "V"
        assert node.extract_input({"user_input": "U"}) == "U"

    def test_merge_output_maps_fields(self):
        node = DerEnrollmentWorkflowGraphNode()
        merged = node.merge_output({}, {"output": '{"x":1}', "ingest_count": 2, "status": "success",
                                        "error_code": None})
        assert merged["result"] == '{"x":1}' and merged["ingest_count"] == 2
        assert merged["status"] == "success"


class TestInnerWorkflow:
    def test_inner_registers_four_nodes(self):
        wf = DerEnrollmentWorkflow(config={})
        wf.register_nodes()
        for slot in ("asset_ingest", "eligibility_classify", "portfolio_scenario_evaluate",
                     "deliverable_synthesis"):
            assert slot in wf._nodes

    def test_name_and_state_schema(self):
        wf = DerEnrollmentWorkflow(config={})
        assert wf.name == "DerEnrollmentWorkflow"
        assert wf.state_schema is State

    def test_route_zero_hit_to_deliverable(self):
        wf = DerEnrollmentWorkflow(config={})
        assert wf.route({"ingest_count": 0}) == "deliverable_synthesis"
        assert wf.route({"error_code": "NO_DATA", "ingest_count": 3}) == "deliverable_synthesis"

    def test_route_default_to_classify(self):
        wf = DerEnrollmentWorkflow(config={})
        assert wf.route({"ingest_count": 3}) == "eligibility_classify"

    def test_get_output_surfaces_fields(self):
        wf = DerEnrollmentWorkflow(config={})
        out = wf.get_output({"result": "R", "status": "success", "ingest_count": 2,
                             "error_code": None, "node_history": []})
        assert out["output"] == "R" and out["ingest_count"] == 2 and out["status"] == "success"


class TestServerModule:
    def test_server_imports(self):
        try:
            import src.api.server as server
        except ModuleNotFoundError as exc:
            pytest.skip(f"platform module unavailable in the local stub env: {exc}")
        assert server.app is not None and server.agent is not None
