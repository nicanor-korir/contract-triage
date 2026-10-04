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

    # Thinking tokens count against max_tokens, so leave room for a turn of many tool calls.
    def create(self, *, model: str | None = None, max_tokens: int = 16000, **kwargs):
        response = self.client.messages.create(
            model=model or config.MODEL, max_tokens=max_tokens, **kwargs)
        self.usage.add(response.usage)
        return response


def blocks_to_dicts(content) -> list[dict]:
    """Convert response blocks to plain dicts so they can be sent back as history."""
    out = []
    for block in content:
        # Models with thinking on (Sonnet 5 and 5.5 think by default) must get their
        # thinking blocks back unchanged alongside the tool_use blocks, or the next call fails.
        if block.type == "thinking":
            out.append({"type": "thinking", "thinking": block.thinking, "signature": block.signature})
        elif block.type == "redacted_thinking":
            out.append({"type": "redacted_thinking", "data": block.data})
        elif block.type == "text" and block.text.strip():
            out.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            out.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
    return out


def forced_tool(llm: LLM, *, tool: dict, system: str, user: str, model: str | None = None) -> dict:
    """A call that must answer through the given tool. Returns the tool input.

    Newer models (Sonnet 5.5, Opus 5.5, Fable 5.1) reject a forced tool_choice, so the tool
    is named in the prompt instead, and the model is asked once more if it does not call it.
    """
    name = tool["name"]
    messages = [{"role": "user", "content": f"{user}\n\nAnswer by calling the {name} tool."}]
    for _ in range(2):
        response = llm.create(model=model, system=system, tools=[tool],
                              tool_choice={"type": "auto"}, messages=messages)
        for block in response.content:
            if block.type == "tool_use" and block.name == name:
                return block.input
        messages += [{"role": "assistant",
                      "content": blocks_to_dicts(response.content) or [{"type": "text", "text": "."}]},
                     {"role": "user", "content": f"Call the {name} tool now."}]
    raise RuntimeError(f"Model did not call {name}")
