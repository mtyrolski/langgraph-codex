import pathlib
from typing import TypedDict

import langgraph_codex.execution.base as execution_base
import langgraph_codex.utils.validation as validation_utils
from langgraph_codex.types import StateValue


class WorkflowState(TypedDict, total=False):
    workspace_path: str | pathlib.Path
    task_title: str
    objective: str
    context: StateValue
    constraints: list[str]
    acceptance_criteria: list[str]
    files: list[StateValue]
    resources: list[str]
    artifacts: dict[str, StateValue]
    metadata: dict[str, StateValue]
    execution_options: dict[str, StateValue]
    backend_options: dict[str, StateValue]
    rendered_prompt: str
    execution_result: execution_base.ExecutionResult
    backend_result: execution_base.ExecutionResult
    validation_result: validation_utils.ValidationResult
    review_result: dict[str, StateValue]
    retry_count: int
    max_retries: int
    additional_instructions: list[str]
