import pathlib
import subprocess
import sys
from typing import cast

import pytest

import langgraph_codex.utils.subprocess
import langgraph_codex.utils.workspace


def test_resolve_workspace_path_defaults_to_current_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert langgraph_codex.utils.workspace.resolve_workspace_path(None) == tmp_path.resolve()


def test_resolve_workspace_path_expands_and_resolves_user_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    home = tmp_path / "home"
    workspace = home / "project"
    workspace.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))

    assert langgraph_codex.utils.workspace.resolve_workspace_path("~/project") == workspace


def test_validate_workspace_path_accepts_existing_directory(tmp_path: pathlib.Path) -> None:
    assert langgraph_codex.utils.workspace.validate_workspace_path(tmp_path) == tmp_path.resolve()


def test_validate_workspace_path_rejects_missing_path(tmp_path: pathlib.Path) -> None:
    with pytest.raises(FileNotFoundError, match="Workspace path does not exist"):
        langgraph_codex.utils.workspace.validate_workspace_path(tmp_path / "missing")


def test_validate_workspace_path_rejects_file(tmp_path: pathlib.Path) -> None:
    file_path = tmp_path / "workspace.txt"
    file_path.write_text("not a directory", encoding="utf-8")

    with pytest.raises(NotADirectoryError, match="Workspace path is not a directory"):
        langgraph_codex.utils.workspace.validate_workspace_path(file_path)


def test_run_command_captures_stdout_stderr_and_returncode(tmp_path: pathlib.Path) -> None:
    result = langgraph_codex.utils.subprocess.run_command(
        [
            sys.executable,
            "-c",
            "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)",
        ],
        cwd=tmp_path,
    )

    assert result.args[0] == sys.executable
    assert result.cwd == tmp_path.resolve()
    assert result.stdout == "out\n"
    assert result.stderr == "err\n"
    assert result.returncode == 3
    assert result.timed_out is False


def test_run_command_passes_input_text(tmp_path: pathlib.Path) -> None:
    result = langgraph_codex.utils.subprocess.run_command(
        [sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"],
        cwd=tmp_path,
        input_text="prompt",
    )

    assert result.stdout == "PROMPT\n"
    assert result.returncode == 0


def test_run_command_reports_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        timeout = kwargs.get("timeout")
        if timeout is None:
            raise AssertionError("timeout should be passed to subprocess.run")
        raise subprocess.TimeoutExpired(
            cmd=cast(list[str], args[0]),
            timeout=cast(int | float, timeout),
            output="partial stdout",
            stderr="partial stderr",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = langgraph_codex.utils.subprocess.run_command(
        ["slow-command"],
        cwd=tmp_path,
        timeout_seconds=4,
        input_text="input",
    )

    assert result.args == ["slow-command"]
    assert result.cwd == tmp_path.resolve()
    assert result.stdout == "partial stdout"
    assert "partial stderr" in result.stderr
    assert "Command timed out after 4 seconds." in result.stderr
    assert result.returncode == 124
    assert result.timed_out is True
