"""
Campus data core.

Pure standard library. This module is the single source of truth that BOTH
the MCP server (mcp_server/server.py) and the student web app (web/app.py)
call into. Write a query function once, get it in both surfaces.

Every function returns a human-readable string, because these are consumed
by an LLM as tool results, not by a UI.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo("Asia/Kolkata")
except Exception:  # pragma: no cover - fallback if tzdata is missing
    TZ = dt.timezone(dt.timedelta(hours=5, minutes=30))

_DEFAULT_DATA = Path(__file__).resolve().parent.parent / "data" / "campus.json"
DATA_PATH = Path(os.environ.get("CAMPUS_DATA", _DEFAULT_DATA))

DAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


def load() -> dict:
    """Read campus.json from disk on every call so edits apply without restart."""
    with open(DATA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def now() -> dt.datetime:
    return dt.datetime.now(TZ)


def _courses_by_code(data: dict) -> dict:
    return {c["code"]: c for c in data.get("courses", [])}


def _label(code: str, courses: dict) -> str:
    course = courses.get(code)
    return f"{course['name']} ({code})" if course else code


def _resolve_day(day: str | None) -> str:
    """Accept 'monday', 'mon', 'today', 'tomorrow', or None -> today."""
    if not day:
        return DAYS[now().weekday()]
    key = day.strip().lower()
    if key in ("today", "aaj"):
        return DAYS[now().weekday()]
    if key in ("tomorrow", "kal"):
        return DAYS[(now().weekday() + 1) % 7]
    for name in DAYS:
        if name.startswith(key[:3]):
            return name
    raise ValueError(f"Unknown day: {day!r}. Use monday-sunday, today, or tomorrow.")


# ---------------------------------------------------------------- tool: courses


def list_courses() -> str:
    """List every course this term with faculty and credits."""
    data = load()
    meta = data.get("meta", {})
    lines = [
        f"{meta.get('branch', 'Course list')} - {meta.get('term', '')} "
        f"({meta.get('academic_year', '')})".strip()
    ]
    for c in data.get("courses", []):
        lines.append(
            f"- {c['name']} ({c['code']}) | {c.get('credits', '?')} credits "
            f"| faculty: {c.get('faculty', 'TBA')}"
        )
    return "\n".join(lines) if len(lines) > 1 else "No courses configured yet."


# -------------------------------------------------------------- tool: timetable


def get_timetable(day: str | None = None) -> str:
    """Return the class schedule for one day."""
    data = load()
    key = _resolve_day(day)
    courses = _courses_by_code(data)
    slots = sorted(
        data.get("timetable", {}).get(key, []), key=lambda s: s["start"]
    )
    if not slots:
        return f"No classes scheduled on {key.title()}."
    lines = [f"Timetable for {key.title()}:"]
    for s in slots:
        lines.append(
            f"- {s['start']}-{s['end']} | {_label(s['course'], courses)} "
            f"| {s.get('type', 'lecture')} | room {s.get('room', 'TBA')}"
        )
    return "\n".join(lines)


def get_next_class() -> str:
    """Return the next class starting from the current IST time."""
    data = load()
    courses = _courses_by_code(data)
    current = now()

    for offset in range(7):
        probe = current + dt.timedelta(days=offset)
        key = DAYS[probe.weekday()]
        slots = sorted(
            data.get("timetable", {}).get(key, []), key=lambda s: s["start"]
        )
        for s in slots:
            hh, mm = (int(x) for x in s["start"].split(":"))
            start = probe.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if start <= current:
                continue
            delta = start - current
            hours, rem = divmod(int(delta.total_seconds()), 3600)
            mins = rem // 60
            when = "today" if offset == 0 else (
                "tomorrow" if offset == 1 else key.title()
            )
            return (
                f"Next class: {_label(s['course'], courses)} "
                f"at {s['start']} {when} in room {s.get('room', 'TBA')} "
                f"({s.get('type', 'lecture')}) - starts in {hours}h {mins}m."
            )
    return "No upcoming classes found in the next 7 days."


# -------------------------------------------------------------- tool: deadlines


def get_deadlines(within_days: int = 14) -> str:
    """List exams, submissions, and events due within N days."""
    data = load()
    courses = _courses_by_code(data)
    today = now().date()
    horizon = today + dt.timedelta(days=int(within_days))

    upcoming = []
    for item in data.get("deadlines", []):
        try:
            date = dt.date.fromisoformat(item["date"])
        except (KeyError, ValueError):
            continue
        if today <= date <= horizon:
            upcoming.append((date, item))

    if not upcoming:
        return f"Nothing due in the next {within_days} days."

    upcoming.sort(key=lambda pair: pair[0])
    lines = [f"Due in the next {within_days} days (today is {today.isoformat()}):"]
    for date, item in upcoming:
        days_left = (date - today).days
        urgency = (
            "TODAY"
            if days_left == 0
            else ("tomorrow" if days_left == 1 else f"in {days_left} days")
        )
        course = (
            f" | {_label(item['course'], courses)}" if item.get("course") else ""
        )
        lines.append(
            f"- {date.isoformat()} ({urgency}) | {item['title']} "
            f"| {item.get('type', 'task')}{course}"
        )
    return "\n".join(lines)


# --------------------------------------------------------------- tool: syllabus


def search_syllabus(query: str) -> str:
    """Find which course and unit covers a topic."""
    data = load()
    term = (query or "").strip().lower()
    if not term:
        return "Provide a topic to search for."

    hits = []
    for c in data.get("courses", []):
        for unit in c.get("units", []):
            matched = [t for t in unit.get("topics", []) if term in t.lower()]
            if matched or term in unit.get("title", "").lower():
                hits.append(
                    f"- {c['name']} ({c['code']}) > {unit.get('title', 'Unit')}: "
                    + ", ".join(matched or unit.get("topics", [])[:4])
                )

    if not hits:
        return (
            f"No syllabus match for {query!r}. "
            "Try a broader term, or check list_courses for what is configured."
        )
    return f"Syllabus matches for {query!r}:\n" + "\n".join(hits)


# ------------------------------------------------------------------ tool: clubs


def get_campus_events(within_days: int = 30) -> str:
    """List club and campus events in the next N days."""
    data = load()
    today = now().date()
    horizon = today + dt.timedelta(days=int(within_days))

    rows = []
    for ev in data.get("events", []):
        try:
            date = dt.date.fromisoformat(ev["date"])
        except (KeyError, ValueError):
            continue
        if today <= date <= horizon:
            rows.append((date, ev))

    if not rows:
        return f"No campus events listed in the next {within_days} days."

    rows.sort(key=lambda pair: pair[0])
    lines = [f"Campus events in the next {within_days} days:"]
    for date, ev in rows:
        lines.append(
            f"- {date.isoformat()} | {ev['title']} | {ev.get('club', 'Campus')} "
            f"| {ev.get('venue', 'TBA')}"
        )
    return "\n".join(lines)


# ------------------------------------------------------------ tool declarations

# Shared schema list. The MCP server and the web app both build their tool
# definitions from this, so the two surfaces can never drift apart.
TOOLS = [
    {
        "name": "list_courses",
        "description": "List all courses for the current term with faculty and credits.",
        "fn": list_courses,
        "schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_timetable",
        "description": (
            "Get the class schedule for a given day. Accepts monday-sunday, "
            "'today', or 'tomorrow'. Defaults to today."
        ),
        "fn": get_timetable,
        "schema": {
            "type": "object",
            "properties": {
                "day": {
                    "type": "string",
                    "description": "monday-sunday, today, or tomorrow",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_next_class",
        "description": "Get the next upcoming class relative to the current IST time.",
        "fn": get_next_class,
        "schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_deadlines",
        "description": "List exams, submissions and deadlines due within N days.",
        "fn": get_deadlines,
        "schema": {
            "type": "object",
            "properties": {
                "within_days": {"type": "integer", "description": "Default 14"}
            },
            "required": [],
        },
    },
    {
        "name": "search_syllabus",
        "description": "Find which course and unit covers a given topic.",
        "fn": search_syllabus,
        "schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Topic to look up"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_campus_events",
        "description": "List club and campus events happening in the next N days.",
        "fn": get_campus_events,
        "schema": {
            "type": "object",
            "properties": {
                "within_days": {"type": "integer", "description": "Default 30"}
            },
            "required": [],
        },
    },
]

TOOLS_BY_NAME = {t["name"]: t for t in TOOLS}


def call_tool(name: str, arguments: dict | None = None) -> str:
    """Dispatch a tool call by name. Used by the web app's tool-use loop."""
    tool = TOOLS_BY_NAME.get(name)
    if not tool:
        return f"Unknown tool: {name}"
    try:
        return tool["fn"](**(arguments or {}))
    except Exception as exc:  # surfaced back to the model as a tool result
        return f"Tool {name} failed: {exc}"
