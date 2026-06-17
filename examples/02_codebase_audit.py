import json
import pathlib
from typing import Required, TypedDict

from langgraph.graph import END, START
from langgraph.graph.state import CompiledStateGraph, StateGraph

from langgraph_codex import PromptSection, PromptSpec
from langgraph_codex.execution import ExecutionResult
from langgraph_codex.graph import create_codex_node
from langgraph_codex.runtime import create_codex_executor, ensure_codex_authorized, print_section

AUDIT_PATH = "codebase_audit.md"
REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]


class RepoContext(TypedDict):
    project_files: list[str]
    package_files: list[str]
    test_files: list[str]
    example_files: list[str]
    readme_testing_claims: str
    make_check_target: str


class AuditState(TypedDict, total=False):
    workspace_path: Required[pathlib.Path]
    repo_context: RepoContext
    codex_result: ExecutionResult
    validation_passed: bool
    validation_message: str


def list_repo_files(workspace_path: pathlib.Path, prefix: str) -> list[str]:
    root = workspace_path / prefix
    if not root.exists():
        return []

    return [
        str(path.relative_to(workspace_path))
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    ]


def read_section(path: pathlib.Path, heading: str) -> str:
    if not path.exists():
        return ""

    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        start = lines.index(heading)
    except ValueError:
        return ""

    body: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        if line.strip():
            body.append(line)

    return "\n".join(body)


def inspect_codebase(state: AuditState) -> dict[str, RepoContext]:
    workspace_path = state["workspace_path"]
    repo_context: RepoContext = {
        "project_files": [
            "pyproject.toml",
            "Makefile",
            "README.md",
            "docs/design-philosophy.md",
            "docs/codex-authorization.md",
        ],
        "package_files": list_repo_files(workspace_path, "langgraph_codex"),
        "test_files": list_repo_files(workspace_path, "tests"),
        "example_files": list_repo_files(workspace_path, "examples"),
        "readme_testing_claims": read_section(workspace_path / "README.md", "## CI/CD"),
        "make_check_target": "make check -> quality, test, package-check, examples",
    }
    return {"repo_context": repo_context}


def prompt_for_codex(state: AuditState) -> PromptSpec:
    repo_context = state.get("repo_context")
    if repo_context is None:
        raise ValueError("inspect_codebase did not populate repo_context.")

    return PromptSpec(
        title="Repository Test And Example Audit",
        objective=f"Audit this existing repository and write {AUDIT_PATH}.",
        context_sections=[
            PromptSection(
                "Repository Context",
                json.dumps(repo_context, indent=2, sort_keys=True),
            )
        ],
        constraints=[
            "Do not invent a service config or unrelated domain.",
            f"Write only {AUDIT_PATH} unless a source edit is required to make the audit truthful.",
        ],
        acceptance_criteria=[
            "Reference concrete files from langgraph_codex/, tests/, examples/, and README.md.",
            "Identify coverage that is already meaningful.",
            (
                "Identify missing or weak coverage around real Codex execution boundaries, "
                "workspace/path safety, validation behavior, and README/example consistency."
            ),
            "Separate high-signal findings from nice-to-have cleanup.",
            "Include the exact line audit_scope=existing_codebase.",
        ],
    )


def validate_audit(state: AuditState) -> dict[str, bool | str]:
    result = state.get("codex_result")
    if result is None:
        return {
            "validation_passed": False,
            "validation_message": "Missing codex_result in graph state.",
        }

    if result.returncode != 0:
        return {
            "validation_passed": False,
            "validation_message": f"Codex failed: {result.stderr or result.stdout}",
        }

    workspace_path = state["workspace_path"]
    audit_path = workspace_path / AUDIT_PATH
    if not audit_path.exists():
        return {
            "validation_passed": False,
            "validation_message": f"Missing {AUDIT_PATH}.",
        }

    audit_text = audit_path.read_text(encoding="utf-8")
    required_fragments = [
        "audit_scope=existing_codebase",
        "langgraph_codex/",
        "tests/",
        "examples/",
        "README.md",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in audit_text]
    if missing:
        return {
            "validation_passed": False,
            "validation_message": f"Audit is too generic; missing: {', '.join(missing)}.",
        }

    return {
        "validation_passed": True,
        "validation_message": f"{AUDIT_PATH} was created for the existing codebase.",
    }


def build_graph() -> CompiledStateGraph[AuditState, None, AuditState, AuditState]:
    graph: StateGraph[AuditState, None, AuditState, AuditState] = StateGraph(AuditState)
    codex_node = create_codex_node(
        executor=create_codex_executor(timeout_seconds=300),
        prompt_builder=prompt_for_codex,
        workspace_path=lambda state: state["workspace_path"],
    )

    def draft_codebase_audit(state: AuditState) -> dict[str, ExecutionResult]:
        update = codex_node(state)
        result = update.get("codex_result")
        if not isinstance(result, ExecutionResult):
            raise TypeError("Codex node did not return an ExecutionResult at codex_result.")

        return {"codex_result": result}

    graph.add_node("inspect_codebase", inspect_codebase)
    graph.add_node("draft_codebase_audit", draft_codebase_audit)
    graph.add_node("validate_audit", validate_audit)
    graph.add_edge(START, "inspect_codebase")
    graph.add_edge("inspect_codebase", "draft_codebase_audit")
    graph.add_edge("draft_codebase_audit", "validate_audit")
    graph.add_edge("validate_audit", END)
    return graph.compile()


def main() -> None:
    ensure_codex_authorized()
    result = build_graph().invoke({"workspace_path": REPOSITORY_ROOT})

    print_section("Validation", result.get("validation_message", "Validation did not run."))
    codex_result = result.get("codex_result")
    if codex_result is not None:
        print_section("Codex stdout", codex_result.stdout or "(empty)")
    if (REPOSITORY_ROOT / AUDIT_PATH).exists():
        print_section("Audit", (REPOSITORY_ROOT / AUDIT_PATH).read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
