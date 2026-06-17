import dataclasses
import json
import pathlib
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Final, TypeAlias, cast

import langgraph_codex.execution.base as execution_base
import langgraph_codex.options as codex_options
import langgraph_codex.utils.subprocess as subprocess_utils
import langgraph_codex.utils.workspace as workspace_utils
from langgraph_codex.types import JsonEventSummarizer, StateValue

CodexConfigValue: TypeAlias = str | int | float | bool

DANGEROUS_CODEX_FLAGS: Final[frozenset[str]] = frozenset(
    {
        "--dangerously-bypass-approvals-and-sandbox",
        "--dangerously-bypass-hook-trust",
    }
)


@dataclasses.dataclass(frozen=True)
class CodexCommandOptions:
    codex_bin: str
    model: str | None
    sandbox: str
    approval_policy: str
    extra_args: tuple[str, ...]
    skip_git_repo_check: bool
    profile: str | None
    additional_writable_roots: tuple[str | pathlib.Path, ...]
    config_overrides: tuple[tuple[str, CodexConfigValue], ...]
    output_schema_path: str | pathlib.Path | None
    output_last_message_path: str | pathlib.Path | None
    json_events: bool
    json_event_summarizers: tuple[JsonEventSummarizer, ...]


_DANGEROUS_CONFIG_KEYS: Final[frozenset[str]] = frozenset(
    {
        "dangerously_bypass_approvals_and_sandbox",
        "dangerously_bypass_hook_trust",
    }
)

_DANGEROUS_CONFIG_VALUES: Final[frozenset[CodexConfigValue]] = frozenset(
    {
        True,
        "true",
        "1",
        "yes",
    }
)

_CODEX_EXEC_SUBCOMMAND: Final[str] = "exec"
_STDIN_PROMPT_MARKER: Final[str] = "-"


@dataclasses.dataclass
class CodexExecutor(execution_base.Executor):
    codex_bin: str = codex_options.DEFAULT_CODEX_BIN
    model: str | None = codex_options.DEFAULT_CODEX_MODEL
    sandbox: str = codex_options.DEFAULT_SANDBOX
    approval_policy: str = codex_options.DEFAULT_APPROVAL_POLICY
    timeout_seconds: int = codex_options.DEFAULT_TIMEOUT_SECONDS
    extra_args: list[str] = dataclasses.field(default_factory=list)
    skip_git_repo_check: bool = True
    profile: str | None = None
    additional_writable_roots: list[str | pathlib.Path] = dataclasses.field(default_factory=list)
    config_overrides: dict[str, CodexConfigValue] = dataclasses.field(default_factory=dict)
    output_schema_path: str | pathlib.Path | None = None
    output_last_message_path: str | pathlib.Path | None = None
    json_events: bool = False
    json_event_summarizers: list[JsonEventSummarizer] = dataclasses.field(default_factory=list)

    def execute(
        self,
        request: execution_base.ExecutionRequest,
    ) -> execution_base.ExecutionResult:
        """Run Codex in the request workspace with the prompt passed on stdin."""
        workspace_path = workspace_utils.validate_workspace_path(request.workspace_path)
        command_options = self._command_options(request.options)
        self._validate_args(command_options)
        command = self._build_command(
            workspace_path=workspace_path,
            command_options=command_options,
        )
        result = subprocess_utils.run_command(
            command,
            cwd=workspace_path,
            timeout_seconds=self._timeout_from_request(request),
            input_text=request.prompt,
        )
        return execution_base.ExecutionResult(
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
            structured_outputs=_structured_outputs_from_result(
                command_options=command_options,
                workspace_path=workspace_path,
                result=result,
            ),
            raw_response=result,
        )

    def build_command(
        self,
        workspace_path: str | pathlib.Path,
        *,
        options: Mapping[str, StateValue] | None = None,
    ) -> list[str]:
        """Build the Codex CLI command without executing it."""
        command_options = self._command_options(options or {})
        self._validate_args(command_options)
        return self._build_command(workspace_path=workspace_path, command_options=command_options)

    def _build_command(
        self,
        workspace_path: str | pathlib.Path,
        command_options: CodexCommandOptions,
    ) -> list[str]:
        resolved_workspace_path = pathlib.Path(workspace_path).expanduser().resolve()
        command = [command_options.codex_bin, _CODEX_EXEC_SUBCOMMAND]
        if command_options.model:
            command.extend(["-m", command_options.model])
        if command_options.profile:
            command.extend(["-p", command_options.profile])

        command.extend(
            [
                "-s",
                command_options.sandbox,
                "-C",
                str(resolved_workspace_path),
                "-c",
                (
                    f"{codex_options.CodexConfigKey.APPROVAL_POLICY.value}="
                    f"{command_options.approval_policy!r}"
                ),
            ]
        )
        for writable_root in command_options.additional_writable_roots:
            command.extend(["--add-dir", str(pathlib.Path(writable_root).expanduser().resolve())])
        for key, value in command_options.config_overrides:
            command.extend(["-c", f"{key}={_format_config_value(value)}"])
        if command_options.skip_git_repo_check:
            command.append("--skip-git-repo-check")
        if command_options.output_schema_path is not None:
            command.extend(
                [
                    "--output-schema",
                    str(
                        _resolve_workspace_relative_path(
                            resolved_workspace_path,
                            command_options.output_schema_path,
                        )
                    ),
                ]
            )
        if command_options.output_last_message_path is not None:
            command.extend(
                [
                    "--output-last-message",
                    str(
                        _resolve_workspace_relative_path(
                            resolved_workspace_path,
                            command_options.output_last_message_path,
                        )
                    ),
                ]
            )
        if command_options.json_events and "--json" not in command_options.extra_args:
            command.append("--json")

        command.extend(command_options.extra_args)
        command.append(_STDIN_PROMPT_MARKER)
        return command

    def _timeout_from_request(
        self,
        request: execution_base.ExecutionRequest,
    ) -> int | float:
        timeout = _option_value(
            request.options,
            codex_options.ExecutionOption.TIMEOUT_SECONDS,
            self.timeout_seconds,
        )
        if not isinstance(timeout, (int, float)):
            raise TypeError(f"timeout_seconds must be int or float, got {type(timeout).__name__}")
        if timeout <= 0:
            raise ValueError(f"timeout_seconds must be positive, got {timeout}")
        return timeout

    def _command_options(self, request_options: Mapping[str, StateValue]) -> CodexCommandOptions:
        return CodexCommandOptions(
            codex_bin=self.codex_bin,
            model=_optional_string_option(
                request_options,
                codex_options.ExecutionOption.MODEL,
                self.model,
            ),
            sandbox=_string_option(
                request_options,
                codex_options.ExecutionOption.SANDBOX,
                self.sandbox,
            ),
            approval_policy=_string_option(
                request_options,
                codex_options.ExecutionOption.APPROVAL_POLICY,
                self.approval_policy,
            ),
            extra_args=(
                *tuple(self.extra_args),
                *_string_sequence_option(
                    request_options,
                    codex_options.ExecutionOption.EXTRA_ARGS,
                    (),
                ),
            ),
            skip_git_repo_check=_bool_option(
                request_options,
                codex_options.ExecutionOption.SKIP_GIT_REPO_CHECK,
                self.skip_git_repo_check,
            ),
            profile=_optional_string_option(
                request_options,
                codex_options.ExecutionOption.PROFILE,
                self.profile,
            ),
            additional_writable_roots=(
                *tuple(self.additional_writable_roots),
                *_path_sequence_option(
                    request_options,
                    codex_options.ExecutionOption.ADDITIONAL_WRITABLE_ROOTS,
                    (),
                ),
            ),
            config_overrides=_merge_config_overrides(
                self.config_overrides,
                _mapping_option(
                    request_options,
                    codex_options.ExecutionOption.CONFIG_OVERRIDES,
                    {},
                ),
            ),
            output_schema_path=_optional_path_option(
                request_options,
                codex_options.ExecutionOption.OUTPUT_SCHEMA_PATH,
                self.output_schema_path,
            ),
            output_last_message_path=_optional_path_option(
                request_options,
                codex_options.ExecutionOption.OUTPUT_LAST_MESSAGE_PATH,
                self.output_last_message_path,
            ),
            json_events=_bool_option(
                request_options,
                codex_options.ExecutionOption.JSON_EVENTS,
                self.json_events,
            ),
            json_event_summarizers=(
                *tuple(self.json_event_summarizers),
                *_summarizer_sequence_option(
                    request_options,
                    codex_options.ExecutionOption.JSON_EVENT_SUMMARIZERS,
                    (),
                ),
            ),
        )

    def _validate_args(self, command_options: CodexCommandOptions) -> None:
        if not command_options.codex_bin:
            raise ValueError("codex_bin must not be empty")
        if not command_options.sandbox:
            raise ValueError("sandbox must not be empty")
        if not command_options.approval_policy:
            raise ValueError("approval_policy must not be empty")

        for arg in command_options.extra_args:
            if _is_dangerous_codex_flag(arg):
                raise ValueError(f"Refusing dangerous Codex flag: {arg}")

        for key, value in command_options.config_overrides:
            if _is_dangerous_config_override(key, value):
                raise ValueError(f"Refusing dangerous Codex config override: {key}")


CodexBackend = CodexExecutor
CodexExecBackend = CodexExecutor


def _option_value(
    options: Mapping[str, StateValue],
    key: codex_options.ExecutionOption,
    default: StateValue,
) -> StateValue:
    return options.get(key.value, default)


def _string_option(
    options: Mapping[str, StateValue],
    key: codex_options.ExecutionOption,
    default: str,
) -> str:
    return _coerce_required_string(_option_value(options, key, default), key.value)


def _optional_string_option(
    options: Mapping[str, StateValue],
    key: codex_options.ExecutionOption,
    default: str | None,
) -> str | None:
    value = _option_value(options, key, default)
    if value is None:
        return None

    coerced_value = _coerce_required_string(value, key.value)
    return coerced_value or None


def _bool_option(
    options: Mapping[str, StateValue],
    key: codex_options.ExecutionOption,
    default: bool,
) -> bool:
    value = _option_value(options, key, default)
    if not isinstance(value, bool):
        raise TypeError(f"{key.value} must be bool, got {type(value).__name__}")

    return value


def _string_sequence_option(
    options: Mapping[str, StateValue],
    key: codex_options.ExecutionOption,
    default: Sequence[str],
) -> tuple[str, ...]:
    value = _option_value(options, key, default)
    if not _is_sequence_option(value):
        raise TypeError(f"{key.value} must be a sequence of strings")

    return tuple(_coerce_required_string(item, key.value) for item in value)


def _path_sequence_option(
    options: Mapping[str, StateValue],
    key: codex_options.ExecutionOption,
    default: Sequence[str | pathlib.Path],
) -> tuple[str | pathlib.Path, ...]:
    value = _option_value(options, key, default)
    if not _is_sequence_option(value):
        raise TypeError(f"{key.value} must be a sequence of paths")

    roots: list[str | pathlib.Path] = []
    for item in value:
        if not isinstance(item, (str, pathlib.Path)):
            raise TypeError(f"{key.value} entries must be str or pathlib.Path")
        roots.append(item)

    return tuple(roots)


def _optional_path_option(
    options: Mapping[str, StateValue],
    key: codex_options.ExecutionOption,
    default: str | pathlib.Path | None,
) -> str | pathlib.Path | None:
    value = _option_value(options, key, default)
    if value is None:
        return None
    if not isinstance(value, (str, pathlib.Path)):
        raise TypeError(f"{key.value} must be str or pathlib.Path, got {type(value).__name__}")

    return value


def _mapping_option(
    options: Mapping[str, StateValue],
    key: codex_options.ExecutionOption,
    default: Mapping[str, StateValue],
) -> Mapping[str, StateValue]:
    value = _option_value(options, key, default)
    if not isinstance(value, Mapping):
        raise TypeError(f"{key.value} must be a mapping")

    return value


def _summarizer_sequence_option(
    options: Mapping[str, StateValue],
    key: codex_options.ExecutionOption,
    default: Sequence[JsonEventSummarizer],
) -> tuple[JsonEventSummarizer, ...]:
    value = _option_value(options, key, default)
    if not _is_sequence_option(value):
        raise TypeError(f"{key.value} must be a sequence of callables")

    summarizers: list[JsonEventSummarizer] = []
    for item in value:
        if not callable(item):
            raise TypeError(f"{key.value} entries must be callable")
        summarizers.append(cast(JsonEventSummarizer, item))

    return tuple(summarizers)


def _merge_config_overrides(
    base_config: Mapping[str, CodexConfigValue],
    request_config: Mapping[str, StateValue],
) -> tuple[tuple[str, CodexConfigValue], ...]:
    merged_config: dict[str, CodexConfigValue] = dict(base_config)
    for raw_key, raw_value in request_config.items():
        key = _coerce_required_string(raw_key, codex_options.ExecutionOption.CONFIG_OVERRIDES.value)
        if not isinstance(raw_value, (str, int, float, bool)):
            raise TypeError(
                "config_overrides values must be str, int, float, or bool, "
                f"got {type(raw_value).__name__}"
            )
        merged_config[key] = raw_value

    return tuple(sorted(merged_config.items()))


def _coerce_required_string(value: StateValue, option_name: str) -> str:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, str):
        return value

    raise TypeError(f"{option_name} must be str, got {type(value).__name__}")


def _format_config_value(value: CodexConfigValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f"{value!r}"

    return str(value)


def _is_sequence_option(value: StateValue) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _resolve_workspace_relative_path(
    workspace_path: pathlib.Path,
    path: str | pathlib.Path,
) -> pathlib.Path:
    candidate_path = pathlib.Path(path).expanduser()
    if candidate_path.is_absolute():
        return candidate_path.resolve()

    return (workspace_path / candidate_path).resolve()


def _structured_outputs_from_result(
    command_options: CodexCommandOptions,
    workspace_path: pathlib.Path,
    result: subprocess_utils.CommandResult,
) -> dict[str, StateValue]:
    structured_outputs: dict[str, StateValue] = {
        "args": result.args,
        "cwd": str(result.cwd),
        "timed_out": result.timed_out,
    }
    json_events: list[StateValue] | None = None
    if command_options.json_events or command_options.json_event_summarizers:
        json_events = _parse_json_lines(result.stdout)
    if command_options.json_events:
        structured_outputs["json_events"] = json_events or []
    if command_options.json_event_summarizers:
        structured_outputs["json_event_summary"] = _summarize_json_events(
            command_options.json_event_summarizers,
            json_events or [],
        )
    if command_options.output_last_message_path is not None:
        last_message_path = _resolve_workspace_relative_path(
            workspace_path,
            command_options.output_last_message_path,
        )
        structured_outputs["last_message_path"] = str(last_message_path)
        if last_message_path.exists():
            last_message = last_message_path.read_text(encoding="utf-8")
            structured_outputs["last_message"] = last_message
            parsed_last_message = _parse_json_value(last_message)
            if parsed_last_message is not None:
                structured_outputs["last_message_json"] = parsed_last_message

    return structured_outputs


def _parse_json_lines(value: str) -> list[StateValue]:
    parsed_lines: list[StateValue] = []
    for raw_line in value.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parsed_value = _parse_json_value(line)
        parsed_lines.append(parsed_value if parsed_value is not None else line)

    return parsed_lines


def _parse_json_value(value: str) -> StateValue | None:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _summarize_json_events(
    summarizers: Sequence[JsonEventSummarizer],
    events: Sequence[StateValue],
) -> dict[str, StateValue]:
    summary: dict[str, StateValue] = {}
    for summarizer in summarizers:
        summary.update(dict(summarizer(events)))
    return summary


def _is_dangerous_codex_flag(arg: str) -> bool:
    return any(
        arg == dangerous_flag or arg.startswith(f"{dangerous_flag}=")
        for dangerous_flag in DANGEROUS_CODEX_FLAGS
    )


def _is_dangerous_config_override(key: str, value: CodexConfigValue) -> bool:
    normalized_key = key.strip().lower().replace("-", "_")
    normalized_value = value.lower() if isinstance(value, str) else value
    return normalized_key in _DANGEROUS_CONFIG_KEYS and normalized_value in _DANGEROUS_CONFIG_VALUES
