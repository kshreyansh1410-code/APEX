"""Capability 2: study reminders and tasks — a small dated to-do list."""

from datetime import date, datetime
from pathlib import Path

from .registry import Registry, Tool, ToolError
from .store import JsonStore


def _parse_due(due: str) -> str:
    try:
        return date.fromisoformat(due).isoformat()
    except ValueError:
        raise ToolError(f"due date '{due}' must be YYYY-MM-DD; call get_current_datetime to work out dates") from None


def _line(t: dict) -> str:
    due = f" (due {t['due']})" if t.get("due") else ""
    done = " [done]" if t.get("done") else ""
    return f"#{t['id']}: {t['title']}{due}{done}"


def _describe_delete(store: JsonStore, task_id: int) -> str:
    for t in store.load():
        if t["id"] == task_id:
            return f"permanently delete task #{task_id}: \"{t['title']}\""
    return f"delete task #{task_id} (it doesn't seem to exist)"


def register(registry: Registry, data_dir: Path) -> None:
    store = JsonStore(data_dir / "tasks.json")

    def find(tasks: list[dict], task_id: int) -> dict:
        for t in tasks:
            if t["id"] == task_id:
                return t
        raise ToolError(f"there is no task #{task_id}; call list_tasks to see the ids")

    def add_task(title: str, due: str = "") -> str:
        tasks = store.load()
        task = {
            "id": JsonStore.next_id(tasks),
            "title": title.strip(),
            "due": _parse_due(due) if due else "",
            "done": False,
            "created": datetime.now().isoformat(timespec="minutes"),
        }
        tasks.append(task)
        store.save(tasks)
        return f"Added {_line(task)}."

    def list_tasks(which: str = "open") -> str:
        today = date.today().isoformat()
        tasks = store.load()
        if which == "today":
            # Due today, plus anything overdue — that's what "today" means to a person.
            picked = [t for t in tasks if not t["done"] and t.get("due") and t["due"] <= today]
        elif which == "open":
            picked = [t for t in tasks if not t["done"]]
        else:
            picked = tasks
        if not picked:
            return {"today": "Nothing is due today or overdue.", "open": "No open tasks."}.get(which, "No tasks yet.")
        picked.sort(key=lambda t: (t["done"], t.get("due") or "9999", t["id"]))
        overdue = sum(1 for t in picked if not t["done"] and t.get("due") and t["due"] < today)
        header = f"{len(picked)} task(s), today is {today}" + (f", {overdue} overdue" if overdue else "") + ":"
        return header + "\n" + "\n".join(_line(t) for t in picked)

    def complete_task(task_id: int) -> str:
        tasks = store.load()
        task = find(tasks, task_id)
        task["done"] = True
        store.save(tasks)
        return f"Marked {_line(task)}."

    def delete_task(task_id: int) -> str:
        tasks = store.load()
        task = find(tasks, task_id)
        tasks.remove(task)
        store.save(tasks)
        return f"Deleted task #{task_id}: {task['title']}."

    def get_current_datetime() -> str:
        now = datetime.now().astimezone()
        return now.strftime("It is %A, %Y-%m-%d, %H:%M (%Z, UTC%z).")

    registry.register(Tool(
        name="add_task",
        description=(
            "Add a study task or reminder to the user's to-do list, optionally with a due date. "
            "Use this when the user asks to be reminded of something or to add something to their list. "
            "For relative dates like 'Friday', call get_current_datetime first to work out the date."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "What to do, e.g. 'Review chapter 4'.", "minLength": 1, "maxLength": 300},
                "due": {"type": "string", "description": "Optional due date as YYYY-MM-DD."},
            },
            "required": ["title"],
            "additionalProperties": False,
        },
        handler=add_task,
    ))
    registry.register(Tool(
        name="list_tasks",
        description=(
            "Show the user's to-do list. Use 'today' for what's due today or overdue "
            "(e.g. 'what's on my list for today?'), 'open' for everything not done yet, and 'all' to include finished tasks."
        ),
        input_schema={
            "type": "object",
            "properties": {"which": {"type": "string", "enum": ["today", "open", "all"]}},
            "required": ["which"],
            "additionalProperties": False,
        },
        handler=list_tasks,
    ))
    registry.register(Tool(
        name="complete_task",
        description="Mark a task as done. Use the task's id from list_tasks.",
        input_schema={
            "type": "object",
            "properties": {"task_id": {"type": "integer"}},
            "required": ["task_id"],
            "additionalProperties": False,
        },
        handler=complete_task,
    ))
    registry.register(Tool(
        name="delete_task",
        description="Permanently delete a task from the list. Use only when the user asks to remove or delete a task.",
        input_schema={
            "type": "object",
            "properties": {"task_id": {"type": "integer"}},
            "required": ["task_id"],
            "additionalProperties": False,
        },
        handler=delete_task,
        consequential=True,  # deletes data
        describe=lambda args: _describe_delete(store, args["task_id"]),
    ))
    registry.register(Tool(
        name="get_current_datetime",
        description="Get the current local date, weekday, and time. Use it to work out due dates or answer 'what day is it'.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=get_current_datetime,
    ))
