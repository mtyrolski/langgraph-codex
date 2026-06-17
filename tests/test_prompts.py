import pathlib

import pytest

import langgraph_codex.utils.prompts


def test_render_prompt_omits_empty_sections_and_uses_stable_order() -> None:
    spec = langgraph_codex.utils.prompts.PromptSpec(
        title="Analyze dataset",
        objective="Produce a concise summary.",
        context_sections=[
            langgraph_codex.utils.prompts.PromptSection(
                title="Source",
                body="Synthetic benchmark data.",
            )
        ],
        constraints=["Do not assume a software repository.", ""],
        acceptance_criteria=["Summary references inputs."],
        files=[
            langgraph_codex.utils.prompts.PromptFile(
                path="data/input.csv",
                description="Primary data file.",
            )
        ],
        resources=["https://example.invalid/spec"],
        artifacts={"zeta": "last", "alpha": "first", "empty": ""},
        additional_instructions=["Return Markdown."],
    )

    rendered_prompt = langgraph_codex.utils.prompts.render_prompt(spec)

    assert rendered_prompt == (
        "# Analyze dataset\n\n"
        "## Objective\n\n"
        "Produce a concise summary.\n\n"
        "## Context\n\n"
        "### Source\n\n"
        "Synthetic benchmark data.\n\n"
        "## Constraints\n\n"
        "- Do not assume a software repository.\n\n"
        "## Acceptance Criteria\n\n"
        "- Summary references inputs.\n\n"
        "## Files\n\n"
        "- `data/input.csv`: Primary data file.\n\n"
        "## Resources\n\n"
        "- https://example.invalid/spec\n\n"
        "## Artifacts\n\n"
        "- `alpha`: first\n"
        "- `zeta`: last\n\n"
        "## Additional Instructions\n\n"
        "- Return Markdown."
    )
    assert "empty" not in rendered_prompt


def test_prompt_spec_from_state_coerces_structured_state() -> None:
    spec = langgraph_codex.utils.prompts.prompt_spec_from_state(
        {
            "task_title": "Title",
            "objective": "Objective",
            "context": {"B": "second", "A": "first"},
            "constraints": "one constraint",
            "files": [{"path": "notes.md", "description": "Notes"}],
        }
    )

    assert [section.title for section in spec.context_sections] == ["A", "B"]
    assert spec.constraints == ["one constraint"]
    assert spec.files[0].path == "notes.md"


def test_render_prompt_returns_empty_string_for_empty_spec() -> None:
    assert (
        langgraph_codex.utils.prompts.render_prompt(langgraph_codex.utils.prompts.PromptSpec())
        == ""
    )


def test_render_prompt_accepts_markdown_render_options() -> None:
    spec = langgraph_codex.utils.prompts.PromptSpec(
        title="Custom renderer",
        objective="Use caller-selected sections.",
        artifacts={"b": "second", "a": "first"},
    )

    rendered_prompt = langgraph_codex.utils.prompts.render_prompt(
        spec,
        options=langgraph_codex.utils.prompts.MarkdownPromptRenderOptions(
            title_level=2,
            section_level=3,
            bullet="*",
            sort_artifacts=False,
            section_order=(
                langgraph_codex.utils.prompts.PromptBlock.OBJECTIVE,
                langgraph_codex.utils.prompts.PromptBlock.TITLE,
                langgraph_codex.utils.prompts.PromptBlock.ARTIFACTS,
            ),
        ),
    )

    assert rendered_prompt == (
        "### Objective\n\n"
        "Use caller-selected sections.\n\n"
        "## Custom renderer\n\n"
        "### Artifacts\n\n"
        "* `b`: second\n"
        "* `a`: first"
    )


def test_render_prompt_handles_files_with_and_without_descriptions() -> None:
    spec = langgraph_codex.utils.prompts.PromptSpec(
        files=[
            langgraph_codex.utils.prompts.PromptFile(path="README.md"),
            langgraph_codex.utils.prompts.PromptFile(
                path=pathlib.Path("tests/test_prompts.py"),
                description="Prompt tests.",
            ),
            langgraph_codex.utils.prompts.PromptFile(path="   ", description="Ignored."),
        ]
    )

    rendered_prompt = langgraph_codex.utils.prompts.render_prompt(spec)

    assert rendered_prompt == (
        "## Files\n\n- `README.md`\n- `tests/test_prompts.py`: Prompt tests."
    )


def test_render_prompt_filters_blank_context_bullets_files_and_artifacts() -> None:
    spec = langgraph_codex.utils.prompts.PromptSpec(
        title="  Trimmed title  ",
        objective="  Trimmed objective  ",
        context_sections=[
            langgraph_codex.utils.prompts.PromptSection(title=" ", body="ignored"),
            langgraph_codex.utils.prompts.PromptSection(title="Kept", body=" body "),
        ],
        constraints=[" ", "keep constraint"],
        files=[langgraph_codex.utils.prompts.PromptFile(path="", description="ignored")],
        artifacts={"none": None, "empty": "", "kept": 0},
    )

    rendered_prompt = langgraph_codex.utils.prompts.render_prompt(spec)

    assert rendered_prompt == (
        "# Trimmed title\n\n"
        "## Objective\n\n"
        "Trimmed objective\n\n"
        "## Context\n\n"
        "### Kept\n\n"
        "body\n\n"
        "## Constraints\n\n"
        "- keep constraint\n\n"
        "## Artifacts\n\n"
        "- `kept`: 0"
    )


@pytest.mark.parametrize(
    ("context_value", "expected_sections"),
    [
        (None, []),
        ("raw context", [("Context", "raw context")]),
        (
            ["first", {"title": "Second", "body": "second body"}],
            [("Context", "first"), ("Second", "second body")],
        ),
        (
            [
                langgraph_codex.utils.prompts.PromptSection(
                    title="Existing",
                    body="existing body",
                )
            ],
            [("Existing", "existing body")],
        ),
    ],
)
def test_prompt_spec_from_state_coerces_context_variants(
    context_value: object,
    expected_sections: list[tuple[str, str]],
) -> None:
    spec = langgraph_codex.utils.prompts.prompt_spec_from_state({"context": context_value})

    assert [(section.title, section.body) for section in spec.context_sections] == expected_sections


def test_prompt_spec_from_state_accepts_context_and_file_pairs() -> None:
    spec = langgraph_codex.utils.prompts.prompt_spec_from_state(
        {
            "context": [("Pair", "Pair body")],
            "files": [("README.md", "Project overview.")],
        }
    )

    assert [(section.title, section.body) for section in spec.context_sections] == [
        ("Pair", "Pair body")
    ]
    assert [(str(prompt_file.path), prompt_file.description) for prompt_file in spec.files] == [
        ("README.md", "Project overview.")
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, []),
        ("single", ["single"]),
        (["one", None, 2], ["one", "2"]),
        (7, ["7"]),
    ],
)
def test_prompt_spec_from_state_coerces_list_like_fields(
    value: object,
    expected: list[str],
) -> None:
    spec = langgraph_codex.utils.prompts.prompt_spec_from_state(
        {
            "constraints": value,
            "acceptance_criteria": value,
            "resources": value,
            "additional_instructions": value,
        }
    )

    assert spec.constraints == expected
    assert spec.acceptance_criteria == expected
    assert spec.resources == expected
    assert spec.additional_instructions == expected


@pytest.mark.parametrize(
    ("files_value", "expected_paths"),
    [
        (None, []),
        ("README.md", ["README.md"]),
        (
            [
                "pyproject.toml",
                {"path": "tests/test_graphs.py", "description": "Graph tests"},
                langgraph_codex.utils.prompts.PromptFile(path="docs/design-philosophy.md"),
            ],
            ["pyproject.toml", "tests/test_graphs.py", "docs/design-philosophy.md"],
        ),
    ],
)
def test_prompt_spec_from_state_coerces_file_variants(
    files_value: object,
    expected_paths: list[str],
) -> None:
    spec = langgraph_codex.utils.prompts.prompt_spec_from_state({"files": files_value})

    assert [str(prompt_file.path) for prompt_file in spec.files] == expected_paths


def test_code_review_recipe_builds_actionable_review_prompt() -> None:
    spec = langgraph_codex.utils.prompts.create_code_review_prompt(
        changes_summary="Diff touches prompt rendering and public exports.",
        focus_areas=["API compatibility", "Missing tests"],
        files=[
            ("langgraph_codex/prompts/renderers.py", "Markdown renderer."),
            langgraph_codex.utils.prompts.PromptFile(
                path="tests/test_prompts.py",
                description="Prompt coverage.",
            ),
        ],
        additional_instructions=["Do not edit files during review."],
    )

    rendered_prompt = langgraph_codex.utils.prompts.render_prompt(spec)

    assert spec.title == "Code Review"
    assert [str(prompt_file.path) for prompt_file in spec.files] == [
        "langgraph_codex/prompts/renderers.py",
        "tests/test_prompts.py",
    ]
    assert (
        "### Changes Summary\n\nDiff touches prompt rendering and public exports."
        in rendered_prompt
    )
    assert "### Focus Areas\n\n- API compatibility\n- Missing tests" in rendered_prompt
    assert "- Report findings first, ordered by severity." in rendered_prompt
    assert "- Findings are actionable and include severity." in rendered_prompt
    assert "- Do not edit files during review." in rendered_prompt


def test_implementation_recipe_includes_requirements_and_validation_commands() -> None:
    spec = langgraph_codex.utils.prompts.create_implementation_prompt(
        objective="Add typed prompt recipes.",
        requirements=["Expose helpers from prompt modules.", "Preserve renderer output."],
        validation_commands=["uv run pytest tests/test_prompts.py"],
        constraints=["Do not change graph execution behavior."],
        acceptance_criteria=["Prompt recipe tests pass."],
    )

    assert spec.title == "Implementation"
    assert [(section.title, section.body) for section in spec.context_sections] == [
        (
            "Requirements",
            "- Expose helpers from prompt modules.\n- Preserve renderer output.",
        ),
        ("Validation Commands", "- uv run pytest tests/test_prompts.py"),
    ]
    assert "Keep changes scoped to the requested behavior." in spec.constraints
    assert "Do not change graph execution behavior." in spec.constraints
    assert "Prompt recipe tests pass." in spec.acceptance_criteria


def test_test_generation_recipe_describes_behavior_and_scenarios() -> None:
    spec = langgraph_codex.utils.prompts.create_test_generation_prompt(
        objective="Cover prompt recipes.",
        behavior_under_test="Recipe helpers return PromptSpec objects.",
        test_scenarios=["Default constraints", "Caller-provided files"],
    )

    assert spec.title == "Test Generation"
    assert [(section.title, section.body) for section in spec.context_sections] == [
        ("Behavior Under Test", "Recipe helpers return PromptSpec objects."),
        ("Test Scenarios", "- Default constraints\n- Caller-provided files"),
    ]
    assert "Reuse the project's existing test framework and fixtures." in spec.constraints


def test_docs_update_recipe_and_migration_plan_recipe_use_task_specific_context() -> None:
    docs_spec = langgraph_codex.utils.prompts.create_docs_update_prompt(
        objective="Document prompt recipes.",
        audience="LangGraph application developers.",
        documentation_targets=["README prompt section", "Examples index"],
    )
    migration_spec = langgraph_codex.utils.prompts.create_migration_plan_prompt(
        objective="Plan migration to structured prompts.",
        current_state="Prompt builders return raw strings.",
        target_state="Prompt builders return PromptSpec recipes.",
        migration_steps=["Inventory prompt builders", "Replace common tasks with recipes"],
    )

    assert [(section.title, section.body) for section in docs_spec.context_sections] == [
        ("Audience", "LangGraph application developers."),
        ("Documentation Targets", "- README prompt section\n- Examples index"),
    ]
    assert "Do not document unsupported behavior." in docs_spec.constraints
    assert [(section.title, section.body) for section in migration_spec.context_sections] == [
        ("Current State", "Prompt builders return raw strings."),
        ("Target State", "Prompt builders return PromptSpec recipes."),
        (
            "Known Migration Steps",
            "- Inventory prompt builders\n- Replace common tasks with recipes",
        ),
    ]
    assert "Separate required changes from optional cleanup." in migration_spec.constraints


def test_prompt_recipes_are_public_from_prompt_modules() -> None:
    import langgraph_codex.prompts

    assert langgraph_codex.prompts.create_code_review_prompt is (
        langgraph_codex.utils.prompts.create_code_review_prompt
    )
    assert langgraph_codex.prompts.create_implementation_prompt is (
        langgraph_codex.utils.prompts.create_implementation_prompt
    )
    assert langgraph_codex.prompts.create_test_generation_prompt is (
        langgraph_codex.utils.prompts.create_test_generation_prompt
    )
    assert langgraph_codex.prompts.create_docs_update_prompt is (
        langgraph_codex.utils.prompts.create_docs_update_prompt
    )
    assert langgraph_codex.prompts.create_migration_plan_prompt is (
        langgraph_codex.utils.prompts.create_migration_plan_prompt
    )
