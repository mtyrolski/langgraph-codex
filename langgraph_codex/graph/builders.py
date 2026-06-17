from collections.abc import Sequence
from itertools import pairwise
from typing import Any, TypeAlias, cast

import langgraph.graph
from langgraph.graph.state import CompiledStateGraph, StateGraph

import langgraph_codex.execution.base as execution_base
import langgraph_codex.graph.constants as graph_constants
import langgraph_codex.graph.nodes as graph_nodes
import langgraph_codex.graph.state as graph_state
import langgraph_codex.utils.validation as validation_utils

WorkflowGraph: TypeAlias = StateGraph[
    graph_state.WorkflowState,
    None,
    graph_state.WorkflowState,
    graph_state.WorkflowState,
]
CompiledGraph: TypeAlias = CompiledStateGraph[
    graph_state.WorkflowState,
    None,
    graph_state.WorkflowState,
    graph_state.WorkflowState,
]
GraphEndpoint: TypeAlias = str | graph_constants.GraphNode


def build_context_only_graph(
    context_builder: graph_nodes.ContextBuilder | None = None,
) -> CompiledGraph:
    """Build a graph that prepares context and renders a prompt without executing it."""
    graph = _new_workflow_graph()
    _add_context_nodes(graph, context_builder)
    _connect_linear(
        graph,
        [
            langgraph.graph.START,
            graph_constants.GraphNode.BUILD_CONTEXT,
            graph_constants.GraphNode.RENDER_PROMPT,
            langgraph.graph.END,
        ],
    )
    return graph.compile()


def build_execution_graph(
    executor: execution_base.Executor | None = None,
    validators: list[validation_utils.Validator] | None = None,
    context_builder: graph_nodes.ContextBuilder | None = None,
    *,
    backend: execution_base.Executor | None = None,
) -> CompiledGraph:
    """Build a single-pass graph that renders a prompt, executes it, and reviews output."""
    selected_executor = _select_executor(executor=executor, backend=backend)
    graph = _new_workflow_graph()
    _add_context_nodes(graph, context_builder)
    _add_execution_nodes(graph, selected_executor, validators)
    _connect_linear(
        graph,
        [
            langgraph.graph.START,
            graph_constants.GraphNode.BUILD_CONTEXT,
            graph_constants.GraphNode.RENDER_PROMPT,
            graph_constants.GraphNode.EXECUTE,
            graph_constants.GraphNode.REVIEW,
            langgraph.graph.END,
        ],
    )
    return graph.compile()


def build_basic_backend_graph(
    backend: execution_base.Executor | None = None,
    validators: list[validation_utils.Validator] | None = None,
    context_builder: graph_nodes.ContextBuilder | None = None,
) -> CompiledGraph:
    """Build the execution graph using the older backend naming."""
    return build_execution_graph(
        executor=backend,
        validators=validators,
        context_builder=context_builder,
    )


def build_retry_graph(
    executor: execution_base.Executor | None = None,
    validators: list[validation_utils.Validator] | None = None,
    context_builder: graph_nodes.ContextBuilder | None = None,
    *,
    backend: execution_base.Executor | None = None,
) -> CompiledGraph:
    """Build an execution graph that retries while validation fails and budget remains."""
    selected_executor = _select_executor(executor=executor, backend=backend)
    graph = _new_workflow_graph()
    _add_context_nodes(graph, context_builder)
    _add_execution_nodes(graph, selected_executor, validators)
    _add_node(graph, graph_constants.GraphNode.RETRY, graph_nodes.retry_node)
    _connect_linear(
        graph,
        [
            langgraph.graph.START,
            graph_constants.GraphNode.BUILD_CONTEXT,
            graph_constants.GraphNode.RENDER_PROMPT,
            graph_constants.GraphNode.EXECUTE,
            graph_constants.GraphNode.REVIEW,
        ],
    )
    graph.add_conditional_edges(
        graph_constants.GraphNode.REVIEW.value,
        graph_nodes.route_after_review,
        {
            graph_constants.ReviewRoute.SUCCESS: langgraph.graph.END,
            graph_constants.ReviewRoute.RETRY: graph_constants.GraphNode.RETRY.value,
            graph_constants.ReviewRoute.FAIL: langgraph.graph.END,
        },
    )
    _connect(graph, graph_constants.GraphNode.RETRY, graph_constants.GraphNode.RENDER_PROMPT)
    return graph.compile()


def build_retry_backend_graph(
    backend: execution_base.Executor | None = None,
    validators: list[validation_utils.Validator] | None = None,
    context_builder: graph_nodes.ContextBuilder | None = None,
) -> CompiledGraph:
    """Build the retry graph using the older backend naming."""
    return build_retry_graph(
        executor=backend,
        validators=validators,
        context_builder=context_builder,
    )


def _new_workflow_graph() -> WorkflowGraph:
    return StateGraph(graph_state.WorkflowState)


def _add_context_nodes(
    graph: WorkflowGraph,
    context_builder: graph_nodes.ContextBuilder | None,
) -> None:
    _add_node(
        graph,
        graph_constants.GraphNode.BUILD_CONTEXT,
        graph_nodes.create_build_context_node(context_builder),
    )
    _add_node(
        graph,
        graph_constants.GraphNode.RENDER_PROMPT,
        graph_nodes.create_render_prompt_node(),
    )


def _add_execution_nodes(
    graph: WorkflowGraph,
    executor: execution_base.Executor | None,
    validators: list[validation_utils.Validator] | None,
) -> None:
    _add_node(
        graph,
        graph_constants.GraphNode.EXECUTE,
        graph_nodes.create_execution_node(executor),
    )
    _add_node(
        graph,
        graph_constants.GraphNode.REVIEW,
        graph_nodes.create_review_node(validators),
    )


def _add_node(
    graph: WorkflowGraph,
    name: graph_constants.GraphNode,
    node: graph_nodes.ContextBuilder,
) -> None:
    graph.add_node(name.value, cast(Any, node))


def _connect_linear(graph: WorkflowGraph, endpoints: Sequence[GraphEndpoint]) -> None:
    for start_endpoint, end_endpoint in pairwise(endpoints):
        _connect(graph, start_endpoint, end_endpoint)


def _connect(
    graph: WorkflowGraph,
    start_endpoint: GraphEndpoint,
    end_endpoint: GraphEndpoint,
) -> None:
    graph.add_edge(_endpoint_name(start_endpoint), _endpoint_name(end_endpoint))


def _endpoint_name(endpoint: GraphEndpoint) -> str:
    if isinstance(endpoint, graph_constants.GraphNode):
        return endpoint.value

    return endpoint


def _select_executor(
    executor: execution_base.Executor | None,
    backend: execution_base.Executor | None,
) -> execution_base.Executor | None:
    if executor is not None and backend is not None:
        raise ValueError("Pass either executor or backend, not both.")
    return executor if executor is not None else backend
