from enum import StrEnum
from typing import Final

import langgraph_codex.options as codex_options


class GraphNode(StrEnum):
    BUILD_CONTEXT = "build_context"
    RENDER_PROMPT = "render_prompt"
    EXECUTE = "execute"
    REVIEW = "review"
    RETRY = "retry_node"


class ReviewRoute(StrEnum):
    SUCCESS = "success"
    RETRY = "retry"
    FAIL = "fail"


DEFAULT_MAX_RETRIES: Final[int] = codex_options.DEFAULT_MAX_RETRIES

__all__ = [
    "DEFAULT_MAX_RETRIES",
    "GraphNode",
    "ReviewRoute",
]
