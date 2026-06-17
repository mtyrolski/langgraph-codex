import dataclasses
from collections.abc import Callable

import langgraph_codex.execution.base as execution_base
from langgraph_codex.types import StateValue

FakeResponder = Callable[
    [execution_base.ExecutionRequest],
    execution_base.ExecutionResult,
]


@dataclasses.dataclass
class FakeExecutor(execution_base.Executor):
    stdout: str = "Fake executor completed."
    stderr: str = ""
    returncode: int = 0
    structured_outputs: dict[str, StateValue] = dataclasses.field(default_factory=dict)
    response: StateValue = None
    responder: FakeResponder | None = None
    requests: list[execution_base.ExecutionRequest] = dataclasses.field(default_factory=list)

    def execute(
        self,
        request: execution_base.ExecutionRequest,
    ) -> execution_base.ExecutionResult:
        """Record the request and return a deterministic result for tests."""
        self.requests.append(request)
        if self.responder is not None:
            return self.responder(request)

        return execution_base.ExecutionResult(
            stdout=self.stdout,
            stderr=self.stderr,
            returncode=self.returncode,
            structured_outputs=dict(self.structured_outputs),
            raw_response=self.response,
        )


FakeBackend = FakeExecutor
