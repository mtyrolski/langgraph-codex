# langgraph-codex

Put Codex inside the LangGraph you already own.

`langgraph-codex` is a small adapter library for one practical pattern: keep your deterministic graph, then replace one bounded node with a Codex-backed node when ordinary Python is not enough.

- LangGraph owns orchestration, state, routing, persistence, and checkpoints.
- Python owns parsing, context building, policy, and validation.
- Codex owns one explicit execution step with a clear prompt and workspace.
- Your application stays in control.

It is not a chat framework, hidden agent runtime, repository automation product, or broad model abstraction layer.

This README describes `langgraph-codex` v0.1.4.

## Install

```bash
uv add langgraph-codex
```

For local development:

```bash
uv sync --extra dev
make check
```

## Start Here: Codex As One LangGraph Node

This is the main use case. Build a normal `langgraph.graph.StateGraph`, authorize Codex once, and use `create_codex_node` only for the node that needs agentic execution.

```python
import pathlib
import typing

import langgraph.graph

from langgraph_codex.execution import ExecutionResult
from langgraph_codex.graph import create_codex_node
from langgraph_codex.runtime import create_codex_executor, ensure_codex_authorized


class ReviewState(typing.TypedDict, total=False):
    workspace_path: typing.Required[pathlib.Path]
    repo_context: dict[str, list[str]]
    codex_result: ExecutionResult
    validation_message: str


def inspect_codebase(_state: ReviewState) -> dict[str, dict[str, list[str]]]:
    return {
        "repo_context": {
            "package_files": ["langgraph_codex/graph/nodes.py"],
            "test_files": ["tests/test_graphs.py", "tests/test_execution.py"],
            "example_files": ["examples/00_existing_langgraph_graph.py"],
        }
    }


def prompt_for_codex(state: ReviewState) -> str:
    return "\n".join(
        [
            "Audit the existing langgraph-codex repository.",
            f"Repository context: {state.get('repo_context', {})}",
            "Write codebase_audit.md with concrete findings about tests and examples.",
            "Do not invent an unrelated service configuration.",
        ]
    )


def validate_result(state: ReviewState) -> dict[str, str]:
    result = state.get("codex_result")
    if result is None:
        return {"validation_message": "Codex did not return a result."}
    if result.returncode != 0:
        return {"validation_message": f"Codex failed: {result.stderr}"}

    return {"validation_message": "Codex completed. Validate codebase_audit.md next."}


ensure_codex_authorized()
codex_node = create_codex_node(
    executor=create_codex_executor(timeout_seconds=300),
    prompt_builder=prompt_for_codex,
    workspace_path=lambda state: state["workspace_path"],
)


def draft_audit(state: ReviewState) -> dict[str, ExecutionResult]:
    update = codex_node(state)
    result = update.get("codex_result")
    if not isinstance(result, ExecutionResult):
        raise TypeError("Codex node did not return codex_result.")

    return {"codex_result": result}

graph = langgraph.graph.StateGraph(ReviewState)
graph.add_node("inspect_codebase", inspect_codebase)
graph.add_node("draft_audit", draft_audit)
graph.add_node("validate_result", validate_result)
graph.add_edge(langgraph.graph.START, "inspect_codebase")
graph.add_edge("inspect_codebase", "draft_audit")
graph.add_edge("draft_audit", "validate_result")
graph.add_edge("validate_result", langgraph.graph.END)

result = graph.compile().invoke({"workspace_path": pathlib.Path.cwd()})
print(result["validation_message"])
```

That is the intended shape:

```text
prepare deterministic context -> call Codex node -> validate deterministically -> route
```

## Authorization

Real Codex execution requires the Codex CLI and credentials. The runtime helpers load local `.env` values and map `OPEN_AI_SECRET_KEY` to `OPENAI_API_KEY` when needed.

```bash
cp .env.example .env
```

Then set the relevant values:

```text
OPEN_AI_SECRET_KEY=...
OPEN_AI_KEY_NAME=github-actions
OPEN_AI_MODEL=
```

See [docs/codex-authorization.md](docs/codex-authorization.md) for local setup, GitHub Actions secrets, and CI guidance.

## Typed Codex Options

The Codex-facing defaults are enum-backed and exported for application code. Plain strings still work when you need a newer CLI value, but stable options no longer need naked literals:

```python
import pathlib

from langgraph_codex import CodexApprovalPolicy, CodexSandbox, ExecutionOption
from langgraph_codex.execution import CodexExecutor, ExecutionRequest

executor = CodexExecutor(
    sandbox=CodexSandbox.WORKSPACE_WRITE,
    approval_policy=CodexApprovalPolicy.NEVER,
    profile="ci",
    config_overrides={"reasoning.effort": "low"},
)

request = ExecutionRequest(
    workspace_path=pathlib.Path.cwd(),
    prompt="Run the bounded migration and report changed files.",
    options={
        ExecutionOption.MODEL.value: "gpt-5.1",
        ExecutionOption.TIMEOUT_SECONDS.value: 300,
        ExecutionOption.EXTRA_ARGS.value: ["--json"],
    },
)
```

Useful enums include:

- `CodexSandbox`: `READ_ONLY`, `WORKSPACE_WRITE`, `DANGER_FULL_ACCESS`
- `CodexApprovalPolicy`: `UNTRUSTED`, `ON_FAILURE`, `ON_REQUEST`, `NEVER`
- `ExecutionOption`: per-request model, timeout, sandbox, approval policy, profile, extra args, config overrides, writable roots, git-repo-check behavior, JSON events, output schema path, and output-last-message path

Dangerous bypass flags and equivalent config overrides are rejected before subprocess execution.

## Structured AI Outputs

Codex can produce machine-readable output for downstream graph nodes. Use `OUTPUT_SCHEMA_PATH` to pass a JSON Schema file to the CLI, `OUTPUT_LAST_MESSAGE_PATH` to persist the final response, and `JSON_EVENTS` to parse JSONL stdout into structured graph state:

```python
import pathlib

from langgraph_codex import ExecutionOption
from langgraph_codex.execution import ExecutionRequest
from langgraph_codex.utils.validation import require_structured_output

request = ExecutionRequest(
    workspace_path=pathlib.Path.cwd(),
    prompt="Return a JSON object with status and changed_files.",
    options={
        ExecutionOption.OUTPUT_SCHEMA_PATH.value: "schemas/remediation-result.schema.json",
        ExecutionOption.OUTPUT_LAST_MESSAGE_PATH.value: "codex-result.json",
        ExecutionOption.JSON_EVENTS.value: True,
    },
)

validators = [require_structured_output("last_message_json")]
```

When the last message contains valid JSON, `ExecutionResult.structured_outputs` includes:

- `last_message_path`
- `last_message`
- `last_message_json`
- `json_events`

This keeps AI output useful for routing, validation, and persistence without scraping free-form stdout.

## Prompt Rendering

You can still pass normal strings to `create_codex_node`, but structured prompts are now first-class. A `prompt_builder` may return `PromptSpec`; the node renders it before calling the executor.

```python
from langgraph_codex import PromptFile, PromptSection, PromptSpec


def prompt_for_codex(state: ReviewState) -> PromptSpec:
    return PromptSpec(
        title="Patch billing export",
        objective="Fix the missing purchase order references.",
        context_sections=[
            PromptSection("Ticket", state["ticket"]),
            PromptSection("Repository notes", "\n".join(state["repo_context"]["files"])),
        ],
        files=[PromptFile("services/billing/export.py", "Exporter under review.")],
        acceptance_criteria=[
            "Existing billing tests pass.",
            "The export includes purchase order references.",
        ],
    )
```

For custom prompt layouts, use the Markdown renderer options:

```python
from langgraph_codex import MarkdownPromptRenderOptions, PromptBlock
from langgraph_codex.utils.prompts import render_prompt

prompt = render_prompt(
    prompt_for_codex(state),
    options=MarkdownPromptRenderOptions(
        section_order=(
            PromptBlock.OBJECTIVE,
            PromptBlock.CONTEXT,
            PromptBlock.FILES,
            PromptBlock.ACCEPTANCE_CRITERIA,
        ),
        bullet="*",
    ),
)
```

The default renderer preserves the stable Markdown order used by earlier releases.

For common Codex tasks, use typed prompt recipes that return ordinary `PromptSpec`
objects:

```python
from langgraph_codex.prompts import PromptSpec, create_implementation_prompt


def prompt_for_codex(state: ReviewState) -> PromptSpec:
    return create_implementation_prompt(
        objective="Patch the billing export workflow.",
        requirements=[
            "Include purchase order references in every exported row.",
            "Keep the existing CSV schema order stable.",
        ],
        validation_commands=["uv run pytest tests/test_billing_export.py"],
        files=[("services/billing/export.py", "CSV export implementation.")],
    )
```

Recipe helpers are available for code review, implementation, test generation,
documentation updates, and migration planning. They only assemble structured
prompt content; rendering and graph execution continue to use the normal
`PromptSpec` path.

## Validation

Codex output should be checked by deterministic code before anything downstream consumes it.

Good validators check files, schemas, command output, tests, checksums, and domain-specific facts:

```python
from langgraph_codex.utils.validation import require_files

validators = [require_files(["remediation_plan.md"])]
```

You can use the built-in validation helpers, or write normal LangGraph nodes that inspect your application state and route from there.

## Examples

The examples are intentionally few and close to the production integration shape:

- [examples/01_real_codex_node.py](examples/01_real_codex_node.py): real Codex inside a plain LangGraph graph, with deterministic preprocessing and validation.
- [examples/00_existing_langgraph_graph.py](examples/00_existing_langgraph_graph.py): offline version of the same idea using `FakeExecutor`.
- [examples/02_codebase_audit.py](examples/02_codebase_audit.py): real Codex codebase audit graph that gathers repository context and validates `codebase_audit.md`.

Run:

```bash
uv run python3 -m examples.00_existing_langgraph_graph
uv run python3 -m examples.01_real_codex_node
uv run python3 -m examples.02_codebase_audit
```

## Convenience Builders

For small tests and quick starts, the package also includes complete graph builders:

- `build_context_only_graph()`
- `build_execution_graph()`
- `build_retry_graph()`

Most production applications should prefer `create_codex_node` inside their own graph.

Builder internals use exported graph constants instead of loose strings:

```python
from langgraph_codex.graph import GraphNode, ReviewRoute

assert GraphNode.REVIEW.value == "review"
assert ReviewRoute.RETRY.value == "retry"
```

Those constants are useful when composing custom graphs, asserting route behavior, or instrumenting node-level metrics.

## Advanced Node Usage

`create_codex_node` supports static and dynamic metadata/options, custom result keys, custom result mapping, state-derived workspaces, and structured prompt builders:

```python
codex_node = create_codex_node(
    executor=executor,
    prompt_builder=prompt_for_codex,
    workspace_path=lambda state: state["workspace_path"],
    metadata={"workflow": "billing-remediation"},
    metadata_builder=lambda state: {"ticket_id": state["ticket_id"]},
    options={ExecutionOption.TIMEOUT_SECONDS.value: 300},
    options_builder=lambda state: {ExecutionOption.MODEL.value: state["model"]},
    result_key="remediation_result",
)
```

This lets a deterministic graph choose the Codex model, timeout, profile, writable roots, and validation context per task without rebuilding the executor.

## CI/CD

The repository validates:

- GitHub Actions workflow syntax with actionlint;
- Ruff formatting and linting;
- Pylint with `10.00/10`;
- strict mypy and Pyright;
- Python compile checks;
- pytest across Python 3.11, 3.12, and 3.13;
- offline examples;
- wheel and source distribution build plus Twine metadata validation;
- optional real Codex smoke checks through workflow dispatch.

Release publishing uses PyPI trusted publishing through the `pypi` GitHub environment.

## Design Notes

The package deliberately stays small. It does not own memory, UI, checkpoint storage, broad model selection, or repository policy. Those concerns belong in the graph and infrastructure you already control.

Read more in [docs/design-philosophy.md](docs/design-philosophy.md).
Planned follow-up work is tracked in [docs/follow-up-work.md](docs/follow-up-work.md).

## Testing Without Codex

Use `FakeExecutor` when you want CI-safe tests, examples, or local development without calling the Codex CLI.

```python
from langgraph_codex.execution import FakeExecutor

executor = FakeExecutor(stdout="Priority: medium. Area: billing exports.")
```

`FakeExecutor` records requests and returns deterministic results, so you can assert prompt content, metadata, options, and graph routing without network credentials.

## Development

```bash
make sync
make format
make check
```

Useful targets include `make quality`, `make test`, `make package-check`, `make examples`, `make examples-codex`, and `make clean`.

## License

MIT
