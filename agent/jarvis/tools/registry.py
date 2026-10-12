"""The tool registry: the one place capabilities are added.

A new capability = one self-contained module that registers a Tool. The core loop
never changes when tools are added.
"""

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class Tool:
    name: str
    # Written for the model: say *when* to use it, not just what it is.
    description: str
    # JSON Schema for the input object (a small subset is enforced; see validate()).
    input_schema: dict
    handler: Callable[..., str]
    # True for anything that sends, spends, deletes, or changes a setting.
    # These never run on assumed permission (Tier 6 adds the confirmation gate).
    consequential: bool = False


@dataclass
class ToolOutcome:
    content: str
    is_error: bool = False


class ToolError(Exception):
    """Raised by a tool for an expected failure; the message goes to the model."""


@dataclass
class Registry:
    tools: dict[str, Tool] = field(default_factory=dict)
    # Tool names that fail on purpose, for testing recovery (config: debug.fail_tools).
    simulate_failure: frozenset[str] = frozenset()
    # Called before a consequential tool runs; returns True only on an explicit yes.
    # Until the Tier 6 gate exists there is no approver, so consequential tools refuse.
    approver: Callable[[Tool, dict], bool] | None = None

    def register(self, tool: Tool) -> None:
        if tool.name in self.tools:
            raise ValueError(f"tool '{tool.name}' is already registered")
        self.tools[tool.name] = tool

    def schemas(self) -> list[dict]:
        """Tool definitions in the shape the model API expects, in a stable order."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
                "eager_input_streaming": True,
            }
            for t in sorted(self.tools.values(), key=lambda t: t.name)
        ]

    def run(self, name: str, args: Any) -> ToolOutcome:
        tool = self.tools.get(name)
        if tool is None:
            return ToolOutcome(f"There is no tool named '{name}'.", is_error=True)
        problem = validate(args, tool.input_schema)
        if problem:
            return ToolOutcome(f"Invalid input for {name}: {problem}. Fix the input and try again.", is_error=True)
        if tool.consequential and not (self.approver and self.approver(tool, args)):
            return ToolOutcome(
                f"{name} was not run: it needs the user's explicit confirmation first and none was given. "
                "Tell the user what you wanted to do.",
                is_error=True,
            )
        try:
            if name in self.simulate_failure:
                raise ToolError("simulated failure (debug.fail_tools in config.toml)")
            return ToolOutcome(tool.handler(**args))
        except ToolError as e:
            return ToolOutcome(f"{name} failed: {e}", is_error=True)
        except Exception as e:  # a buggy tool must not crash the agent
            return ToolOutcome(f"{name} failed unexpectedly ({type(e).__name__}: {e}).", is_error=True)


_TYPES = {"string": str, "integer": int, "boolean": bool, "number": (int, float)}


def validate(args: Any, schema: dict) -> str | None:
    """Check args against the schema subset our tools use. Returns a problem, or None.

    Needed because tool inputs are streamed eagerly, so the API doesn't validate them.
    """
    if not isinstance(args, dict):
        return "input must be an object"
    props = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in args:
            return f"missing required field '{key}'"
    for key, value in args.items():
        spec = props.get(key)
        if spec is None:
            return f"unexpected field '{key}'"
        expected = _TYPES[spec["type"]]
        if not isinstance(value, expected) or (spec["type"] != "boolean" and isinstance(value, bool)):
            return f"'{key}' must be a {spec['type']}"
        if "enum" in spec and value not in spec["enum"]:
            return f"'{key}' must be one of {spec['enum']}"
        if spec["type"] == "string":
            if "maxLength" in spec and len(value) > spec["maxLength"]:
                return f"'{key}' is longer than {spec['maxLength']} characters"
            if "minLength" in spec and len(value.strip()) < spec["minLength"]:
                return f"'{key}' must not be empty"
    return None
