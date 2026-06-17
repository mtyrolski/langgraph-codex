from enum import StrEnum
from typing import Final


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


DEFAULT_CODEX_BIN: Final[str] = CodexCliBinary.CODEX.value
DEFAULT_CODEX_MODEL: Final[str | None] = None
DEFAULT_SANDBOX: Final[str] = CodexSandbox.WORKSPACE_WRITE.value
DEFAULT_APPROVAL_POLICY: Final[str] = CodexApprovalPolicy.NEVER.value
DEFAULT_TIMEOUT_SECONDS: Final[int] = 900
DEFAULT_MAX_RETRIES: Final[int] = 0

__all__ = [
    "CodexApprovalPolicy",
    "CodexCliBinary",
    "CodexConfigKey",
    "CodexSandbox",
    "DEFAULT_APPROVAL_POLICY",
    "DEFAULT_CODEX_BIN",
    "DEFAULT_CODEX_MODEL",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_SANDBOX",
    "DEFAULT_TIMEOUT_SECONDS",
    "ExecutionOption",
]
