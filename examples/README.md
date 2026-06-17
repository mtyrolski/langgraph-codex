# Examples

The examples show the intended integration shape: keep your LangGraph app, then replace one bounded node with a Codex-backed node.

Run the offline example:

```bash
uv run python3 -m examples.00_existing_langgraph_graph
```

Run the real Codex example after installing and authenticating the Codex CLI:

```bash
uv run python3 -m examples.01_real_codex_node
```

Run only the repository audit example:

```bash
uv run python3 -m examples.02_codebase_audit
```

## Index

| File | Runtime | Shows |
| --- | --- | --- |
| `00_existing_langgraph_graph.py` | Offline | A normal `langgraph.graph.StateGraph` where one node is backed by `create_codex_node` and `FakeExecutor`. |
| `01_real_codex_node.py` | Real Codex | A normal LangGraph service-config review graph with deterministic preprocessing, a Codex remediation node, and deterministic validation. |
| `02_codebase_audit.py` | Real Codex | A repository audit graph that gathers real codebase context, asks Codex for `codebase_audit.md`, and validates the artifact. |

## Pattern

1. Build context with deterministic Python.
2. Call Codex through one explicit graph node.
3. Store the executor result in application state.
4. Validate files or structured output deterministically.
5. Route or finish from your own LangGraph graph.

## Quality Rules

The examples are written as reference integrations, not throwaway snippets:

- typed `TypedDict` state with `Required` workspace paths;
- typed `StateGraph` / `CompiledStateGraph` return values;
- structured `PromptSpec` prompts instead of ad hoc prompt strings where Codex is doing real work;
- deterministic validation after Codex execution;
- no qualified `typing.*` shortcuts;
- no broad graph casts in example code.

See [docs/design-philosophy.md](../docs/design-philosophy.md) for the reasoning behind this shape and [docs/codex-authorization.md](../docs/codex-authorization.md) for local and CI authorization.
