"""Typed prompt recipes for common Codex workflows."""
# pylint: disable=too-many-arguments

import pathlib
from collections.abc import Mapping, Sequence

from langgraph_codex.prompts.models import PromptFile, PromptSection, PromptSpec
from langgraph_codex.types import StateValue

PromptFileInput = PromptFile | str | pathlib.Path | tuple[str | pathlib.Path, str]
PromptSectionInput = PromptSection | tuple[str, str]

_CODE_REVIEW_CONSTRAINTS: tuple[str, ...] = (
    "Prioritize correctness, regressions, security, and missing tests.",
    "Report findings first, ordered by severity.",
    "Ground findings in concrete files, symbols, or behavior when evidence is available.",
)
_CODE_REVIEW_ACCEPTANCE_CRITERIA: tuple[str, ...] = (
    "Findings are actionable and include severity.",
    "Risky or unverified assumptions are called out explicitly.",
)

_IMPLEMENTATION_CONSTRAINTS: tuple[str, ...] = (
    "Keep changes scoped to the requested behavior.",
    "Follow existing project patterns before introducing new abstractions.",
    "Update or add focused tests for changed behavior.",
)
_IMPLEMENTATION_ACCEPTANCE_CRITERIA: tuple[str, ...] = (
    "The requested behavior is implemented.",
    "Relevant tests or validation commands pass.",
)

_TEST_GENERATION_CONSTRAINTS: tuple[str, ...] = (
    "Prefer focused tests that exercise observable behavior.",
    "Reuse the project's existing test framework and fixtures.",
    "Avoid brittle assertions against incidental implementation details.",
)
_TEST_GENERATION_ACCEPTANCE_CRITERIA: tuple[str, ...] = (
    "New tests fail against the old behavior when practical.",
    "The relevant test subset passes after implementation.",
)

_DOCS_UPDATE_CONSTRAINTS: tuple[str, ...] = (
    "Keep documentation consistent with current public APIs and examples.",
    "Use concise, user-facing language.",
    "Do not document unsupported behavior.",
)
_DOCS_UPDATE_ACCEPTANCE_CRITERIA: tuple[str, ...] = (
    "Documentation explains the new or changed workflow.",
    "Examples are syntactically valid and match exported names.",
)

_MIGRATION_PLAN_CONSTRAINTS: tuple[str, ...] = (
    "Separate required changes from optional cleanup.",
    "Call out compatibility, rollback, and data-risk concerns.",
    "Prefer incremental steps that can be validated independently.",
)
_MIGRATION_PLAN_ACCEPTANCE_CRITERIA: tuple[str, ...] = (
    "The plan identifies sequencing, risks, validation, and rollback guidance.",
    "Each step has a clear owner or implementation surface when known.",
)


def create_code_review_prompt(
    *,
    objective: str = "Review the requested code changes and identify actionable issues.",
    changes_summary: str = "",
    focus_areas: Sequence[str] | None = None,
    context_sections: Sequence[PromptSectionInput] | None = None,
    files: Sequence[PromptFileInput] | None = None,
    constraints: Sequence[str] | None = None,
    acceptance_criteria: Sequence[str] | None = None,
    resources: Sequence[str] | None = None,
    artifacts: Mapping[str, StateValue] | None = None,
    additional_instructions: Sequence[str] | None = None,
) -> PromptSpec:
    """Build a PromptSpec for a Codex code review task."""
    return _build_recipe_spec(
        title="Code Review",
        objective=objective,
        context_sections=[
            *_optional_text_section("Changes Summary", changes_summary),
            *_optional_list_section("Focus Areas", focus_areas),
            *_coerce_context_sections(context_sections),
        ],
        constraints=(*_CODE_REVIEW_CONSTRAINTS, *_coerce_strings(constraints)),
        acceptance_criteria=(
            *_CODE_REVIEW_ACCEPTANCE_CRITERIA,
            *_coerce_strings(acceptance_criteria),
        ),
        files=files,
        resources=resources,
        artifacts=artifacts,
        additional_instructions=additional_instructions,
    )


def create_implementation_prompt(
    *,
    objective: str,
    requirements: Sequence[str] | None = None,
    validation_commands: Sequence[str] | None = None,
    context_sections: Sequence[PromptSectionInput] | None = None,
    files: Sequence[PromptFileInput] | None = None,
    constraints: Sequence[str] | None = None,
    acceptance_criteria: Sequence[str] | None = None,
    resources: Sequence[str] | None = None,
    artifacts: Mapping[str, StateValue] | None = None,
    additional_instructions: Sequence[str] | None = None,
) -> PromptSpec:
    """Build a PromptSpec for a bounded Codex implementation task."""
    return _build_recipe_spec(
        title="Implementation",
        objective=objective,
        context_sections=[
            *_optional_list_section("Requirements", requirements),
            *_optional_list_section("Validation Commands", validation_commands),
            *_coerce_context_sections(context_sections),
        ],
        constraints=(*_IMPLEMENTATION_CONSTRAINTS, *_coerce_strings(constraints)),
        acceptance_criteria=(
            *_IMPLEMENTATION_ACCEPTANCE_CRITERIA,
            *_coerce_strings(acceptance_criteria),
        ),
        files=files,
        resources=resources,
        artifacts=artifacts,
        additional_instructions=additional_instructions,
    )


def create_test_generation_prompt(
    *,
    objective: str,
    behavior_under_test: str = "",
    test_scenarios: Sequence[str] | None = None,
    validation_commands: Sequence[str] | None = None,
    context_sections: Sequence[PromptSectionInput] | None = None,
    files: Sequence[PromptFileInput] | None = None,
    constraints: Sequence[str] | None = None,
    acceptance_criteria: Sequence[str] | None = None,
    resources: Sequence[str] | None = None,
    artifacts: Mapping[str, StateValue] | None = None,
    additional_instructions: Sequence[str] | None = None,
) -> PromptSpec:
    """Build a PromptSpec for adding or improving tests."""
    return _build_recipe_spec(
        title="Test Generation",
        objective=objective,
        context_sections=[
            *_optional_text_section("Behavior Under Test", behavior_under_test),
            *_optional_list_section("Test Scenarios", test_scenarios),
            *_optional_list_section("Validation Commands", validation_commands),
            *_coerce_context_sections(context_sections),
        ],
        constraints=(*_TEST_GENERATION_CONSTRAINTS, *_coerce_strings(constraints)),
        acceptance_criteria=(
            *_TEST_GENERATION_ACCEPTANCE_CRITERIA,
            *_coerce_strings(acceptance_criteria),
        ),
        files=files,
        resources=resources,
        artifacts=artifacts,
        additional_instructions=additional_instructions,
    )


def create_docs_update_prompt(
    *,
    objective: str,
    audience: str = "",
    documentation_targets: Sequence[str] | None = None,
    context_sections: Sequence[PromptSectionInput] | None = None,
    files: Sequence[PromptFileInput] | None = None,
    constraints: Sequence[str] | None = None,
    acceptance_criteria: Sequence[str] | None = None,
    resources: Sequence[str] | None = None,
    artifacts: Mapping[str, StateValue] | None = None,
    additional_instructions: Sequence[str] | None = None,
) -> PromptSpec:
    """Build a PromptSpec for updating user-facing documentation."""
    return _build_recipe_spec(
        title="Documentation Update",
        objective=objective,
        context_sections=[
            *_optional_text_section("Audience", audience),
            *_optional_list_section("Documentation Targets", documentation_targets),
            *_coerce_context_sections(context_sections),
        ],
        constraints=(*_DOCS_UPDATE_CONSTRAINTS, *_coerce_strings(constraints)),
        acceptance_criteria=(
            *_DOCS_UPDATE_ACCEPTANCE_CRITERIA,
            *_coerce_strings(acceptance_criteria),
        ),
        files=files,
        resources=resources,
        artifacts=artifacts,
        additional_instructions=additional_instructions,
    )


def create_migration_plan_prompt(
    *,
    objective: str,
    current_state: str = "",
    target_state: str = "",
    migration_steps: Sequence[str] | None = None,
    context_sections: Sequence[PromptSectionInput] | None = None,
    files: Sequence[PromptFileInput] | None = None,
    constraints: Sequence[str] | None = None,
    acceptance_criteria: Sequence[str] | None = None,
    resources: Sequence[str] | None = None,
    artifacts: Mapping[str, StateValue] | None = None,
    additional_instructions: Sequence[str] | None = None,
) -> PromptSpec:
    """Build a PromptSpec for migration planning."""
    return _build_recipe_spec(
        title="Migration Plan",
        objective=objective,
        context_sections=[
            *_optional_text_section("Current State", current_state),
            *_optional_text_section("Target State", target_state),
            *_optional_list_section("Known Migration Steps", migration_steps),
            *_coerce_context_sections(context_sections),
        ],
        constraints=(*_MIGRATION_PLAN_CONSTRAINTS, *_coerce_strings(constraints)),
        acceptance_criteria=(
            *_MIGRATION_PLAN_ACCEPTANCE_CRITERIA,
            *_coerce_strings(acceptance_criteria),
        ),
        files=files,
        resources=resources,
        artifacts=artifacts,
        additional_instructions=additional_instructions,
    )


def _build_recipe_spec(
    *,
    title: str,
    objective: str,
    context_sections: Sequence[PromptSection],
    constraints: Sequence[str],
    acceptance_criteria: Sequence[str],
    files: Sequence[PromptFileInput] | None,
    resources: Sequence[str] | None,
    artifacts: Mapping[str, StateValue] | None,
    additional_instructions: Sequence[str] | None,
) -> PromptSpec:
    return PromptSpec(
        title=title,
        objective=objective,
        context_sections=list(context_sections),
        constraints=_coerce_strings(constraints),
        acceptance_criteria=_coerce_strings(acceptance_criteria),
        files=_coerce_files(files),
        resources=_coerce_strings(resources),
        artifacts=dict(artifacts or {}),
        additional_instructions=_coerce_strings(additional_instructions),
    )


def _coerce_context_sections(
    context_sections: Sequence[PromptSectionInput] | None,
) -> list[PromptSection]:
    sections: list[PromptSection] = []
    for section in context_sections or ():
        if isinstance(section, PromptSection):
            sections.append(section)
        else:
            sections.append(PromptSection(title=section[0], body=section[1]))
    return sections


def _coerce_files(files: Sequence[PromptFileInput] | None) -> list[PromptFile]:
    prompt_files: list[PromptFile] = []
    for file_input in files or ():
        if isinstance(file_input, PromptFile):
            prompt_files.append(file_input)
        elif isinstance(file_input, tuple):
            prompt_files.append(PromptFile(path=file_input[0], description=file_input[1]))
        else:
            prompt_files.append(PromptFile(path=file_input))
    return prompt_files


def _coerce_strings(values: Sequence[str] | None) -> list[str]:
    return [value for value in values or () if value.strip()]


def _optional_text_section(title: str, body: str) -> list[PromptSection]:
    if not body.strip():
        return []
    return [PromptSection(title=title, body=body)]


def _optional_list_section(title: str, values: Sequence[str] | None) -> list[PromptSection]:
    normalized_values = _coerce_strings(values)
    if not normalized_values:
        return []
    return [PromptSection(title=title, body="\n".join(f"- {value}" for value in normalized_values))]
