"""Minimal tool-use agent loop that works with Gemini (free tier) or Claude.

An agent = a system prompt + a set of tools. The model decides which tools to
call; we execute them, feed results back, and stop when a *terminal* tool
(e.g. submit_proposal) is called with valid input.

Provider is chosen from environment variables:
  AGENT_PROVIDER = gemini | anthropic      (optional; auto-detected from keys)
  GEMINI_API_KEY   -> Gemini  (free tier available at aistudio.google.com)
  ANTHROPIC_API_KEY -> Claude (paid)
  AGENT_MODEL      -> optional model override
"""
import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable

GEMINI_DEFAULT_MODEL = "gemini-3.1-flash-lite"
ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-5-5"


class AgentError(Exception):
    """The agent could not produce a result."""


class AgentNotConfigured(AgentError):
    """No API key is configured."""


# ---------------------------------------------------------------- configuration

def _gemini_key():
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def provider_name():
    explicit = os.getenv("AGENT_PROVIDER", "").strip().lower()
    if explicit in {"gemini", "anthropic"}:
        return explicit
    if _gemini_key():
        return "gemini"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    return None


def agents_configured() -> bool:
    provider = provider_name()
    if provider == "gemini":
        return bool(_gemini_key())
    if provider == "anthropic":
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    return False


def agent_model() -> str:
    if os.getenv("AGENT_MODEL"):
        return os.environ["AGENT_MODEL"]
    return ANTHROPIC_DEFAULT_MODEL if provider_name() == "anthropic" else GEMINI_DEFAULT_MODEL


def get_client():
    provider = provider_name()
    if provider == "gemini":
        key = _gemini_key()
        if not key:
            raise AgentNotConfigured("AI agents are not configured. Set GEMINI_API_KEY on the server.")
        from google import genai
        return genai.Client(api_key=key)
    if provider == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise AgentNotConfigured("AI agents are not configured. Set ANTHROPIC_API_KEY on the server.")
        import anthropic
        return anthropic.Anthropic(api_key=key)
    raise AgentNotConfigured("AI agents are not configured. Set GEMINI_API_KEY (free) or ANTHROPIC_API_KEY on the server.")


# ---------------------------------------------------------------------- types

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


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


# ------------------------------------------------------------ provider sessions
# Each session keeps the conversation in its provider's format and exposes:
#   next_calls() -> list[ToolCall]      ask the model what to do next
#   add_results([(call, text, is_error)])  send tool results back

class _AnthropicSession:
    def __init__(self, client, model, system, tools, max_tokens, task):
        self.client, self.model, self.system, self.max_tokens = client, model, system, max_tokens
        self.specs = [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]
        self.messages = [{"role": "user", "content": task}]

    def next_calls(self):
        response = self.client.messages.create(
            model=self.model, max_tokens=self.max_tokens,
            system=self.system, tools=self.specs, messages=self.messages,
        )
        self.messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            raise AgentError("The agent stopped without submitting a result.")
        return [ToolCall(b.id, b.name, b.input or {}) for b in response.content if b.type == "tool_use"]

    def add_results(self, results):
        blocks = []
        for call, text, is_error in results:
            block = {"type": "tool_result", "tool_use_id": call.id, "content": text}
            if is_error:
                block["is_error"] = True
            blocks.append(block)
        self.messages.append({"role": "user", "content": blocks})


class _GeminiSession:
    def __init__(self, client, model, system, tools, max_tokens, task):
        from google.genai import types
        self.types, self.client, self.model = types, client, model
        declarations = []
        for t in tools:
            decl = {"name": t.name, "description": t.description}
            if t.input_schema.get("properties"):  # Gemini rejects empty parameter objects
                decl["parameters"] = t.input_schema
            declarations.append(decl)
        self.config = types.GenerateContentConfig(
            system_instruction=system,
            tools=[types.Tool(function_declarations=declarations)],
            max_output_tokens=max_tokens,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        self.contents = [types.Content(role="user", parts=[types.Part(text=task)])]

    def next_calls(self):
        response = self.client.models.generate_content(model=self.model, contents=self.contents, config=self.config)
        candidates = getattr(response, "candidates", None)
        if not candidates or not candidates[0].content:
            raise AgentError("The AI returned an empty response.")
        # keep the model's turn exactly as returned (Gemini 3 needs its thought signatures echoed back)
        self.contents.append(candidates[0].content)
        calls = [ToolCall(fc.id or fc.name, fc.name, dict(fc.args or {})) for fc in (response.function_calls or [])]
        if not calls:
            raise AgentError("The agent stopped without submitting a result.")
        return calls

    def add_results(self, results):
        parts = []
        for call, text, is_error in results:
            payload = {"error": text} if is_error else {"result": json.loads(text)}
            parts.append(self.types.Part.from_function_response(name=call.name, response=payload))
        self.contents.append(self.types.Content(role="user", parts=parts))


# ----------------------------------------------------------------------- loop

def run_agent(*, system: str, task: str, tools: list[Tool], max_steps: int = 6, max_tokens: int = 2048) -> AgentResult:
    client = get_client()
    session_cls = _GeminiSession if provider_name() == "gemini" else _AnthropicSession
    session = session_cls(client, agent_model(), system, tools, max_tokens, task)
    by_name = {t.name: t for t in tools}
    trace = []

    for _ in range(max_steps):
        try:
            calls = session.next_calls()
        except AgentError:
            raise
        except Exception as exc:  # network / quota / auth errors from the AI service
            raise AgentError(f"The AI service request failed: {exc}") from exc

        results = []
        for call in calls:
            tool = by_name.get(call.name)
            try:
                if tool is None:
                    raise ValueError(f"Unknown tool: {call.name}")
                output = tool.handler(call.args)
                trace.append({"tool": call.name, "input": call.args, "ok": True})
                if tool.terminal:
                    return AgentResult(output=output, trace=trace)
                results.append((call, json.dumps(output, default=str), False))
            except Exception as exc:  # let the model see the error and self-correct
                trace.append({"tool": call.name, "input": call.args, "ok": False, "error": str(exc)})
                results.append((call, f"Error: {exc}", True))
        session.add_results(results)

    raise AgentError("The agent took too many steps without finishing.")
