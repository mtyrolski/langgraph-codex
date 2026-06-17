import dataclasses
from collections.abc import Callable
from enum import StrEnum
from typing import Final, Protocol

from langgraph_codex.prompts.models import PromptSpec
from langgraph_codex.types import StateValue


class PromptBlock(StrEnum):
    TITLE = "title"
    OBJECTIVE = "objective"
    CONTEXT = "context"
    CONSTRAINTS = "constraints"
    ACCEPTANCE_CRITERIA = "acceptance_criteria"
    FILES = "files"
    RESOURCES = "resources"
    ARTIFACTS = "artifacts"
    ADDITIONAL_INSTRUCTIONS = "additional_instructions"


DEFAULT_MARKDOWN_BLOCK_ORDER: Final[tuple[PromptBlock, ...]] = (
    PromptBlock.TITLE,
    PromptBlock.OBJECTIVE,
    PromptBlock.CONTEXT,
    PromptBlock.CONSTRAINTS,
    PromptBlock.ACCEPTANCE_CRITERIA,
    PromptBlock.FILES,
    PromptBlock.RESOURCES,
    PromptBlock.ARTIFACTS,
    PromptBlock.ADDITIONAL_INSTRUCTIONS,
)


class PromptRenderer(Protocol):
    def render(self, spec: PromptSpec) -> str:
        """Render a prompt spec into a final prompt string."""
        raise NotImplementedError


ArtifactValueRenderer = Callable[[StateValue], str]


@dataclasses.dataclass(frozen=True)
class MarkdownPromptRenderOptions:
    title_level: int = 1
    section_level: int = 2
    context_section_level: int = 3
    bullet: str = "-"
    sort_artifacts: bool = True
    section_order: tuple[PromptBlock, ...] = DEFAULT_MARKDOWN_BLOCK_ORDER
    artifact_value_renderer: ArtifactValueRenderer = str


@dataclasses.dataclass(frozen=True)
class MarkdownPromptRenderer:
    options: MarkdownPromptRenderOptions = MarkdownPromptRenderOptions()

    def render(self, spec: PromptSpec) -> str:
        """Render a prompt spec into stable Markdown, omitting empty sections."""
        self._validate_options()
        block_renderers: dict[PromptBlock, Callable[[PromptSpec], str]] = {
            PromptBlock.TITLE: self._render_title,
            PromptBlock.OBJECTIVE: self._render_objective,
            PromptBlock.CONTEXT: self._render_context_sections,
            PromptBlock.CONSTRAINTS: self._render_constraints,
            PromptBlock.ACCEPTANCE_CRITERIA: self._render_acceptance_criteria,
            PromptBlock.FILES: self._render_files,
            PromptBlock.RESOURCES: self._render_resources,
            PromptBlock.ARTIFACTS: self._render_artifacts,
            PromptBlock.ADDITIONAL_INSTRUCTIONS: self._render_additional_instructions,
        }

        blocks = [
            rendered_block
            for block_name in self.options.section_order
            if (rendered_block := block_renderers[block_name](spec))
        ]
        return "\n\n".join(blocks).strip()

    def _render_title(self, spec: PromptSpec) -> str:
        if not spec.title.strip():
            return ""

        return _heading(self.options.title_level, spec.title.strip())

    def _render_objective(self, spec: PromptSpec) -> str:
        return self._render_text_section("Objective", spec.objective)

    def _render_context_sections(self, spec: PromptSpec) -> str:
        rendered_sections = [
            f"{_heading(self.options.context_section_level, section.title.strip())}\n\n"
            f"{section.body.strip()}"
            for section in spec.context_sections
            if section.title.strip() and section.body.strip()
        ]
        if not rendered_sections:
            return ""

        joined_sections = "\n\n".join(rendered_sections)
        return f"{_heading(self.options.section_level, 'Context')}\n\n{joined_sections}"

    def _render_constraints(self, spec: PromptSpec) -> str:
        return self._render_bullets("Constraints", spec.constraints)

    def _render_acceptance_criteria(self, spec: PromptSpec) -> str:
        return self._render_bullets("Acceptance Criteria", spec.acceptance_criteria)

    def _render_files(self, spec: PromptSpec) -> str:
        rendered_files: list[str] = []
        for prompt_file in spec.files:
            path = str(prompt_file.path).strip()
            description = prompt_file.description.strip()
            if path and description:
                rendered_files.append(f"{self.options.bullet} `{path}`: {description}")
            elif path:
                rendered_files.append(f"{self.options.bullet} `{path}`")

        return self._render_list_section("Files", rendered_files)

    def _render_resources(self, spec: PromptSpec) -> str:
        return self._render_bullets("Resources", spec.resources)

    def _render_artifacts(self, spec: PromptSpec) -> str:
        artifact_keys = sorted(spec.artifacts) if self.options.sort_artifacts else spec.artifacts
        rendered_artifacts: list[str] = []
        for key in artifact_keys:
            value = spec.artifacts[key]
            if value is None or value == "":
                continue

            rendered_value = self.options.artifact_value_renderer(value)
            rendered_artifacts.append(f"{self.options.bullet} `{key}`: {rendered_value}")

        return self._render_list_section("Artifacts", rendered_artifacts)

    def _render_additional_instructions(self, spec: PromptSpec) -> str:
        return self._render_bullets("Additional Instructions", spec.additional_instructions)

    def _render_text_section(self, title: str, body: str) -> str:
        if not body.strip():
            return ""

        return f"{_heading(self.options.section_level, title)}\n\n{body.strip()}"

    def _render_bullets(self, title: str, values: list[str]) -> str:
        normalized_values = [value.strip() for value in values if value.strip()]
        rendered_values = [f"{self.options.bullet} {value}" for value in normalized_values]
        return self._render_list_section(title, rendered_values)

    def _render_list_section(self, title: str, rendered_values: list[str]) -> str:
        if not rendered_values:
            return ""

        joined_values = "\n".join(rendered_values)
        return f"{_heading(self.options.section_level, title)}\n\n{joined_values}"

    def _validate_options(self) -> None:
        _validate_heading_level(self.options.title_level, "title_level")
        _validate_heading_level(self.options.section_level, "section_level")
        _validate_heading_level(self.options.context_section_level, "context_section_level")
        if not self.options.bullet.strip():
            raise ValueError("bullet must not be blank")


def render_prompt(
    spec: PromptSpec,
    *,
    renderer: PromptRenderer | None = None,
    options: MarkdownPromptRenderOptions | None = None,
) -> str:
    if renderer is not None and options is not None:
        raise ValueError("Pass either renderer or options, not both.")

    active_renderer = renderer or MarkdownPromptRenderer(
        options=options or MarkdownPromptRenderOptions()
    )
    return active_renderer.render(spec)


def _heading(level: int, title: str) -> str:
    return f"{'#' * level} {title}"


def _validate_heading_level(level: int, option_name: str) -> None:
    if level < 1 or level > 6:
        raise ValueError(f"{option_name} must be between 1 and 6")
