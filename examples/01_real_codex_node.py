import hashlib
import json
import pathlib
import tempfile
from typing import Required, TypedDict, cast

from langgraph.graph import END, START
from langgraph.graph.state import CompiledStateGraph, StateGraph

from langgraph_codex import PromptFile, PromptSection, PromptSpec
from langgraph_codex.execution import ExecutionResult
from langgraph_codex.graph import create_codex_node
from langgraph_codex.runtime import create_codex_executor, ensure_codex_authorized, print_section

REMEDIATION_PATH = "remediation_plan.md"
CONFIG_PATH = "service_config.json"
EXPECTED_FINDING_COUNT = 3


class ConfigReviewState(TypedDict, total=False):
    workspace_path: Required[pathlib.Path]
    config_path: str
    config_sha256: str
    findings: list[str]
    codex_result: ExecutionResult
    validation_passed: bool
    validation_message: str


def write_service_config(workspace_path: pathlib.Path) -> pathlib.Path:
    config_path = workspace_path / CONFIG_PATH
    config_path.write_text(
        json.dumps(
            {
                "service": "appointment-reminders",
                "retry_attempts": 6,
                "timeout_seconds": 45,
                "batch_size": 500,
                "channels": ["email", "sms"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return config_path


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_config(state: ConfigReviewState) -> dict[str, str | list[str]]:
    workspace_path = state["workspace_path"]
    config_path = workspace_path / CONFIG_PATH
    config = cast(dict[str, object], json.loads(config_path.read_text(encoding="utf-8")))
    findings: list[str] = []
    if _int_config_value(config, "retry_attempts") > 3:
        findings.append("retry_attempts exceeds 3")
    if _int_config_value(config, "timeout_seconds") > 30:
        findings.append("timeout_seconds exceeds 30")
    if _int_config_value(config, "batch_size") > 250:
        findings.append("batch_size exceeds 250")

    return {
        "config_path": config_path.name,
        "config_sha256": sha256_file(config_path),
        "findings": findings,
    }


def build_prompt(state: ConfigReviewState) -> PromptSpec:
    findings = cast(list[str], state.get("findings", []))
    return PromptSpec(
        title="Service Configuration Remediation",
        objective=f"Review {CONFIG_PATH} and create {REMEDIATION_PATH}.",
        context_sections=[
            PromptSection("Deterministic Findings", json.dumps(findings, indent=2)),
        ],
        files=[PromptFile(CONFIG_PATH, "Source configuration. Do not modify this file.")],
        constraints=[f"Do not modify {CONFIG_PATH}."],
        acceptance_criteria=[
            f"{REMEDIATION_PATH} exists.",
            f"The plan includes the exact line finding_count={EXPECTED_FINDING_COUNT}.",
            "The plan mentions retry_attempts, timeout_seconds, and batch_size.",
        ],
    )


def validate_output(state: ConfigReviewState) -> dict[str, bool | str]:
    workspace_path = state["workspace_path"]
    config_path = workspace_path / str(state.get("config_path", CONFIG_PATH))
    remediation_path = workspace_path / REMEDIATION_PATH
    if not remediation_path.exists():
        return {
            "validation_passed": False,
            "validation_message": f"Missing {REMEDIATION_PATH}.",
        }
    if sha256_file(config_path) != str(state.get("config_sha256", "")):
        return {
            "validation_passed": False,
            "validation_message": "service_config.json was modified.",
        }

    remediation_text = remediation_path.read_text(encoding="utf-8")
    missing = [
        fragment
        for fragment in ["finding_count=3", "retry_attempts", "timeout_seconds", "batch_size"]
        if fragment not in remediation_text
    ]
    if missing:
        return {
            "validation_passed": False,
            "validation_message": f"Missing remediation details: {', '.join(missing)}.",
        }

    return {
        "validation_passed": True,
        "validation_message": "Remediation plan is present and source config is unchanged.",
    }


def build_graph() -> CompiledStateGraph[
    ConfigReviewState,
    None,
    ConfigReviewState,
    ConfigReviewState,
]:
    graph: StateGraph[
        ConfigReviewState,
        None,
        ConfigReviewState,
        ConfigReviewState,
    ] = StateGraph(ConfigReviewState)
    codex_node = create_codex_node(
        executor=create_codex_executor(timeout_seconds=300),
        prompt_builder=build_prompt,
        workspace_path=lambda state: state["workspace_path"],
    )

    def draft_remediation(state: ConfigReviewState) -> dict[str, ExecutionResult]:
        update = codex_node(state)
        result = update.get("codex_result")
        if not isinstance(result, ExecutionResult):
            raise TypeError("Codex node did not return an ExecutionResult at codex_result.")

        return {"codex_result": result}

    graph.add_node("inspect_config", inspect_config)
    graph.add_node("draft_remediation", draft_remediation)
    graph.add_node("validate_output", validate_output)
    graph.add_edge(START, "inspect_config")
    graph.add_edge("inspect_config", "draft_remediation")
    graph.add_edge("draft_remediation", "validate_output")
    graph.add_edge("validate_output", END)
    return graph.compile()


def _int_config_value(config: dict[str, object], key: str) -> int:
    value = config.get(key)
    if not isinstance(value, int):
        raise TypeError(f"{key} must be an integer in {CONFIG_PATH}.")

    return value


def main() -> None:
    ensure_codex_authorized()
    with tempfile.TemporaryDirectory(prefix="langgraph-codex-config-") as temporary_directory:
        workspace_path = pathlib.Path(temporary_directory)
        write_service_config(workspace_path)
        result = build_graph().invoke({"workspace_path": workspace_path})

        print_section("Workspace", workspace_path)
        print_section("Validation", result["validation_message"])
        print_section("Codex stdout", result["codex_result"].stdout or "(empty)")
        print_section(
            "Remediation", (workspace_path / REMEDIATION_PATH).read_text(encoding="utf-8")
        )


if __name__ == "__main__":
    main()
