import dataclasses
import json
import pathlib
from collections.abc import Callable, MutableMapping
from typing import TypeAlias

import langgraph_codex.utils.subprocess as subprocess_utils
from langgraph_codex.types import StateValue


@dataclasses.dataclass
class ValidationResult:
    passed: bool
    message: str = ""
    details: dict[str, StateValue] = dataclasses.field(default_factory=dict)


ValidatorState: TypeAlias = MutableMapping[str, StateValue]
Validator: TypeAlias = Callable[[ValidatorState], ValidationResult]


def passing_validation(message: str = "Validation passed.") -> ValidationResult:
    """Create a successful validation result with no extra details."""
    return ValidationResult(passed=True, message=message)


def failing_validation(
    message: str,
    details: dict[str, StateValue] | None = None,
) -> ValidationResult:
    """Create a failed validation result with optional structured details."""
    return ValidationResult(passed=False, message=message, details=details or {})


def run_validators(
    state: ValidatorState,
    validators: list[Validator] | None = None,
) -> ValidationResult:
    """Run validators in order and stop at the first failure."""
    active_validators = validators or []
    details: dict[str, StateValue] = {"results": []}

    for validator in active_validators:
        result = validator(state)
        details["results"].append(dataclasses.asdict(result))
        if not result.passed:
            return ValidationResult(
                passed=False,
                message=result.message,
                details=details,
            )

    return ValidationResult(
        passed=True,
        message="All validators passed." if active_validators else "No validators configured.",
        details=details,
    )


def require_artifacts(keys: list[str]) -> Validator:
    """Return a validator that requires named keys in state['artifacts']."""

    def validate(state: ValidatorState) -> ValidationResult:
        artifacts = state.get("artifacts", {}) or {}
        missing_keys = [key for key in keys if key not in artifacts]
        if missing_keys:
            return failing_validation(
                message=f"Missing required artifacts: {', '.join(missing_keys)}",
                details={"missing": missing_keys},
            )

        return passing_validation("Required artifacts are present.")

    return validate


def require_files(paths: list[str | pathlib.Path]) -> Validator:
    """Return a validator that checks for files relative to the workspace path."""

    def validate(state: ValidatorState) -> ValidationResult:
        workspace_path = pathlib.Path(state.get("workspace_path", pathlib.Path.cwd()))
        missing_paths: list[str] = []
        for relative_path in paths:
            candidate_path = workspace_path / pathlib.Path(relative_path)
            if not candidate_path.exists():
                missing_paths.append(str(relative_path))

        if missing_paths:
            return failing_validation(
                message=f"Missing required files: {', '.join(missing_paths)}",
                details={"missing": missing_paths},
            )

        return passing_validation("Required files are present.")

    return validate


def require_json_artifact(key: str) -> Validator:
    """Return a validator that requires an artifact to be structured or valid JSON."""

    def validate(state: ValidatorState) -> ValidationResult:
        artifacts = state.get("artifacts", {}) or {}
        if key not in artifacts:
            return failing_validation(message=f"Missing JSON artifact: {key}")

        value = artifacts[key]
        if isinstance(value, (dict, list)):
            return passing_validation(f"JSON artifact is structured: {key}")

        try:
            json.loads(str(value))
        except json.JSONDecodeError as error:
            return failing_validation(
                message=f"Artifact is not valid JSON: {key}",
                details={"error": str(error)},
            )

        return passing_validation(f"JSON artifact is valid: {key}")

    return validate


def require_structured_output(key: str) -> Validator:
    """Return a validator that requires a key in execution_result.structured_outputs."""

    def validate(state: ValidatorState) -> ValidationResult:
        execution_result = state.get("execution_result") or state.get("backend_result")
        if execution_result is None:
            return failing_validation(message="Missing execution result.")
        if key not in execution_result.structured_outputs:
            return failing_validation(
                message=f"Missing structured output: {key}",
                details={"missing": key},
            )

        return passing_validation(f"Structured output is present: {key}")

    return validate


def command_validator(
    args: list[str],
    timeout_seconds: int | float | None = None,
) -> Validator:
    """Return a validator that passes only when a command exits with code zero."""

    def validate(state: ValidatorState) -> ValidationResult:
        workspace_path = pathlib.Path(state.get("workspace_path", pathlib.Path.cwd()))
        result = subprocess_utils.run_command(
            args=args,
            cwd=workspace_path,
            timeout_seconds=timeout_seconds,
        )
        if result.returncode != 0:
            return failing_validation(
                message=f"Command failed with return code {result.returncode}: {' '.join(args)}",
                details=dataclasses.asdict(result),
            )

        return ValidationResult(
            passed=True,
            message=f"Command passed: {' '.join(args)}",
            details=dataclasses.asdict(result),
        )

    return validate
