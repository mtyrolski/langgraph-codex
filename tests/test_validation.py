import pathlib
import sys
from collections.abc import MutableMapping
from typing import Any

import pytest

import langgraph_codex.execution
import langgraph_codex.utils.subprocess
import langgraph_codex.utils.validation


def test_passing_and_failing_validation_helpers_preserve_details() -> None:
    passing = langgraph_codex.utils.validation.passing_validation("ok")
    failing = langgraph_codex.utils.validation.failing_validation(
        "bad",
        details={"reason": "missing"},
    )

    assert passing.passed is True
    assert passing.message == "ok"
    assert not passing.details
    assert failing.passed is False
    assert failing.message == "bad"
    assert failing.details == {"reason": "missing"}


def test_run_validators_reports_empty_validator_list() -> None:
    result = langgraph_codex.utils.validation.run_validators({})

    assert result.passed is True
    assert result.message == "No validators configured."
    assert result.details == {"results": []}


def test_run_validators_short_circuits_on_first_failure() -> None:
    calls: list[str] = []

    def first_validator(
        _state: MutableMapping[str, Any],
    ) -> langgraph_codex.utils.validation.ValidationResult:
        calls.append("first")
        return langgraph_codex.utils.validation.failing_validation("first failed")

    def second_validator(
        _state: MutableMapping[str, Any],
    ) -> langgraph_codex.utils.validation.ValidationResult:
        calls.append("second")
        return langgraph_codex.utils.validation.passing_validation("second passed")

    result = langgraph_codex.utils.validation.run_validators(
        {},
        [first_validator, second_validator],
    )

    assert result.passed is False
    assert result.message == "first failed"
    assert calls == ["first"]
    assert len(result.details["results"]) == 1


def test_run_validators_records_each_passing_result() -> None:
    validators = [
        lambda _state: langgraph_codex.utils.validation.passing_validation("one"),
        lambda _state: langgraph_codex.utils.validation.passing_validation("two"),
    ]

    result = langgraph_codex.utils.validation.run_validators({}, validators)

    assert result.passed is True
    assert result.message == "All validators passed."
    assert [item["message"] for item in result.details["results"]] == ["one", "two"]


def test_require_artifacts_passes_when_all_keys_exist() -> None:
    validator = langgraph_codex.utils.validation.require_artifacts(["summary", "score"])

    result = validator({"artifacts": {"summary": "", "score": None}})

    assert result.passed is True


def test_require_artifacts_reports_missing_keys() -> None:
    validator = langgraph_codex.utils.validation.require_artifacts(["summary", "score"])

    result = validator({"artifacts": {"summary": "done"}})

    assert result.passed is False
    assert result.details == {"missing": ["score"]}


def test_require_files_uses_workspace_path(tmp_path: pathlib.Path) -> None:
    required_file = tmp_path / "artifact.txt"
    required_file.write_text("content", encoding="utf-8")
    validator = langgraph_codex.utils.validation.require_files(["artifact.txt"])

    result = validator({"workspace_path": tmp_path})

    assert result.passed is True


def test_require_files_reports_missing_paths(tmp_path: pathlib.Path) -> None:
    validator = langgraph_codex.utils.validation.require_files(
        ["present.txt", pathlib.Path("missing.txt")]
    )
    (tmp_path / "present.txt").write_text("content", encoding="utf-8")

    result = validator({"workspace_path": tmp_path})

    assert result.passed is False
    assert result.details == {"missing": ["missing.txt"]}


def test_json_artifact_accepts_structured_json() -> None:
    validator = langgraph_codex.utils.validation.require_json_artifact("payload")

    result = validator({"artifacts": {"payload": {"ok": True}}})

    assert result.passed is True


def test_json_artifact_accepts_string_json() -> None:
    validator = langgraph_codex.utils.validation.require_json_artifact("payload")

    result = validator({"artifacts": {"payload": '{"ok": true}'}})

    assert result.passed is True


@pytest.mark.parametrize(
    ("state", "message"),
    [
        ({"artifacts": {}}, "Missing JSON artifact: payload"),
        ({"artifacts": {"payload": "{not json}"}}, "Artifact is not valid JSON: payload"),
    ],
)
def test_json_artifact_reports_missing_or_invalid_json(
    state: dict[str, Any],
    message: str,
) -> None:
    validator = langgraph_codex.utils.validation.require_json_artifact("payload")

    result = validator(state)

    assert result.passed is False
    assert result.message == message


def test_require_structured_output_passes_when_key_exists() -> None:
    validator = langgraph_codex.utils.validation.require_structured_output("last_message_json")
    execution_result = langgraph_codex.execution.ExecutionResult(
        stdout="",
        stderr="",
        returncode=0,
        structured_outputs={"last_message_json": {"status": "accepted"}},
    )

    result = validator({"execution_result": execution_result})

    assert result.passed is True


def test_require_structured_output_reports_missing_key() -> None:
    validator = langgraph_codex.utils.validation.require_structured_output("last_message_json")
    execution_result = langgraph_codex.execution.ExecutionResult(
        stdout="",
        stderr="",
        returncode=0,
    )

    result = validator({"execution_result": execution_result})

    assert result.passed is False
    assert result.message == "Missing structured output: last_message_json"


def test_command_validator_runs_generic_command(tmp_path: pathlib.Path) -> None:
    validator = langgraph_codex.utils.validation.command_validator(
        [sys.executable, "-c", "print('ok')"],
        timeout_seconds=5,
    )

    result = validator({"workspace_path": tmp_path})

    assert result.passed is True
    assert result.details["returncode"] == 0
    assert result.details["stdout"] == "ok\n"


def test_command_validator_reports_command_failure(tmp_path: pathlib.Path) -> None:
    validator = langgraph_codex.utils.validation.command_validator(
        [sys.executable, "-c", "import sys; print('bad'); sys.exit(7)"],
        timeout_seconds=5,
    )

    result = validator({"workspace_path": tmp_path})

    assert result.passed is False
    assert "Command failed with return code 7" in result.message
    assert result.details["returncode"] == 7
    assert result.details["stdout"] == "bad\n"


def test_command_validator_passes_workspace_and_timeout_to_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run_command(
        args: list[str],
        cwd: str | pathlib.Path,
        timeout_seconds: int | float | None = None,
        input_text: str | None = None,
    ) -> langgraph_codex.utils.subprocess.CommandResult:
        calls.append(
            {
                "args": args,
                "cwd": cwd,
                "timeout_seconds": timeout_seconds,
                "input_text": input_text,
            }
        )
        return langgraph_codex.utils.subprocess.CommandResult(
            args=args,
            cwd=pathlib.Path(cwd),
            stdout="ok",
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(langgraph_codex.utils.subprocess, "run_command", fake_run_command)
    validator = langgraph_codex.utils.validation.command_validator(["tool", "arg"], 9)

    result = validator({"workspace_path": tmp_path})

    assert result.passed is True
    assert calls == [
        {
            "args": ["tool", "arg"],
            "cwd": tmp_path,
            "timeout_seconds": 9,
            "input_text": None,
        }
    ]
