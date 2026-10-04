"""Thin wrapper around the Anthropic client that keeps count of tokens and cost."""
from __future__ import annotations

from dataclasses import dataclass

from . import config


@dataclass
class Usage:
    calls: int = 0
    input: int = 0
    output: int = 0
    cache_write: int = 0
    cache_read: int = 0

    def add(self, usage) -> None:
        self.calls += 1
        self.input += getattr(usage, "input_tokens", 0) or 0
        self.output += getattr(usage, "output_tokens", 0) or 0
        self.cache_write += getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.cache_read += getattr(usage, "cache_read_input_tokens", 0) or 0

    def cost(self) -> float | None:
        if config.PRICE_INPUT is None or config.PRICE_OUTPUT is None:
            return None
        input_cost = (
            self.input
            + self.cache_write * config.CACHE_WRITE_MULTIPLIER
            + self.cache_read * config.CACHE_READ_MULTIPLIER
        ) * config.PRICE_INPUT
        return round((input_cost + self.output * config.PRICE_OUTPUT) / 1_000_000, 4)

    def as_dict(self) -> dict:
        return {"calls": self.calls, "input_tokens": self.input, "output_tokens": self.output,
                "cache_write_tokens": self.cache_write, "cache_read_tokens": self.cache_read,
                "cost_usd": self.cost()}


class LLM:
    def __init__(self, client=None):
        if client is None:
            import anthropic
            client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.client = client
        self.usage = Usage()

    def create(self, *, model: str | None = None, max_tokens: int = 4096, **kwargs):
        response = self.client.messages.create(
            model=model or config.MODEL, max_tokens=max_tokens, **kwargs)
        self.usage.add(response.usage)
        return response


def blocks_to_dicts(content) -> list[dict]:
    """Convert response blocks to plain dicts so they can be sent back as history."""
    out = []
    for block in content:
        if block.type == "text" and block.text.strip():
            out.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            out.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
    return out


def forced_tool(llm: LLM, *, tool: dict, system: str, user: str, model: str | None = None) -> dict:
    """One call that must answer through the given tool. Returns the tool input."""
    response = llm.create(
        model=model, system=system, tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": user}])
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError(f"Model did not call {tool['name']}")
