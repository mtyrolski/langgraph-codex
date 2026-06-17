# Follow-Up Work

This roadmap keeps `langgraph-codex` focused on deterministic LangGraph ownership while improving the Codex node as a bounded AI execution primitive.

## Near Term

- Add more structured-output validators for common JSON object, list, and schema checks.
- Add examples that route on `ExecutionResult.structured_outputs["last_message_json"]`.
- Add schema-file helpers that write temporary JSON Schema files for Codex `--output-schema`.
- Add observability hooks for prompt length, retry count, command arguments, and validation results.

## Medium Term

- Add typed prompt recipes for common Codex tasks: code review, implementation, test generation, docs updates, and migration planning.
- Add policy helpers that restrict writable roots, profiles, sandbox modes, and model choices by workflow.
- Add optional JSONL event summarizers for Codex `--json` output.
- Add richer retry strategies that can modify prompt context after failed deterministic validation.

## Deferred

- Provider abstraction beyond Codex CLI. This should stay out until a real application needs it.
- Persistent memory. LangGraph applications should own persistence and checkpointing.
- Autonomous repository-wide orchestration. This package should keep Codex as one bounded node.
