import dataclasses
import pathlib
from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Final, TypeVar

from langgraph_codex.types import ExecutionOptions, StateValue

T = TypeVar("T")


class CodexCliBinary(StrEnum):
    CODEX = "codex"


class CodexSandbox(StrEnum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    DANGER_FULL_ACCESS = "danger-full-access"


class CodexApprovalPolicy(StrEnum):
    UNTRUSTED = "untrusted"
    ON_FAILURE = "on-failure"
    ON_REQUEST = "on-request"
    NEVER = "never"


class CodexConfigKey(StrEnum):
    APPROVAL_POLICY = "approval_policy"


class ExecutionOption(StrEnum):
    TIMEOUT_SECONDS = "timeout_seconds"
    MODEL = "model"
    SANDBOX = "sandbox"
    APPROVAL_POLICY = "approval_policy"
    EXTRA_ARGS = "extra_args"
    CONFIG_OVERRIDES = "config_overrides"
    PROFILE = "profile"
    ADDITIONAL_WRITABLE_ROOTS = "additional_writable_roots"
    SKIP_GIT_REPO_CHECK = "skip_git_repo_check"
    OUTPUT_SCHEMA_PATH = "output_schema_path"
    OUTPUT_LAST_MESSAGE_PATH = "output_last_message_path"
    JSON_EVENTS = "json_events"
    JSON_EVENT_SUMMARIZERS = "json_event_summarizers"


class WorkflowPolicyViolation(ValueError):
    """Raised when execution options fall outside a workflow policy."""


@dataclasses.dataclass(frozen=True)
class CodexWorkflowPolicy:
    workflow: str
    writable_roots: tuple[str | pathlib.Path, ...] | None = None
    profiles: tuple[str | None, ...] | None = None
    sandbox_modes: tuple[str, ...] | None = None
    models: tuple[str | None, ...] | None = None

    def restrict(
        self,
        options: Mapping[str, StateValue],
        *,
        workspace_path: str | pathlib.Path | None = None,
    ) -> ExecutionOptions:
        """Return a copy of options after validating them against this policy."""
        restricted_options = dict(options)
        self.validate(restricted_options, workspace_path=workspace_path)
        return restricted_options

    def validate(
        self,
        options: Mapping[str, StateValue],
        *,
        workspace_path: str | pathlib.Path | None = None,
    ) -> None:
        _validate_choice_option(
            policy=self,
            options=options,
            option=ExecutionOption.PROFILE,
            allowed_values=self.profiles,
        )
        _validate_choice_option(
            policy=self,
            options=options,
            option=ExecutionOption.SANDBOX,
            allowed_values=self.sandbox_modes,
        )
        _validate_choice_option(
            policy=self,
            options=options,
            option=ExecutionOption.MODEL,
            allowed_values=self.models,
        )
        _validate_writable_roots(
            policy=self,
            options=options,
            workspace_path=workspace_path,
        )


def codex_workflow_policy(
    workflow: str,
    *,
    writable_roots: Iterable[str | pathlib.Path] | None = None,
    profiles: Iterable[str | None] | None = None,
    sandbox_modes: Iterable[str | CodexSandbox] | None = None,
    models: Iterable[str | None] | None = None,
) -> CodexWorkflowPolicy:
    """Build a workflow policy with enum values normalized to strings."""
    return CodexWorkflowPolicy(
        workflow=workflow,
        writable_roots=_optional_tuple(writable_roots),
        profiles=_optional_tuple(profiles),
        sandbox_modes=_optional_string_tuple(sandbox_modes),
        models=_optional_tuple(models),
    )


def restrict_options_by_workflow(
    workflow: str,
    options: Mapping[str, StateValue],
    policies: Mapping[str, CodexWorkflowPolicy],
    *,
    workspace_path: str | pathlib.Path | None = None,
) -> ExecutionOptions:
    """Validate options against the named workflow policy and return a copy."""
    try:
        policy = policies[workflow]
    except KeyError as error:
        raise WorkflowPolicyViolation(
            f"No Codex workflow policy configured for: {workflow}"
        ) from error

    return policy.restrict(options, workspace_path=workspace_path)


def _validate_choice_option(
    *,
    policy: CodexWorkflowPolicy,
    options: Mapping[str, StateValue],
    option: ExecutionOption,
    allowed_values: tuple[StateValue, ...] | None,
) -> None:
    if allowed_values is None or option.value not in options:
        return

    value = _string_or_none(options[option.value], option.value)
    if value not in allowed_values:
        raise WorkflowPolicyViolation(
            f"Workflow {policy.workflow!r} does not allow {option.value}={value!r}"
        )


def _validate_writable_roots(
    *,
    policy: CodexWorkflowPolicy,
    options: Mapping[str, StateValue],
    workspace_path: str | pathlib.Path | None,
) -> None:
    if policy.writable_roots is None:
        return

    option_name = ExecutionOption.ADDITIONAL_WRITABLE_ROOTS.value
    roots = options.get(option_name, ())
    if not _is_non_string_iterable(roots):
        raise TypeError(f"{option_name} must be a sequence of paths")

    allowed_roots = tuple(
        _resolve_policy_path(root, workspace_path=workspace_path) for root in policy.writable_roots
    )
    for root in roots:
        if not isinstance(root, (str, pathlib.Path)):
            raise TypeError(f"{option_name} entries must be str or pathlib.Path")
        resolved_root = _resolve_policy_path(root, workspace_path=workspace_path)
        if not any(_is_relative_to(resolved_root, allowed_root) for allowed_root in allowed_roots):
            raise WorkflowPolicyViolation(
                f"Workflow {policy.workflow!r} does not allow writable root: {root}"
            )


def _resolve_policy_path(
    path: str | pathlib.Path,
    *,
    workspace_path: str | pathlib.Path | None,
) -> pathlib.Path:
    candidate = pathlib.Path(path).expanduser()
    if not candidate.is_absolute() and workspace_path is not None:
        candidate = pathlib.Path(workspace_path).expanduser() / candidate
    return candidate.resolve(strict=False)


def _is_relative_to(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _string_or_none(value: StateValue, option_name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, str):
        return value
    raise TypeError(f"{option_name} must be str or None, got {type(value).__name__}")


def _optional_tuple(values: Iterable[T] | None) -> tuple[T, ...] | None:
    if values is None:
        return None
    return tuple(values)


def _optional_string_tuple(
    values: Iterable[str | StrEnum] | None,
) -> tuple[str, ...] | None:
    if values is None:
        return None
    return tuple(value.value if isinstance(value, StrEnum) else value for value in values)


def _is_non_string_iterable(value: StateValue) -> bool:
    return isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray))


DEFAULT_CODEX_BIN: Final[str] = CodexCliBinary.CODEX.value
DEFAULT_CODEX_MODEL: Final[str | None] = None
DEFAULT_SANDBOX: Final[str] = CodexSandbox.WORKSPACE_WRITE.value
DEFAULT_APPROVAL_POLICY: Final[str] = CodexApprovalPolicy.NEVER.value
DEFAULT_TIMEOUT_SECONDS: Final[int] = 900
DEFAULT_MAX_RETRIES: Final[int] = 0

__all__ = [
    "CodexApprovalPolicy",
    "CodexCliBinary",
    "CodexWorkflowPolicy",
    "CodexConfigKey",
    "CodexSandbox",
    "DEFAULT_APPROVAL_POLICY",
    "DEFAULT_CODEX_BIN",
    "DEFAULT_CODEX_MODEL",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_SANDBOX",
    "DEFAULT_TIMEOUT_SECONDS",
    "ExecutionOption",
    "WorkflowPolicyViolation",
    "codex_workflow_policy",
    "restrict_options_by_workflow",
]
