import abc
import dataclasses
import pathlib

from langgraph_codex.types import StateValue


@dataclasses.dataclass
class ExecutionRequest:
    workspace_path: pathlib.Path
    prompt: str
    metadata: dict[str, StateValue] = dataclasses.field(default_factory=dict)
    options: dict[str, StateValue] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class ExecutionResult:
    stdout: str
    stderr: str
    returncode: int
    structured_outputs: dict[str, StateValue] = dataclasses.field(default_factory=dict)
    raw_response: StateValue = None

    @property
    def succeeded(self) -> bool:
        """Return whether the executor completed with exit code zero."""
        return self.returncode == 0


class Executor(abc.ABC):
    @abc.abstractmethod
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        raise NotImplementedError


BackendRequest = ExecutionRequest
BackendResult = ExecutionResult
ExecutionBackend = Executor
