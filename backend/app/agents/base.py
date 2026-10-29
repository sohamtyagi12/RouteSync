"""Minimal tool-use agent loop on top of the Anthropic Messages API.

An agent = a system prompt + a set of tools. The model decides which tools to
call; we execute them, feed results back, and stop when a *terminal* tool
(e.g. submit_proposal) is called with valid input.
"""
import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable

DEFAULT_MODEL = "claude-sonnet-5-5"


class AgentError(Exception):
    """The agent could not produce a result."""


class AgentNotConfigured(AgentError):
    """ANTHROPIC_API_KEY is missing."""


def agent_model() -> str:
    return os.getenv("AGENT_MODEL", DEFAULT_MODEL)


def agents_configured() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def get_client():
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise AgentNotConfigured("AI agents are not configured. Set ANTHROPIC_API_KEY on the server.")
    import anthropic
    return anthropic.Anthropic(api_key=key)


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    handler: Callable[[dict], Any]
    terminal: bool = False  # calling it (successfully) ends the run


@dataclass
class AgentResult:
    output: Any
    trace: list = field(default_factory=list)


def run_agent(*, system: str, task: str, tools: list[Tool], max_steps: int = 6, max_tokens: int = 1024) -> AgentResult:
    client = get_client()
    by_name = {t.name: t for t in tools}
    specs = [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]
    messages = [{"role": "user", "content": task}]
    trace = []

    for _ in range(max_steps):
        try:
            response = client.messages.create(
                model=agent_model(), max_tokens=max_tokens,
                system=system, tools=specs, messages=messages,
            )
        except Exception as exc:  # network / API / auth errors
            raise AgentError(f"The AI service request failed: {exc}") from exc

        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            raise AgentError("The agent stopped without submitting a result.")

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            tool = by_name.get(block.name)
            try:
                if tool is None:
                    raise ValueError(f"Unknown tool: {block.name}")
                output = tool.handler(block.input or {})
                trace.append({"tool": block.name, "input": block.input, "ok": True})
                if tool.terminal:
                    return AgentResult(output=output, trace=trace)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(output, default=str)})
            except Exception as exc:  # let the model see the error and self-correct
                trace.append({"tool": block.name, "input": block.input, "ok": False, "error": str(exc)})
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": f"Error: {exc}", "is_error": True})
        messages.append({"role": "user", "content": results})

    raise AgentError("The agent took too many steps without finishing.")
