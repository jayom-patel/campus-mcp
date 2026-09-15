"""
CampusMCP - an MCP server exposing VIT Pune academic data as Claude tools.

This is the piece that signals real Claude-ecosystem fluency: it speaks
Model Context Protocol, so Claude Desktop / Claude Code can call campus data
directly as native tools.

Run locally:
    pip install -r requirements.txt
    python mcp_server/server.py

Register with Claude Desktop by adding this to claude_desktop_config.json:

    {
      "mcpServers": {
        "campus": {
          "command": "python",
          "args": ["/absolute/path/to/campus-mcp/mcp_server/server.py"]
        }
      }
    }
"""

import sys
from pathlib import Path

# Allow running this file directly without installing the project as a package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import campus  # noqa: E402

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover
    try:
        # Standalone fastmcp package, if the bundled one is unavailable.
        from fastmcp import FastMCP
    except ImportError:
        sys.exit(
            "Missing dependency. Run: pip install -r requirements.txt\n"
            "(installs the official 'mcp' Python SDK)"
        )

mcp = FastMCP("campus")


@mcp.tool()
def list_courses() -> str:
    """List all courses for the current term with faculty and credits."""
    return campus.list_courses()


@mcp.tool()
def get_timetable(day: str = "today") -> str:
    """Get the class schedule for a day.

    Args:
        day: monday-sunday, or 'today' / 'tomorrow'.
    """
    return campus.get_timetable(day)


@mcp.tool()
def get_next_class() -> str:
    """Get the next upcoming class relative to the current IST time."""
    return campus.get_next_class()


@mcp.tool()
def get_deadlines(within_days: int = 14) -> str:
    """List exams, submissions and deadlines due within N days.

    Args:
        within_days: Lookahead window in days.
    """
    return campus.get_deadlines(within_days)


@mcp.tool()
def search_syllabus(query: str) -> str:
    """Find which course and unit covers a topic.

    Args:
        query: Topic to look up, e.g. 'backpropagation'.
    """
    return campus.search_syllabus(query)


@mcp.tool()
def get_campus_events(within_days: int = 30) -> str:
    """List club and campus events happening in the next N days.

    Args:
        within_days: Lookahead window in days.
    """
    return campus.get_campus_events(within_days)


if __name__ == "__main__":
    mcp.run()
