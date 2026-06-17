from collections.abc import Mapping, Sequence

from langgraph_codex.prompts.models import PromptFile, PromptSection, PromptSpec
from langgraph_codex.types import StateMapping, StateValue


def prompt_spec_from_state(state: StateMapping) -> PromptSpec:
    """Build a prompt spec from graph state while accepting common shorthand values."""
    return PromptSpec(
        title=str(state.get("task_title", "") or ""),
        objective=str(state.get("objective", "") or ""),
        context_sections=_coerce_context_sections(state.get("context", [])),
        constraints=_coerce_list(state.get("constraints", [])),
        acceptance_criteria=_coerce_list(state.get("acceptance_criteria", [])),
        files=_coerce_files(state.get("files", [])),
        resources=_coerce_list(state.get("resources", [])),
        artifacts=_coerce_artifacts(state.get("artifacts", {})),
        additional_instructions=_coerce_list(state.get("additional_instructions", [])),
    )


def _coerce_context_sections(value: StateValue) -> list[PromptSection]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [
            PromptSection(title=str(key), body=str(value[key]))
            for key in sorted(value, key=str)
            if value[key] is not None and str(value[key]).strip()
        ]
    if _is_non_string_sequence(value):
        sections: list[PromptSection] = []
        for item in value:
            if isinstance(item, PromptSection):
                sections.append(item)
            elif isinstance(item, Mapping):
                sections.append(
                    PromptSection(
                        title=str(item.get("title", "")),
                        body=str(item.get("body", "")),
                    )
                )
            elif _is_pair(item):
                sections.append(PromptSection(title=str(item[0]), body=str(item[1])))
            else:
                sections.append(PromptSection(title="Context", body=str(item)))
        return sections

    return [PromptSection(title="Context", body=str(value))]


def _coerce_files(value: StateValue) -> list[PromptFile]:
    if value is None:
        return []
    if _is_non_string_sequence(value):
        files: list[PromptFile] = []
        for item in value:
            if isinstance(item, PromptFile):
                files.append(item)
            elif isinstance(item, Mapping):
                files.append(
                    PromptFile(
                        path=str(item.get("path", "")),
                        description=str(item.get("description", "")),
                    )
                )
            elif _is_pair(item):
                files.append(PromptFile(path=str(item[0]), description=str(item[1])))
            else:
                files.append(PromptFile(path=str(item)))
        return files

    return [PromptFile(path=str(value))]


def _coerce_list(value: StateValue) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if _is_non_string_sequence(value):
        return [str(item) for item in value if item is not None]

    return [str(value)]


def _coerce_artifacts(value: StateValue) -> dict[str, StateValue]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}

    return {"artifact": value}


def _is_non_string_sequence(value: StateValue) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _is_pair(value: StateValue) -> bool:
    return _is_non_string_sequence(value) and len(value) == 2
