import pathlib
from typing import Required, TypedDict

from langgraph.graph import END, START
from langgraph.graph.state import CompiledStateGraph, StateGraph

from langgraph_codex import PromptSection, PromptSpec
from langgraph_codex.execution import ExecutionResult, FakeExecutor
from langgraph_codex.graph import create_codex_node


class SupportState(TypedDict, total=False):
    workspace_path: Required[pathlib.Path]
    ticket: str
    deterministic_summary: str
    codex_result: ExecutionResult
    customer_reply: str


def load_ticket(state: SupportState) -> dict[str, str]:
    _ = state
    return {
        "ticket": (
            "Enterprise customer reports that exported billing reports omit purchase order "
            "references for several invoices."
        )
    }


def summarize_ticket(state: SupportState) -> dict[str, str]:
    ticket = str(state.get("ticket", ""))
    keywords = [
        keyword
        for keyword in ["enterprise", "billing", "purchase order", "invoice"]
        if keyword in ticket.lower()
    ]
    return {"deterministic_summary": f"keywords={', '.join(keywords)}"}


def build_prompt(state: SupportState) -> PromptSpec:
    ticket = str(state.get("ticket", ""))
    deterministic_summary = str(state.get("deterministic_summary", ""))
    return PromptSpec(
        title="Support Triage",
        objective="Draft a concise internal support response.",
        context_sections=[
            PromptSection("Ticket", ticket),
            PromptSection("Deterministic Summary", deterministic_summary),
        ],
        acceptance_criteria=[
            "Include priority.",
            "Include affected area.",
            "Include next action.",
        ],
    )


def finalize_reply(state: SupportState) -> dict[str, str]:
    codex_result = state.get("codex_result")
    if not isinstance(codex_result, ExecutionResult):
        raise TypeError("draft_reply did not return an ExecutionResult.")

    structured_reply = codex_result.structured_outputs.get("last_message_json", {})
    if isinstance(structured_reply, dict):
        priority = str(structured_reply.get("priority", "unknown"))
        area = str(structured_reply.get("area", "unknown"))
        next_action = str(structured_reply.get("next_action", codex_result.stdout))
        return {
            "customer_reply": (f"Priority: {priority}\nArea: {area}\nNext action: {next_action}")
        }

    return {"customer_reply": codex_result.stdout}


def build_graph() -> CompiledStateGraph[SupportState, None, SupportState, SupportState]:
    executor = FakeExecutor(
        stdout=(
            "Priority: medium\n"
            "Area: billing exports\n"
            "Next action: inspect export field mapping for purchase order references."
        ),
        structured_outputs={
            "last_message_json": {
                "priority": "medium",
                "area": "billing exports",
                "next_action": ("inspect export field mapping for purchase order references."),
            }
        },
    )
    codex_node = create_codex_node(
        executor=executor,
        prompt_builder=build_prompt,
        workspace_path=lambda state: state["workspace_path"],
    )

    def draft_reply(state: SupportState) -> dict[str, ExecutionResult]:
        update = codex_node(state)
        result = update.get("codex_result")
        if not isinstance(result, ExecutionResult):
            raise TypeError("Codex node did not return an ExecutionResult at codex_result.")

        return {"codex_result": result}

    graph: StateGraph[SupportState, None, SupportState, SupportState] = StateGraph(SupportState)
    graph.add_node("load_ticket", load_ticket)
    graph.add_node("summarize_ticket", summarize_ticket)
    graph.add_node("draft_reply", draft_reply)
    graph.add_node("finalize_reply", finalize_reply)
    graph.add_edge(START, "load_ticket")
    graph.add_edge("load_ticket", "summarize_ticket")
    graph.add_edge("summarize_ticket", "draft_reply")
    graph.add_edge("draft_reply", "finalize_reply")
    graph.add_edge("finalize_reply", END)
    return graph.compile()


def main() -> None:
    result = build_graph().invoke({"workspace_path": pathlib.Path.cwd()})
    print(result["customer_reply"])


if __name__ == "__main__":
    main()
