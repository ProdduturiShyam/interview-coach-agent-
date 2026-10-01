"""Browser-native, hands-free interview component."""

from pathlib import Path

import streamlit.components.v1 as components

_component = components.declare_component(
    "live_interview",
    path=str(Path(__file__).parent / "frontend"),
)


def live_interview(question: str = "", *, active: bool = True, greeting: str = "",
                   replay: int = 0, mode: str = "interview", key: str = "live") -> dict:
    """Speak ``question``, listen until the candidate pauses, and return its transcript."""
    return _component(
        question=question,
        active=active,
        greeting=greeting,
        replay=replay,
        mode=mode,
        key=key,
        default={},
    )
