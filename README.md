# CampusMCP

An MCP server that gives Claude access to real VIT Pune academic data, plus a web app so any student can use it without installing anything.

Built by Jayom Patel, SY B.Tech CSE (AI & ML), Vishwakarma Institute of Technology, Pune.

## The problem

Every semester my class of 70 students asks the same questions in the WhatsApp group: what room is the lab in, when is the unit test, which unit covers this topic. The answers exist, but they are spread across PDFs, notice boards and screenshots. As Class Representative I answer these by hand, dozens of times a week.

## What this does

CampusMCP loads the class timetable, syllabus, deadlines and campus events into a single structured source, then exposes them as six tools:

| Tool | What it answers |
| --- | --- |
| `list_courses` | What am I taking this term, and who teaches it |
| `get_timetable` | Schedule for any day, including "today" and "tomorrow" |
| `get_next_class` | What is next right now, and how long until it starts |
| `get_deadlines` | Exams and submissions due in the next N days |
| `search_syllabus` | Which course and unit covers a given topic |
| `get_campus_events` | Club and campus events coming up |

Those tools are served two ways from one implementation:

1. **As an MCP server** (`mcp_server/server.py`) so Claude Desktop and Claude Code can call campus data as native tools.
2. **As a web chat** (`web/app.py`) so classmates who have never heard of MCP can just open a link on their phone.

Both import the same functions from `core/campus.py`, so the two surfaces cannot drift apart.

## Design decisions

**The model is never allowed to guess a fact.** The system prompt requires a tool call before answering anything about schedules, deadlines or syllabus, and requires it to say so plainly when data is missing. A study assistant that invents an exam date is worse than no assistant.

**Zero dependencies for the web app.** It uses `http.server` and `urllib` from the standard library and talks to the Anthropic Messages API directly, implementing the tool-use loop by hand. Anyone can run it with nothing but Python installed.

**Data is re-read from disk on every call.** I can fix a wrong room number and the answer is correct on the next question, without a restart.

## Setup

```
git clone <your-repo-url>
cd campus-mcp
```

### 1. Put in your real data

Edit `data/campus.json`. Replace every `REPLACE_ME` with your actual course codes, rooms, faculty and dates. Then validate:

```
python scripts/selfcheck.py
```

This checks the JSON, catches timetable slots pointing at courses that do not exist, and prints the output of all six tools. No API key or internet needed.

### 2. Run the web app

```
export ANTHROPIC_API_KEY=sk-ant-...
python web/app.py
```

Open http://localhost:8000. To share it with your class, expose it with a tunnel, for example `cloudflared tunnel --url http://localhost:8000`, and send the link.

Each question is appended to `data/usage.log` with an anonymous visitor id, so real usage can be counted:

```
wc -l data/usage.log
python -c "import json;print(len({json.loads(l)['visitor'] for l in open('data/usage.log')}))"
```

### 3. Run the MCP server

```
pip install -r requirements.txt
python mcp_server/server.py
```

Register it with Claude Desktop by adding this to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "campus": {
      "command": "python",
      "args": ["/absolute/path/to/campus-mcp/mcp_server/server.py"]
    }
    
  }
}
```

Restart Claude Desktop, then ask: "What is my next class and what is due this week?" Claude will call the campus tools.

## Layout

```
core/campus.py        all query logic and the shared tool registry
mcp_server/server.py  MCP wrapper (thin)
web/app.py            HTTP server and Claude tool-use loop (thin)
web/index.html         student-facing chat UI
data/campus.json      the data you edit
scripts/selfcheck.py  offline validation of data and tools
```

## Limitations

- Data is entered by hand. It is only as correct as the last time I updated it, which is why the UI tells students to confirm exam dates with their CR.
- Single class scope. Supporting other divisions means one JSON file per division and a selector.
- No auth on the web app. Fine for a class link, not for anything private.

## Roadmap

- Pull the academic calendar automatically instead of hand-entering it
- Per-division data files so the whole CSE (AI & ML) branch can use it
- A `submit_correction` tool so students can flag wrong data instead of messaging me
