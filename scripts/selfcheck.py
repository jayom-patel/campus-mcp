"""
Self-check: validates data/campus.json and exercises every tool offline.

Run this before you demo. No API key and no internet needed.

    python scripts/selfcheck.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import campus  # noqa: E402

FAIL = []
WARN = []


def check_data():
    try:
        data = campus.load()
    except FileNotFoundError:
        FAIL.append(f"campus.json not found at {campus.DATA_PATH}")
        return None
    except ValueError as exc:
        FAIL.append(f"campus.json is not valid JSON: {exc}")
        return None

    codes = {c.get("code") for c in data.get("courses", [])}
    if not codes:
        FAIL.append("No courses defined.")

    placeholders = sum(
        1 for c in codes if isinstance(c, str) and "REPLACE_ME" in c
    )
    if placeholders:
        WARN.append(
            f"{placeholders} course code(s) still say REPLACE_ME. "
            "Real data is the whole product - fill these in."
        )

    slot_count = 0
    for day, slots in data.get("timetable", {}).items():
        if day not in campus.DAYS:
            FAIL.append(f"Unknown day key in timetable: {day!r}")
        for slot in slots:
            slot_count += 1
            if slot.get("course") not in codes:
                FAIL.append(
                    f"{day}: slot at {slot.get('start')} references unknown "
                    f"course {slot.get('course')!r}"
                )
            for field in ("start", "end"):
                value = slot.get(field, "")
                if not (len(value) == 5 and value[2] == ":"):
                    FAIL.append(
                        f"{day}: slot {field} must be HH:MM, got {value!r}"
                    )

    if slot_count < 5:
        WARN.append(
            f"Only {slot_count} timetable slots. Enter a full week or students "
            "will hit empty answers and stop using it."
        )

    for item in data.get("deadlines", []):
        if item.get("course") and item["course"] not in codes:
            FAIL.append(f"Deadline {item.get('title')!r} has unknown course code.")

    return data


def check_tools():
    print("\nTool output:")
    print("-" * 60)
    probes = [
        ("list_courses", {}),
        ("get_timetable", {"day": "monday"}),
        ("get_timetable", {"day": "today"}),
        ("get_next_class", {}),
        ("get_deadlines", {"within_days": 30}),
        ("search_syllabus", {"query": "trees"}),
        ("get_campus_events", {"within_days": 60}),
    ]
    for name, args in probes:
        label = f"{name}({', '.join(f'{k}={v!r}' for k, v in args.items())})"
        try:
            out = campus.call_tool(name, args)
        except Exception as exc:
            FAIL.append(f"{label} raised {exc}")
            continue
        if not isinstance(out, str) or not out.strip():
            FAIL.append(f"{label} returned nothing.")
        print(f"\n$ {label}\n{out}")


def main():
    print(f"Reading {campus.DATA_PATH}")
    if check_data() is not None:
        check_tools()

    print("\n" + "=" * 60)
    for warning in WARN:
        print(f"WARN  {warning}")
    for failure in FAIL:
        print(f"FAIL  {failure}")

    if FAIL:
        print(f"\n{len(FAIL)} problem(s) to fix.")
        return 1
    print(f"\nAll checks passed. {len(WARN)} warning(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
