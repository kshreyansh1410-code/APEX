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
    # These never run without the user's explicit yes for that one action.
    consequential: bool = False
    # Plain-language summary of what a call will do, shown when asking for confirmation.
    describe: Callable[[dict], str] | None = None


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
    # The confirmation gate. Called before every consequential call with
    # (tool, args, description); returns True only on an explicit yes. Each call asks
    # again: one yes never covers the next action. With no approver (e.g. a
    # background job with nobody to ask) consequential tools simply don't run.
    approver: Callable[[Tool, dict, str], bool] | None = None
    # Extra tool names that must be confirmed even though they're normally safe (config).
    extra_confirm: frozenset[str] = frozenset()

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

    def needs_confirmation(self, tool: Tool) -> bool:
        return tool.consequential or tool.name in self.extra_confirm

    def describe(self, tool: Tool, args: dict) -> str:
        if tool.describe:
            try:
                return tool.describe(args)
            except Exception:
                pass  # fall back to showing the raw call
        shown = ", ".join(f"{k}={v!r}" for k, v in args.items())
        return f"run {tool.name}({shown})"

    def run(self, name: str, args: Any) -> ToolOutcome:
        tool = self.tools.get(name)
        if tool is None:
            return ToolOutcome(f"There is no tool named '{name}'.", is_error=True)
        problem = validate(args, tool.input_schema)
        if problem:
            return ToolOutcome(f"Invalid input for {name}: {problem}. Fix the input and try again.", is_error=True)
        if self.needs_confirmation(tool):
            if self.approver is None:
                return ToolOutcome(
                    f"{name} was not run: it needs the user's explicit confirmation and there's no way to ask "
                    "them right now. Tell the user what you wanted to do.",
                    is_error=True,
                )
            try:
                approved = self.approver(tool, args, self.describe(tool, args)) is True
            except Exception:
                approved = False  # if asking fails, the answer is no
            if not approved:
                return ToolOutcome(
                    f"The user did not approve {name}, so it was not run. Don't retry it unless they ask again.",
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


_TYPES = {"string": str, "integer": int, "boolean": bool, "number": (int, float),
          "array": list, "object": dict, "null": type(None)}


def _type_ok(value: Any, type_name: str) -> bool:
    expected = _TYPES.get(type_name)
    if expected is None:
        return True  # a type we don't know: let the tool itself decide
    if isinstance(value, bool) and type_name in ("integer", "number"):
        return False  # True is an int in Python, but not in JSON
    return isinstance(value, expected)


def validate(args: Any, schema: dict) -> str | None:
    """Check args against the JSON Schema subset tools use. Returns a problem, or None.

    Needed because tool inputs are streamed eagerly, so the API doesn't validate them.
    Strict about our own tools (which set additionalProperties: false); lenient about
    keywords it doesn't understand in external schemas.
    """
    if not isinstance(args, dict):
        return "input must be an object"
    return _check_object(args, schema, path="")


def _check_object(value: dict, schema: dict, path: str) -> str | None:
    props = schema.get("properties", {}) or {}
    for key in schema.get("required", []) or []:
        if key not in value:
            return f"missing required field '{path}{key}'"
    for key, item in value.items():
        spec = props.get(key)
        if spec is None:
            if schema.get("additionalProperties") is False:
                return f"unexpected field '{path}{key}'"
            continue
        problem = _check_value(item, spec, f"{path}{key}")
        if problem:
            return problem
    return None


def _check_value(value: Any, spec: dict, name: str) -> str | None:
    if not isinstance(spec, dict):
        return None
    types = spec.get("type")
    if types is not None:
        types = types if isinstance(types, list) else [types]
        if not any(_type_ok(value, t) for t in types):
            return f"'{name}' must be {' or '.join(map(str, types))}"
    if "enum" in spec and value not in spec["enum"]:
        return f"'{name}' must be one of {spec['enum']}"
    if isinstance(value, str):
        if "maxLength" in spec and len(value) > spec["maxLength"]:
            return f"'{name}' is longer than {spec['maxLength']} characters"
        if "minLength" in spec and len(value.strip()) < spec["minLength"]:
            return f"'{name}' must not be empty"
    if isinstance(value, dict) and ("properties" in spec or "required" in spec):
        return _check_object(value, spec, path=f"{name}.")
    if isinstance(value, list) and isinstance(spec.get("items"), dict):
        for i, item in enumerate(value):
            problem = _check_value(item, spec["items"], f"{name}[{i}]")
            if problem:
                return problem
    return None
