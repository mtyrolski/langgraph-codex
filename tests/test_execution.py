import pathlib
from collections.abc import Sequence
from typing import Any

import pytest

import langgraph_codex
import langgraph_codex.backends
import langgraph_codex.execution
import langgraph_codex.utils.subprocess


def test_execution_result_succeeded_reflects_return_code() -> None:
    assert langgraph_codex.execution.ExecutionResult(stdout="", stderr="", returncode=0).succeeded
    assert not langgraph_codex.execution.ExecutionResult(
        stdout="",
        stderr="failed",
        returncode=2,
    ).succeeded


def test_backend_aliases_match_execution_exports() -> None:
    assert langgraph_codex.BackendRequest is langgraph_codex.execution.ExecutionRequest
    assert langgraph_codex.BackendResult is langgraph_codex.execution.ExecutionResult
    assert langgraph_codex.ExecutionBackend is langgraph_codex.execution.Executor
    assert langgraph_codex.CodexBackend is langgraph_codex.execution.CodexExecutor
    assert langgraph_codex.CodexExecBackend is langgraph_codex.execution.CodexExecutor
    assert langgraph_codex.FakeBackend is langgraph_codex.execution.FakeExecutor
    assert langgraph_codex.backends.CodexExecutor is langgraph_codex.execution.CodexExecutor


def test_fake_executor_returns_configured_result_and_captures_request(
    tmp_path: pathlib.Path,
) -> None:
    executor = langgraph_codex.execution.FakeExecutor(
        stdout="done",
        stderr="",
        returncode=0,
        structured_outputs={"value": 1},
    )
    request = langgraph_codex.execution.ExecutionRequest(
        workspace_path=tmp_path,
        prompt="Perform work.",
    )

    result = executor.execute(request)

    assert result.succeeded is True
    assert result.stdout == "done"
    assert result.structured_outputs == {"value": 1}
    assert executor.requests == [request]


def test_fake_executor_copies_structured_outputs_per_execution(tmp_path: pathlib.Path) -> None:
    executor = langgraph_codex.execution.FakeExecutor(
        structured_outputs={"items": ["initial"]},
        response={"raw": True},
    )
    request = langgraph_codex.execution.ExecutionRequest(
        workspace_path=tmp_path,
        prompt="Perform work.",
    )

    first_result = executor.execute(request)
    first_result.structured_outputs["items"] = ["mutated"]
    second_result = executor.execute(request)

    assert second_result.structured_outputs == {"items": ["initial"]}
    assert second_result.raw_response == {"raw": True}
    assert executor.requests == [request, request]


def test_fake_executor_can_use_responder(tmp_path: pathlib.Path) -> None:
    def responder(
        request: langgraph_codex.execution.ExecutionRequest,
    ) -> langgraph_codex.execution.ExecutionResult:
        return langgraph_codex.execution.ExecutionResult(
            stdout=f"prompt={request.prompt}",
            stderr="",
            returncode=0,
        )

    executor = langgraph_codex.execution.FakeExecutor(responder=responder)
    result = executor.execute(
        langgraph_codex.execution.ExecutionRequest(
            workspace_path=tmp_path,
            prompt="abc",
        )
    )

    assert result.stdout == "prompt=abc"


def test_codex_executor_builds_safe_exec_command(tmp_path: pathlib.Path) -> None:
    executor = langgraph_codex.execution.CodexExecutor(
        codex_bin="codex",
        model="gpt-5.5-mini",
        sandbox="workspace-write",
        approval_policy="never",
        extra_args=["--json"],
    )

    command = executor.build_command(tmp_path)

    assert command == [
        "codex",
        "exec",
        "-m",
        "gpt-5.5-mini",
        "-s",
        "workspace-write",
        "-C",
        str(tmp_path.resolve()),
        "-c",
        "approval_policy='never'",
        "--skip-git-repo-check",
        "--json",
        "-",
    ]


def test_codex_executor_supports_enums_and_request_option_overrides(
    tmp_path: pathlib.Path,
) -> None:
    executor = langgraph_codex.execution.CodexExecutor(
        sandbox=langgraph_codex.CodexSandbox.READ_ONLY,
        approval_policy=langgraph_codex.CodexApprovalPolicy.UNTRUSTED,
        profile="base",
        additional_writable_roots=[tmp_path / "base-extra"],
        config_overrides={"reasoning.effort": "low"},
        extra_args=["--json"],
    )

    command = executor.build_command(
        tmp_path,
        options={
            langgraph_codex.ExecutionOption.MODEL.value: "gpt-5.1",
            langgraph_codex.ExecutionOption.SANDBOX.value: (
                langgraph_codex.CodexSandbox.WORKSPACE_WRITE
            ),
            langgraph_codex.ExecutionOption.APPROVAL_POLICY.value: (
                langgraph_codex.CodexApprovalPolicy.ON_REQUEST
            ),
            langgraph_codex.ExecutionOption.PROFILE.value: "ci",
            langgraph_codex.ExecutionOption.ADDITIONAL_WRITABLE_ROOTS.value: [
                tmp_path / "request-extra"
            ],
            langgraph_codex.ExecutionOption.CONFIG_OVERRIDES.value: {
                "model_reasoning_summary": "auto",
                "strict_config": True,
            },
            langgraph_codex.ExecutionOption.EXTRA_ARGS.value: [
                "--output-last-message",
                str(tmp_path / "last-message.txt"),
            ],
            langgraph_codex.ExecutionOption.SKIP_GIT_REPO_CHECK.value: False,
        },
    )

    assert command[:4] == ["codex", "exec", "-m", "gpt-5.1"]
    assert command[4:6] == ["-p", "ci"]
    assert "read-only" not in command
    assert "workspace-write" in command
    assert "approval_policy='on-request'" in command
    assert "--add-dir" in command
    assert str((tmp_path / "base-extra").resolve()) in command
    assert str((tmp_path / "request-extra").resolve()) in command
    assert "model_reasoning_summary='auto'" in command
    assert "reasoning.effort='low'" in command
    assert "strict_config=true" in command
    assert "--skip-git-repo-check" not in command
    assert command[-4:] == [
        "--json",
        "--output-last-message",
        str(tmp_path / "last-message.txt"),
        "-",
    ]


def test_codex_executor_supports_structured_output_options(tmp_path: pathlib.Path) -> None:
    schema_path = tmp_path / "schema.json"
    last_message_path = tmp_path / "last-message.json"
    executor = langgraph_codex.execution.CodexExecutor(
        output_schema_path=schema_path,
        output_last_message_path="last-message.json",
        json_events=True,
    )

    command = executor.build_command(tmp_path)

    assert "--output-schema" in command
    assert str(schema_path.resolve()) in command
    assert "--output-last-message" in command
    assert str(last_message_path.resolve()) in command
    assert "--json" in command


def test_codex_executor_does_not_duplicate_json_flag(tmp_path: pathlib.Path) -> None:
    executor = langgraph_codex.execution.CodexExecutor(json_events=True, extra_args=["--json"])

    command = executor.build_command(tmp_path)

    assert command.count("--json") == 1


def test_codex_executor_captures_structured_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    last_message_path = tmp_path / "last-message.json"
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
        last_message_path.write_text('{"status": "accepted", "score": 0.97}', encoding="utf-8")
        return langgraph_codex.utils.subprocess.CommandResult(
            args=args,
            cwd=pathlib.Path(cwd),
            stdout='{"type": "started"}\nnot-json\n{"type": "completed"}\n',
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(
        langgraph_codex.utils.subprocess,
        "run_command",
        fake_run_command,
    )
    executor = langgraph_codex.execution.CodexExecutor(
        output_last_message_path="last-message.json",
        json_events=True,
    )
    request = langgraph_codex.execution.ExecutionRequest(
        workspace_path=tmp_path,
        prompt="Return structured status.",
    )

    result = executor.execute(request)

    assert calls[0]["args"][-1] == "-"
    assert result.structured_outputs["last_message_path"] == str(last_message_path.resolve())
    assert result.structured_outputs["last_message"] == '{"status": "accepted", "score": 0.97}'
    assert result.structured_outputs["last_message_json"] == {
        "status": "accepted",
        "score": 0.97,
    }
    assert result.structured_outputs["json_events"] == [
        {"type": "started"},
        "not-json",
        {"type": "completed"},
    ]


def test_codex_executor_can_summarize_json_events_without_storing_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    def fake_run_command(
        args: list[str],
        cwd: str | pathlib.Path,
        timeout_seconds: int | float | None = None,
        input_text: str | None = None,
    ) -> langgraph_codex.utils.subprocess.CommandResult:
        del timeout_seconds, input_text
        return langgraph_codex.utils.subprocess.CommandResult(
            args=args,
            cwd=pathlib.Path(cwd),
            stdout=(
                '{"type": "started"}\n{"type": "token_count", "total_token_count": 42}\nraw line\n'
            ),
            stderr="",
            returncode=0,
        )

    def summarize(events: Sequence[Any]) -> dict[str, Any]:
        return {
            "event_count": len(events),
            "last_event": events[-1],
        }

    monkeypatch.setattr(
        langgraph_codex.utils.subprocess,
        "run_command",
        fake_run_command,
    )
    executor = langgraph_codex.execution.CodexExecutor(json_event_summarizers=[summarize])
    request = langgraph_codex.execution.ExecutionRequest(
        workspace_path=tmp_path,
        prompt="Return events.",
    )

    result = executor.execute(request)

    assert "json_events" not in result.structured_outputs
    assert result.structured_outputs["json_event_summary"] == {
        "event_count": 3,
        "last_event": "raw line",
    }


def test_codex_executor_accepts_request_json_event_summarizers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    def fake_run_command(
        args: list[str],
        cwd: str | pathlib.Path,
        timeout_seconds: int | float | None = None,
        input_text: str | None = None,
    ) -> langgraph_codex.utils.subprocess.CommandResult:
        del timeout_seconds, input_text
        return langgraph_codex.utils.subprocess.CommandResult(
            args=args,
            cwd=pathlib.Path(cwd),
            stdout='{"type": "completed"}\n',
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(
        langgraph_codex.utils.subprocess,
        "run_command",
        fake_run_command,
    )
    executor = langgraph_codex.execution.CodexExecutor()
    request = langgraph_codex.execution.ExecutionRequest(
        workspace_path=tmp_path,
        prompt="Return events.",
        options={
            langgraph_codex.ExecutionOption.JSON_EVENT_SUMMARIZERS.value: [
                lambda events: {"first_event": events[0]},
            ],
        },
    )

    result = executor.execute(request)

    assert result.structured_outputs["json_event_summary"] == {"first_event": {"type": "completed"}}


def test_codex_executor_rejects_dangerous_config_overrides(tmp_path: pathlib.Path) -> None:
    executor = langgraph_codex.execution.CodexExecutor(
        config_overrides={"dangerously_bypass_approvals_and_sandbox": True}
    )

    with pytest.raises(ValueError, match="Refusing dangerous Codex config override"):
        executor.build_command(tmp_path)


def test_codex_executor_can_use_cli_default_model(tmp_path: pathlib.Path) -> None:
    executor = langgraph_codex.execution.CodexExecutor(model=None)

    command = executor.build_command(tmp_path)

    assert "-m" not in command
    assert "--skip-git-repo-check" in command
    assert command[-1] == "-"


def test_codex_executor_can_keep_git_repo_check(tmp_path: pathlib.Path) -> None:
    executor = langgraph_codex.execution.CodexExecutor(skip_git_repo_check=False)

    command = executor.build_command(tmp_path)

    assert "--skip-git-repo-check" not in command


@pytest.mark.parametrize(
    "dangerous_flag",
    [
        "--dangerously-bypass-approvals-and-sandbox",
        "--dangerously-bypass-approvals-and-sandbox=true",
        "--dangerously-bypass-hook-trust",
        "--dangerously-bypass-hook-trust=true",
    ],
)
def test_codex_executor_rejects_dangerous_flags(
    tmp_path: pathlib.Path,
    dangerous_flag: str,
) -> None:
    executor = langgraph_codex.execution.CodexExecutor(extra_args=[dangerous_flag])

    with pytest.raises(ValueError, match="Refusing dangerous Codex flag"):
        executor.build_command(tmp_path)


@pytest.mark.parametrize(
    ("executor", "message"),
    [
        (
            langgraph_codex.execution.CodexExecutor(codex_bin=""),
            "codex_bin must not be empty",
        ),
        (
            langgraph_codex.execution.CodexExecutor(sandbox=""),
            "sandbox must not be empty",
        ),
        (
            langgraph_codex.execution.CodexExecutor(approval_policy=""),
            "approval_policy must not be empty",
        ),
    ],
)
def test_codex_executor_rejects_empty_required_command_fields(
    tmp_path: pathlib.Path,
    executor: langgraph_codex.execution.CodexExecutor,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        executor.build_command(tmp_path)


def test_codex_executor_execute_passes_prompt_on_stdin(
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

    monkeypatch.setattr(
        langgraph_codex.utils.subprocess,
        "run_command",
        fake_run_command,
    )
    executor = langgraph_codex.execution.CodexExecutor(timeout_seconds=30)
    request = langgraph_codex.execution.ExecutionRequest(
        workspace_path=tmp_path,
        prompt="Do work.",
        options={"timeout_seconds": 10},
    )

    result = executor.execute(request)

    assert result.stdout == "ok"
    assert isinstance(result.raw_response, langgraph_codex.utils.subprocess.CommandResult)
    assert calls[0]["input_text"] == "Do work."
    assert calls[0]["timeout_seconds"] == 10
    assert calls[0]["args"][-1] == "-"
    assert result.structured_outputs["cwd"] == str(tmp_path.resolve())
    assert result.structured_outputs["timed_out"] is False


def test_codex_executor_rejects_missing_workspace_before_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    def unexpected_run_command(
        _args: list[str],
        cwd: str | pathlib.Path,
        timeout_seconds: int | float | None = None,
        input_text: str | None = None,
    ) -> langgraph_codex.utils.subprocess.CommandResult:
        raise AssertionError("run_command should not be called")

    monkeypatch.setattr(
        langgraph_codex.utils.subprocess,
        "run_command",
        unexpected_run_command,
    )
    request = langgraph_codex.execution.ExecutionRequest(
        workspace_path=tmp_path / "missing",
        prompt="Do work.",
    )

    with pytest.raises(FileNotFoundError, match="Workspace path does not exist"):
        langgraph_codex.execution.CodexExecutor().execute(request)


@pytest.mark.parametrize(
    ("timeout", "error_type", "message"),
    [
        ("slow", TypeError, "timeout_seconds must be int or float"),
        (0, ValueError, "timeout_seconds must be positive"),
    ],
)
def test_codex_executor_rejects_invalid_request_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    timeout: object,
    error_type: type[Exception],
    message: str,
) -> None:
    def unexpected_run_command(
        _args: list[str],
        _cwd: str | pathlib.Path,
        timeout_seconds: int | float | None = None,
        input_text: str | None = None,
    ) -> langgraph_codex.utils.subprocess.CommandResult:
        raise AssertionError("run_command should not be called")

    monkeypatch.setattr(
        langgraph_codex.utils.subprocess,
        "run_command",
        unexpected_run_command,
    )
    executor = langgraph_codex.execution.CodexExecutor()
    request = langgraph_codex.execution.ExecutionRequest(
        workspace_path=tmp_path,
        prompt="Do work.",
        options={"timeout_seconds": timeout},
    )

    with pytest.raises(error_type, match=message):
        executor.execute(request)
