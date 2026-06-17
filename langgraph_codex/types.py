from collections.abc import Callable, Mapping, MutableMapping, Sequence
from typing import Any, TypeAlias

StateValue: TypeAlias = Any
StateMapping: TypeAlias = Mapping[str, StateValue]
MutableStateMapping: TypeAlias = MutableMapping[str, StateValue]
StateUpdate: TypeAlias = dict[str, StateValue]
Metadata: TypeAlias = dict[str, StateValue]
ExecutionOptions: TypeAlias = dict[str, StateValue]
JsonEventSummarizer: TypeAlias = Callable[
    [Sequence[StateValue]],
    Mapping[str, StateValue],
]
