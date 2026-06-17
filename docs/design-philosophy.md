# Design Philosophy

`langgraph-codex` is a small adapter layer for putting Codex inside a LangGraph application.

It is designed for teams that already have graph-shaped workflows and want one step to use Codex without turning the whole application into a hidden agent framework.

## What This Package Is

The package provides:

- executor interfaces for local, fake, and `codex exec` execution;
- a `create_codex_node` adapter for existing LangGraph graphs;
- optional convenience graph builders for simple workflows;
- deterministic prompt rendering and validation helpers.

The center of the library is not a wrapper graph. The center is a normal LangGraph node that can sit inside your graph.

## The Core Pattern

Start with an application graph you own:

```text
load input -> normalize context -> draft output -> validate -> route
```

When deterministic code is not enough, replace the bounded synthesis or remediation step:

```text
load input -> normalize context -> Codex node -> validate -> route
```

The graph stays yours. State shape, routing, persistence, checkpointing, and domain policy stay in your application.
Configure LangGraph persistence and checkpointers in that application layer, not inside this adapter package.

## What Stays Deterministic

Keep these steps in ordinary Python whenever possible:

- parsing source files and external inputs;
- building compact context for Codex;
- deciding which files Codex may touch;
- routing success, retry, and failure paths;
- validating output files, JSON, markers, checksums, tests, and commands;
- recording artifacts and audit metadata.

Deterministic code is easier to test, review, and operate. Codex should receive clear context and bounded work, not vague ownership of the whole workflow.

## What Codex Should Do

Good Codex nodes perform work such as:

- drafting a remediation plan from deterministic findings;
- editing a narrow set of files in a prepared workspace;
- synthesizing a report from curated notes;
- proposing a patch after tests and constraints are already known;
- explaining or transforming content where rules alone are too brittle.

The node should have a clear prompt, a clear workspace, and deterministic validation after it runs.

## What This Package Does Not Own

The package deliberately does not own:

- chat history or memory;
- UI state;
- LangGraph checkpoint storage;
- broad model abstractions;
- repository automation policy;
- test strategy for your application;
- hidden retries or hidden routing.

Those concerns belong in your application graph or infrastructure.
If a workflow needs persistent memory or checkpoint recovery, wire it into the LangGraph app that compiles and runs the graph.

## Recommended Workflow Shape

Use this shape for production workflows:

```text
prepare context -> call Codex node -> validate deterministically -> route
```

Validation should be specific to the task. Prefer file existence checks, schema checks, command checks, checksums, and domain assertions over subjective review.

## Example Selection Principles

The examples in this repository are intentionally few:

- one offline example that runs in CI;
- one real Codex example that uses a temporary workspace;
- no repeated examples that differ only by domain nouns;
- no example that hides LangGraph behind a package-specific builder when the point is integration.

Convenience builders still exist for quick starts and tests, but the primary adoption path is the node adapter.

## Operational Safety

Use temporary or scoped workspaces when evaluating Codex behavior. Keep credentials in environment variables or CI secrets. Do not pass dangerous bypass flags to the Codex CLI. Validate every important output deterministically before downstream systems consume it.

For CI and local authorization details, see [codex-authorization.md](codex-authorization.md).

## When Not To Use It

Do not use this package when the task is fully deterministic, when you want a chat-first agent framework, or when a broader platform should own memory, tools, scheduling, and policy.

In those cases, use LangGraph directly or choose a larger agent framework. This library is for the narrower case: one explicit Codex execution step inside a graph you already understand.
