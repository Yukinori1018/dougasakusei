"""LangGraph DAG that wires all nodes."""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes import (
    bgm,
    compliance,
    factcheck,
    metadata,
    research,
    script,
    shorts,
    subtitle,
    timeline,
    topic,
    visual,
    voice,
)
from .schemas import PipelineState


def build_graph():
    g = StateGraph(PipelineState)

    g.add_node("topic", topic.run)
    g.add_node("research", research.run)
    g.add_node("script", script.run)
    g.add_node("factcheck", factcheck.run)
    g.add_node("voice", voice.run)
    g.add_node("visual", visual.run)
    g.add_node("subtitle", subtitle.run)
    g.add_node("bgm", bgm.run)
    g.add_node("metadata", metadata.run)
    g.add_node("compliance", compliance.run)
    g.add_node("timeline", timeline.run)
    g.add_node("shorts", shorts.run)

    g.set_entry_point("topic")
    g.add_edge("topic", "research")
    g.add_edge("research", "script")
    g.add_edge("script", "factcheck")
    # voice / visual / subtitle / metadata / bgm can be sequential — they're cheap
    # and we keep state.simple. Parallel branches would force pydantic state merges.
    g.add_edge("factcheck", "voice")
    g.add_edge("voice", "visual")
    g.add_edge("visual", "subtitle")
    g.add_edge("subtitle", "bgm")
    g.add_edge("bgm", "metadata")
    g.add_edge("metadata", "compliance")
    g.add_edge("compliance", "timeline")
    g.add_edge("timeline", "shorts")
    g.add_edge("shorts", END)

    return g.compile()
