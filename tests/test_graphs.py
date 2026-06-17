import pathlib
from collections.abc import MutableMapping
from typing import Any, TypedDict, cast

import langgraph.graph
import pytest

import langgraph_codex.execution
import langgraph_codex.graph
import langgraph_codex.graph.nodes
import langgraph_codex.utils.validation


class AppState(TypedDict, total=False):
    workspace_path: pathlib.Path
    ticket: str
    codex_result: langgraph_codex.execution.ExecutionResult
    answer: str


def test_build_context_normalizes_defaults_and_copies_mutable_state(
    tmp_path: pathlib.Path,
) -> None:
    metadata = {"ticket": "A-1"}
    artifacts = {"summary": "ready"}

    result = langgraph_codex.graph.nodes.build_context(
        {
            "workspace_path": tmp_path,
            "metadata": metadata,
            "artifacts": artifacts,
        }
    )

    assert result["workspace_path"] == tmp_path.resolve()
    assert result["retry_count"] == 0
    assert result["max_retries"] == 0
    assert result["metadata"] == metadata
    assert result["metadata"] is not metadata
    assert result["artifacts"] == artifacts
    assert result["artifacts"] is not artifacts


def test_build_context_uses_current_directory_when_workspace_is_absent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = langgraph_codex.graph.nodes.build_context({})

    assert result["workspace_path"] == tmp_path.resolve()


def test_context_only_graph_renders_prompt(tmp_path: pathlib.Path) -> None:
    graph = langgraph_codex.graph.build_context_only_graph()

    result = graph.invoke(
        {
            "workspace_path": tmp_path,
            "task_title": "Context only",
            "objective": "Render prompt.",
        }
    )

    assert result["workspace_path"] == tmp_path.resolve()
    assert result["rendered_prompt"].startswith("# Context only")
    assert "## Objective" in result["rendered_prompt"]


def test_context_builder_receives_normalized_state_and_can_add_context(
    tmp_path: pathlib.Path,
) -> None:
    seen_workspace_paths: list[pathlib.Path] = []

    def context_builder(
        state: langgraph_codex.graph.state.WorkflowState,
    ) -> dict[str, Any]:
        workspace_path = cast(pathlib.Path, state.get("workspace_path"))
        seen_workspace_paths.append(workspace_path)
        return {
            "context": {"Workspace": workspace_path.name},
            "metadata": {"source": "test"},
        }

    graph = langgraph_codex.graph.build_context_only_graph(context_builder=context_builder)

    result = graph.invoke(
        {
            "workspace_path": str(tmp_path),
            "task_title": "Context builder",
            "objective": "Use normalized state.",
        }
    )

    assert seen_workspace_paths == [tmp_path.resolve()]
    assert result["metadata"] == {"source": "test"}
    assert "### Workspace" in result["rendered_prompt"]
    assert tmp_path.name in result["rendered_prompt"]


def test_execution_graph_runs_fake_executor(tmp_path: pathlib.Path) -> None:
    executor = langgraph_codex.execution.FakeExecutor(stdout="completed")
    graph = langgraph_codex.graph.build_execution_graph(executor=executor)

    result = graph.invoke(
        {
            "workspace_path": tmp_path,
            "task_title": "Basic graph",
            "objective": "Run executor.",
        }
    )

    assert result["execution_result"].stdout == "completed"
    assert result["validation_result"].passed is True
    assert len(executor.requests) == 1
    assert executor.requests[0].prompt.startswith("# Basic graph")


def test_execution_graph_uses_validators(tmp_path: pathlib.Path) -> None:
    executor = langgraph_codex.execution.FakeExecutor(stdout="completed")
    validator = langgraph_codex.utils.validation.require_artifacts(["summary"])
    graph = langgraph_codex.graph.build_execution_graph(
        executor=executor,
        validators=[validator],
    )

    result = graph.invoke(
        {
            "workspace_path": tmp_path,
            "task_title": "Validated graph",
            "objective": "Require artifact.",
        }
    )

    assert result["validation_result"].passed is False
    assert result["review_result"]["message"] == "Missing required artifacts: summary"


def test_execution_node_prefers_execution_options_over_backend_options(
    tmp_path: pathlib.Path,
) -> None:
    executor = langgraph_codex.execution.FakeExecutor(stdout="done")
    node = langgraph_codex.graph.nodes.create_execution_node(executor)

    result = node(
        {
            "workspace_path": tmp_path,
            "rendered_prompt": "Run work.",
            "metadata": {"request_id": "R-1"},
            "execution_options": {"timeout_seconds": 5},
            "backend_options": {"timeout_seconds": 99},
        }
    )

    request = executor.requests[0]
    assert result["execution_result"] is result["backend_result"]
    assert request.workspace_path == tmp_path.resolve()
    assert request.prompt == "Run work."
    assert request.metadata == {"request_id": "R-1"}
    assert request.options == {"timeout_seconds": 5}


def test_execution_node_uses_backend_options_as_compatibility_fallback(
    tmp_path: pathlib.Path,
) -> None:
    executor = langgraph_codex.execution.FakeExecutor(stdout="done")
    node = langgraph_codex.graph.nodes.create_execution_node(executor)

    node({"workspace_path": tmp_path, "backend_options": {"timeout_seconds": 15}})

    assert executor.requests[0].options == {"timeout_seconds": 15}


def test_retry_graph_retries_executor_failure(tmp_path: pathlib.Path) -> None:
    executor = langgraph_codex.execution.FakeExecutor(returncode=1, stderr="failed")
    graph = langgraph_codex.graph.build_retry_graph(executor=executor)

    result = graph.invoke(
        {
            "workspace_path": tmp_path,
            "task_title": "Retry graph",
            "objective": "Retry failed executor.",
            "max_retries": 2,
        }
    )

    assert len(executor.requests) == 3
    assert result["retry_count"] == 2
    assert result["validation_result"].passed is False


def test_retry_graph_stops_without_retry_when_max_retries_is_zero(
    tmp_path: pathlib.Path,
) -> None:
    executor = langgraph_codex.execution.FakeExecutor(returncode=1, stderr="failed")
    graph = langgraph_codex.graph.build_retry_graph(executor=executor)

    result = graph.invoke(
        {
            "workspace_path": tmp_path,
            "task_title": "No retry",
            "objective": "Stop immediately.",
            "max_retries": 0,
        }
    )

    assert len(executor.requests) == 1
    assert result["retry_count"] == 0
    assert result["validation_result"].passed is False


def test_retry_graph_stops_after_success(tmp_path: pathlib.Path) -> None:
    attempts = {"count": 0}

    def responder(
        _request: langgraph_codex.execution.ExecutionRequest,
    ) -> langgraph_codex.execution.ExecutionResult:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return langgraph_codex.execution.ExecutionResult(
                stdout="",
                stderr="try again",
                returncode=1,
            )

        return langgraph_codex.execution.ExecutionResult(stdout="ok", stderr="", returncode=0)

    executor = langgraph_codex.execution.FakeExecutor(responder=responder)
    graph = langgraph_codex.graph.build_retry_graph(executor=executor)

    result = graph.invoke(
        {
            "workspace_path": tmp_path,
            "task_title": "Recover",
            "objective": "Succeed after retry.",
            "max_retries": 2,
        }
    )

    assert len(executor.requests) == 2
    assert result["retry_count"] == 1
    assert result["validation_result"].passed is True


def test_retry_graph_strategy_can_update_prompt_context_after_validation_failure(
    tmp_path: pathlib.Path,
) -> None:
    retry_instruction = "Use the validation feedback before retrying."

    def validator(
        state: MutableMapping[str, Any],
    ) -> langgraph_codex.utils.validation.ValidationResult:
        rendered_prompt = str(state.get("rendered_prompt", ""))
        if retry_instruction not in rendered_prompt:
            return langgraph_codex.utils.validation.failing_validation(
                message="Missing retry guidance.",
                details={"instruction": retry_instruction},
            )

        return langgraph_codex.utils.validation.passing_validation()

    def retry_strategy(
        state: langgraph_codex.graph.WorkflowState,
    ) -> dict[str, Any]:
        validation_result = state.get("validation_result")
        assert validation_result is not None
        current_instructions = list(state.get("additional_instructions", []) or [])
        return {
            "additional_instructions": [
                *current_instructions,
                f"{validation_result.message} {retry_instruction}",
            ]
        }

    executor = langgraph_codex.execution.FakeExecutor(stdout="ok")
    graph = langgraph_codex.graph.build_retry_graph(
        executor=executor,
        validators=[validator],
        retry_strategy=retry_strategy,
    )

    result = graph.invoke(
        {
            "workspace_path": tmp_path,
            "task_title": "Retry strategy",
            "objective": "Retry with deterministic feedback.",
            "max_retries": 2,
        }
    )

    assert len(executor.requests) == 2
    assert retry_instruction not in executor.requests[0].prompt
    assert "Missing retry guidance." in executor.requests[1].prompt
    assert retry_instruction in executor.requests[1].prompt
    assert result["retry_count"] == 1
    assert result["validation_result"].passed is True


@pytest.mark.parametrize(
    ("validation_result", "retry_count", "max_retries", "expected_route"),
    [
        (langgraph_codex.utils.validation.ValidationResult(passed=True), 0, 2, "success"),
        (langgraph_codex.utils.validation.ValidationResult(passed=False), 0, 2, "retry"),
        (langgraph_codex.utils.validation.ValidationResult(passed=False), 2, 2, "fail"),
        (None, 0, 1, "retry"),
        (None, 1, 1, "fail"),
    ],
)
def test_route_after_review_handles_success_retry_and_failure_boundaries(
    validation_result: langgraph_codex.utils.validation.ValidationResult | None,
    retry_count: int,
    max_retries: int,
    expected_route: str,
) -> None:
    state: langgraph_codex.graph.state.WorkflowState = {
        "retry_count": retry_count,
        "max_retries": max_retries,
    }
    if validation_result is not None:
        state["validation_result"] = validation_result

    assert langgraph_codex.graph.nodes.route_after_review(state) == expected_route


def test_route_after_review_returns_route_enum() -> None:
    state: langgraph_codex.graph.state.WorkflowState = {
        "validation_result": langgraph_codex.utils.validation.ValidationResult(passed=True),
    }

    assert (
        langgraph_codex.graph.nodes.route_after_review(state)
        is langgraph_codex.graph.ReviewRoute.SUCCESS
    )


def test_codex_node_can_replace_node_in_existing_langgraph(tmp_path: pathlib.Path) -> None:
    executor = langgraph_codex.execution.FakeExecutor(stdout="priority=medium")

    def load_ticket(_state: AppState) -> dict[str, str]:
        return {"ticket": "Billing export is missing purchase order references."}

    def finalize(state: AppState) -> dict[str, str]:
        codex_result = cast(
            langgraph_codex.execution.ExecutionResult,
            state.get("codex_result"),
        )
        return {"answer": codex_result.stdout}

    graph: Any = langgraph.graph.StateGraph(AppState)
    graph.add_node("load_ticket", load_ticket)
    graph.add_node(
        "codex_triage",
        langgraph_codex.graph.create_codex_node(
            executor=executor,
            prompt_builder=lambda state: f"Triage this support ticket: {state['ticket']}",
            workspace_path=lambda state: cast(pathlib.Path, state.get("workspace_path")),
        ),
    )
    graph.add_node("finalize", finalize)
    graph.add_edge(langgraph.graph.START, "load_ticket")
    graph.add_edge("load_ticket", "codex_triage")
    graph.add_edge("codex_triage", "finalize")
    graph.add_edge("finalize", langgraph.graph.END)

    result = graph.compile().invoke({"workspace_path": tmp_path})

    assert result["answer"] == "priority=medium"
    assert executor.requests[0].workspace_path == tmp_path.resolve()
    assert executor.requests[0].prompt == (
        "Triage this support ticket: Billing export is missing purchase order references."
    )


def test_codex_node_uses_state_workspace_when_no_workspace_override(
    tmp_path: pathlib.Path,
) -> None:
    executor = langgraph_codex.execution.FakeExecutor(stdout="done")
    node = langgraph_codex.graph.create_codex_node(
        executor=executor,
        prompt_builder=lambda _state: "Use default workspace.",
    )

    node({"workspace_path": str(tmp_path)})

    assert executor.requests[0].workspace_path == tmp_path.resolve()


def test_codex_node_can_map_result_to_application_state(tmp_path: pathlib.Path) -> None:
    executor = langgraph_codex.execution.FakeExecutor(stdout="accepted")
    node = langgraph_codex.graph.create_codex_node(
        executor=executor,
        prompt_builder=lambda _state: "Review the proposed change.",
        workspace_path=tmp_path,
        result_mapper=lambda result: {"answer": result.stdout.upper()},
    )

    result = node({})

    assert result == {"answer": "ACCEPTED"}


def test_codex_node_accepts_prompt_specs_and_merges_node_options(
    tmp_path: pathlib.Path,
) -> None:
    executor = langgraph_codex.execution.FakeExecutor(stdout="done")
    node = langgraph_codex.graph.create_codex_node(
        executor=executor,
        prompt_builder=lambda _state: langgraph_codex.PromptSpec(
            title="Advanced node",
            objective="Render structured prompt.",
        ),
        workspace_path=tmp_path,
        metadata={"workflow": "audit"},
        metadata_builder=lambda state: {"ticket": state["ticket"]},
        options={langgraph_codex.ExecutionOption.TIMEOUT_SECONDS.value: 30},
        options_builder=lambda _state: {langgraph_codex.ExecutionOption.MODEL.value: "gpt-5.1"},
    )

    result = node({"ticket": "A-42"})

    assert result["codex_result"].stdout == "done"
    assert executor.requests[0].prompt == (
        "# Advanced node\n\n## Objective\n\nRender structured prompt."
    )
    assert executor.requests[0].metadata == {"workflow": "audit", "ticket": "A-42"}
    assert executor.requests[0].options == {"timeout_seconds": 30, "model": "gpt-5.1"}


def test_codex_node_passes_metadata_options_and_custom_result_key(
    tmp_path: pathlib.Path,
) -> None:
    executor = langgraph_codex.execution.FakeExecutor(stdout="done")
    node = langgraph_codex.graph.create_codex_node(
        executor=executor,
        prompt_builder=lambda state: f"Process {state['item_id']}",
        workspace_path=tmp_path,
        result_key="agent_result",
        metadata_builder=lambda state: {"item_id": state["item_id"]},
        options_builder=lambda _state: {"timeout_seconds": 15},
    )

    result = node({"item_id": "A-42"})

    assert result["agent_result"].stdout == "done"
    assert executor.requests[0].metadata == {"item_id": "A-42"}
    assert executor.requests[0].options == {"timeout_seconds": 15}
    assert executor.requests[0].prompt == "Process A-42"


def test_review_node_reports_executor_failure_without_running_validators() -> None:
    calls = 0

    def validator(
        _state: MutableMapping[str, Any],
    ) -> langgraph_codex.utils.validation.ValidationResult:
        nonlocal calls
        calls += 1
        return langgraph_codex.utils.validation.ValidationResult(passed=True)

    node = langgraph_codex.graph.nodes.create_review_node(validators=[validator])

    result = node(
        {
            "execution_result": langgraph_codex.execution.ExecutionResult(
                stdout="",
                stderr="failed",
                returncode=1,
            )
        }
    )

    assert calls == 0
    assert result["validation_result"].passed is False
    assert result["review_result"]["details"]["stderr"] == "failed"


def test_builders_reject_executor_and_backend_together() -> None:
    executor = langgraph_codex.execution.FakeExecutor()
    backend = langgraph_codex.execution.FakeExecutor()

    with pytest.raises(ValueError, match="Pass either executor or backend"):
        langgraph_codex.graph.build_execution_graph(executor=executor, backend=backend)

    with pytest.raises(ValueError, match="Pass either executor or backend"):
        langgraph_codex.graph.build_retry_graph(executor=executor, backend=backend)


def test_backend_graph_aliases_delegate_to_execution_builders(tmp_path: pathlib.Path) -> None:
    backend = langgraph_codex.execution.FakeExecutor(stdout="done")
    graph = langgraph_codex.graph.build_basic_backend_graph(backend=backend)

    result = graph.invoke(
        {
            "workspace_path": tmp_path,
            "task_title": "Backend alias",
            "objective": "Run backend graph.",
        }
    )

    assert result["backend_result"].stdout == "done"
    assert backend.requests[0].prompt.startswith("# Backend alias")


def test_serialize_state_value_handles_nested_dataclasses_and_paths(
    tmp_path: pathlib.Path,
) -> None:
    payload = {
        "request": langgraph_codex.execution.ExecutionRequest(
            workspace_path=tmp_path,
            prompt="Do work.",
            metadata={"path": tmp_path / "artifact.txt"},
        ),
        "items": [tmp_path, {"ok": True}],
    }

    serialized = langgraph_codex.graph.nodes.serialize_state_value(payload)

    assert serialized == {
        "request": {
            "workspace_path": str(tmp_path),
            "prompt": "Do work.",
            "metadata": {"path": str(tmp_path / "artifact.txt")},
            "options": {},
        },
        "items": [str(tmp_path), {"ok": True}],
    }
