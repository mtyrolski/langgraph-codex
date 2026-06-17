import dataclasses
import pathlib

from langgraph_codex.types import StateValue


@dataclasses.dataclass
class PromptSection:
    title: str
    body: str


@dataclasses.dataclass
class PromptFile:
    path: str | pathlib.Path
    description: str = ""


@dataclasses.dataclass
class PromptSpec:
    title: str = ""
    objective: str = ""
    context_sections: list[PromptSection] = dataclasses.field(default_factory=list)
    constraints: list[str] = dataclasses.field(default_factory=list)
    acceptance_criteria: list[str] = dataclasses.field(default_factory=list)
    files: list[PromptFile] = dataclasses.field(default_factory=list)
    resources: list[str] = dataclasses.field(default_factory=list)
    artifacts: dict[str, StateValue] = dataclasses.field(default_factory=dict)
    additional_instructions: list[str] = dataclasses.field(default_factory=list)
