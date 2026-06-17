import hashlib
import os
import pathlib
import shutil
from collections.abc import MutableMapping
from typing import Any

import pytest

import langgraph_codex.execution
import langgraph_codex.graph
import langgraph_codex.utils.open_ai_env as open_ai_env
import langgraph_codex.utils.validation

RUN_REAL_CODEX_ENV = "LANGGRAPH_CODEX_RUN_REAL_CODEX"


def load_local_env() -> open_ai_env.OpenAIEnvironment:
    return open_ai_env.configure_open_ai_environment(env_path=pathlib.Path.cwd() / ".env")


def require_real_codex() -> None:
    environment = load_local_env()
    if not _env_enabled(RUN_REAL_CODEX_ENV):
        pytest.skip(f"Set {RUN_REAL_CODEX_ENV}=1 to run real Codex integration tests.")

    if shutil.which("codex") is None:
        pytest.skip("Codex CLI is not installed.")
    if not environment.authorized:
        pytest.skip(f"Missing {open_ai_env.OPEN_AI_SECRET_KEY} or OPENAI_API_KEY.")


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_codex_executor(timeout_seconds: int = 180) -> langgraph_codex.execution.CodexExecutor:
    environment = load_local_env()
    if environment.model:
        return langgraph_codex.execution.CodexExecutor(
            model=environment.model,
            timeout_seconds=timeout_seconds,
        )

    return langgraph_codex.execution.CodexExecutor(
        model=None,
        timeout_seconds=timeout_seconds,
    )


def _env_enabled(name: str) -> bool:
    return os.environ.get(name) == "1"


def executor_stdout_contains(marker: str) -> langgraph_codex.utils.validation.Validator:
    def validate(
        state: MutableMapping[str, Any],
    ) -> langgraph_codex.utils.validation.ValidationResult:
        execution_result = state["execution_result"]
        if marker in execution_result.stdout:
            return langgraph_codex.utils.validation.passing_validation(
                message=f"Execution stdout contains {marker}."
            )

        return langgraph_codex.utils.validation.failing_validation(
            message=f"Execution stdout is missing {marker}.",
            details={"stdout": execution_result.stdout},
        )

    return validate


def test_real_codex_executor_smoke(tmp_path: pathlib.Path) -> None:
    require_real_codex()
    marker = "LANGGRAPH_CODEX_REAL_EXECUTOR_OK"
    executor = create_codex_executor(timeout_seconds=180)
    graph = langgraph_codex.graph.build_execution_graph(
        executor=executor,
        validators=[executor_stdout_contains(marker)],
    )

    result = graph.invoke(
        {
            "workspace_path": tmp_path,
            "task_title": "Real Codex stdout smoke test",
            "objective": f"Reply with exactly one sentence ending in {marker}.",
            "constraints": [
                "Do not create, modify, or delete files.",
                "Do not print secrets.",
            ],
        }
    )

    execution_result = result["execution_result"]
    assert execution_result.succeeded, execution_result.stderr
    assert result["validation_result"].passed
    assert not list(tmp_path.iterdir())


def test_real_codex_creates_validated_artifact(tmp_path: pathlib.Path) -> None:
    require_real_codex()
    source_path = tmp_path / "source_note.txt"
    output_path = tmp_path / "summary.md"
    source_path.write_text(
        "First source line about deterministic context.\n"
        "Second source line about executor-driven Codex work.\n",
        encoding="utf-8",
    )
    source_hash = sha256_file(source_path)

    def validate_summary(
        _state: MutableMapping[str, Any],
    ) -> langgraph_codex.utils.validation.ValidationResult:
        if not output_path.exists():
            return langgraph_codex.utils.validation.failing_validation(
                message="summary.md was not created."
            )
        if sha256_file(source_path) != source_hash:
            return langgraph_codex.utils.validation.failing_validation(
                message="source_note.txt was modified."
            )
        summary_text = output_path.read_text(encoding="utf-8")
        if "source_lines=2" not in summary_text:
            return langgraph_codex.utils.validation.failing_validation(
                message="summary.md is missing source_lines=2."
            )

        return langgraph_codex.utils.validation.passing_validation(
            message="summary.md exists, source is unchanged, and deterministic fact is present."
        )

    executor = create_codex_executor(timeout_seconds=180)
    graph = langgraph_codex.graph.build_execution_graph(
        executor=executor,
        validators=[validate_summary],
    )

    result = graph.invoke(
        {
            "workspace_path": tmp_path,
            "task_title": "Real Codex artifact smoke test",
            "objective": (
                "Read source_note.txt and create summary.md. Include the exact line "
                "source_lines=2 in summary.md."
            ),
            "constraints": [
                "Do not modify source_note.txt.",
                "Do not print secrets.",
            ],
        }
    )

    assert result["execution_result"].succeeded, result["execution_result"].stderr
    assert result["validation_result"].passed
