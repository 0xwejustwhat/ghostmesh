from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from ghostmesh.domain import NodeType, PatchPanel
from ghostmesh.patchpanel.errors import PatchPanelValidationError


@dataclass(frozen=True)
class GraphValidationReport:
    node_count: int
    edge_count: int
    cycles: list[list[str]] = field(default_factory=list)


class PatchPanelValidator:
    """Validate Patch Panel graph semantics without executing the workflow."""

    def validate(self, patch_panel: PatchPanel) -> GraphValidationReport:
        errors: list[str] = []
        node_ids = {node.id for node in patch_panel.nodes}
        bucket_ids = {bucket.id for bucket in patch_panel.buckets}
        contract_ids = {contract.id for contract in patch_panel.acceptance_contracts}

        self._validate_contract_references(patch_panel, contract_ids, errors)
        self._validate_edges(patch_panel, node_ids, errors)
        self._validate_validator_edges(patch_panel, errors)
        self._validate_pipe_bindings(patch_panel, node_ids, bucket_ids, errors)

        graph = self._build_graph(patch_panel)
        self._validate_boundaries(patch_panel, graph, errors)
        self._validate_reachability(patch_panel, graph, errors)
        self._validate_dead_ends(patch_panel, graph, errors)

        if errors:
            raise PatchPanelValidationError(errors)

        return GraphValidationReport(
            node_count=graph.number_of_nodes(),
            edge_count=graph.number_of_edges(),
            cycles=list(nx.simple_cycles(graph)),
        )

    def _build_graph(self, patch_panel: PatchPanel) -> nx.DiGraph:
        graph = nx.DiGraph()
        for node in patch_panel.nodes:
            graph.add_node(node.id, type=node.type)
        for edge in patch_panel.edges:
            graph.add_edge(edge.from_node, edge.to_node, on=edge.on, condition=edge.condition)
        return graph

    def _validate_contract_references(
        self,
        patch_panel: PatchPanel,
        contract_ids: set[str],
        errors: list[str],
    ) -> None:
        for bucket in patch_panel.buckets:
            if bucket.acceptance_contract and bucket.acceptance_contract not in contract_ids:
                errors.append(
                    f"bucket '{bucket.id}' references unknown acceptance contract "
                    f"'{bucket.acceptance_contract}'"
                )

        for node in patch_panel.nodes:
            if node.acceptance_contract and node.acceptance_contract not in contract_ids:
                errors.append(
                    f"node '{node.id}' references unknown acceptance contract "
                    f"'{node.acceptance_contract}'"
                )

    def _validate_edges(
        self,
        patch_panel: PatchPanel,
        node_ids: set[str],
        errors: list[str],
    ) -> None:
        for edge in patch_panel.edges:
            if edge.from_node not in node_ids:
                errors.append(f"edge from '{edge.from_node}' references an unknown node")
            if edge.to_node not in node_ids:
                errors.append(f"edge to '{edge.to_node}' references an unknown node")

    def _validate_validator_edges(
        self,
        patch_panel: PatchPanel,
        errors: list[str],
    ) -> None:
        validators = {
            node.id: set(node.output_pipes)
            for node in patch_panel.nodes
            if node.type == NodeType.VALIDATOR
        }
        for edge in patch_panel.edges:
            output_pipes = validators.get(edge.from_node)
            if output_pipes is None:
                continue
            if edge.on not in output_pipes:
                errors.append(
                    f"validator edge from '{edge.from_node}' uses exit '{edge.on}' "
                    "that is not declared in output_pipes"
                )

    def _validate_pipe_bindings(
        self,
        patch_panel: PatchPanel,
        node_ids: set[str],
        bucket_ids: set[str],
        errors: list[str],
    ) -> None:
        declared_pipes: dict[str, tuple[str, str]] = {}
        for node in patch_panel.nodes:
            for pipe in node.input_pipes:
                declared_pipes[pipe] = (node.id, "input")
            for pipe in node.output_pipes:
                declared_pipes[pipe] = (node.id, "output")

        for pipe, binding in patch_panel.pipe_bindings.items():
            if pipe not in declared_pipes:
                errors.append(f"pipe binding '{pipe}' is not declared by any node")
                continue

            declared_node_id, declared_direction = declared_pipes[pipe]
            if binding.node and binding.node not in node_ids:
                errors.append(f"pipe binding '{pipe}' references unknown node '{binding.node}'")
            if binding.node and binding.node != declared_node_id:
                errors.append(
                    f"pipe binding '{pipe}' is assigned to node '{binding.node}' but is declared "
                    f"by node '{declared_node_id}'"
                )
            if binding.direction and binding.direction != declared_direction:
                errors.append(
                    f"pipe binding '{pipe}' declares direction '{binding.direction}' but the node "
                    f"declares it as '{declared_direction}'"
                )
            if binding.bucket not in bucket_ids:
                errors.append(f"pipe binding '{pipe}' references unknown bucket '{binding.bucket}'")

        for pipe in declared_pipes:
            if pipe not in patch_panel.pipe_bindings:
                errors.append(f"declared pipe '{pipe}' is missing a pipe binding")

    def _validate_boundaries(
        self,
        patch_panel: PatchPanel,
        graph: nx.DiGraph,
        errors: list[str],
    ) -> None:
        source_nodes = [node for node in patch_panel.nodes if node.type == NodeType.SOURCE]
        sink_nodes = [node for node in patch_panel.nodes if node.type == NodeType.SINK]

        if not source_nodes:
            errors.append("Patch Panel must declare at least one source node")
        if not sink_nodes:
            errors.append("Patch Panel must declare at least one sink node")

        for node in source_nodes:
            if graph.in_degree(node.id) > 0:
                errors.append(f"source node '{node.id}' must not have incoming edges")
        for node in sink_nodes:
            if graph.out_degree(node.id) > 0:
                errors.append(f"sink node '{node.id}' must not have outgoing edges")

    def _validate_reachability(
        self,
        patch_panel: PatchPanel,
        graph: nx.DiGraph,
        errors: list[str],
    ) -> None:
        source_ids = [node.id for node in patch_panel.nodes if node.type == NodeType.SOURCE]
        if not source_ids:
            return

        reachable: set[str] = set(source_ids)
        for source_id in source_ids:
            reachable.update(nx.descendants(graph, source_id))

        for node in patch_panel.nodes:
            if node.id not in reachable:
                errors.append(f"node '{node.id}' is not reachable from any source node")

    def _validate_dead_ends(
        self,
        patch_panel: PatchPanel,
        graph: nx.DiGraph,
        errors: list[str],
    ) -> None:
        sink_ids = {node.id for node in patch_panel.nodes if node.type == NodeType.SINK}
        for node in patch_panel.nodes:
            if node.id not in sink_ids and graph.out_degree(node.id) == 0:
                errors.append(f"node '{node.id}' is a dead end and is not a sink")
