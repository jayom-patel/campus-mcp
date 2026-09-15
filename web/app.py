"""
CampusMCP web app - the surface your classmates actually use.

An MCP server only works for people who have Claude Desktop configured.
That is a distribution problem when you need real usage numbers in 3 days.
So this file wraps the SAME tools from core/campus.py in a plain web chat
that anyone can open from a WhatsApp link.

Zero third-party dependencies: standard library http.server + urllib.

Run:
    export ANTHROPIC_API_KEY=sk-ant-...
    python web/app.py
    open http://localhost:8000

Usage is appended to data/usage.log so you can count real users for your
application.
"""

import json
import os
import sys
import urllib.error
import urllib.request
import datetime as dt
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import campus  # noqa: E402

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5")
PORT = int(os.environ.get("PORT", "8000"))
USAGE_LOG = ROOT / "data" / "usage.log"
MAX_TOOL_ROUNDS = 6

SYSTEM_PROMPT = """You are CampusMCP, an assistant for SY B.Tech CSE (AI & ML) students at Vishwakarma Institute of Technology, Pune.

You have tools that read this class's real timetable, syllabus, deadlines and campus events. Rules:

- ALWAYS call a tool before answering anything about schedules, deadlines, syllabus or events. Never guess a time, room or date.
- If a tool returns no data, say so plainly and tell the student what is missing. Do not invent a plausible answer.
- Be brief. Students are checking this between classes on a phone.
- For study help, you may explain concepts from your own knowledge, but ground any syllabus scope in search_syllabus.
- Answer in the language the student uses. Hinglish is fine.
"""


def anthropic_tools():
    """Build Anthropic API tool definitions from the shared registry."""
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["schema"],
        }
        for t in campus.TOOLS
    ]


def post_to_anthropic(payload: dict, api_key: str) -> dict:
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def run_conversation(messages: list, api_key: str) -> tuple:
    """Run the Claude tool-use loop. Returns (reply_text, tools_used)."""
    tools_used = []

    for _ in range(MAX_TOOL_ROUNDS):
        result = post_to_anthropic(
            {
                "model": MODEL,
                "max_tokens": 1024,
                "system": SYSTEM_PROMPT,
                "tools": anthropic_tools(),
                "messages": messages,
            },
            api_key,
        )

        blocks = result.get("content", [])
        messages.append({"role": "assistant", "content": blocks})

        if result.get("stop_reason") != "tool_use":
            text = "".join(
                b.get("text", "") for b in blocks if b.get("type") == "text"
            )
            return text.strip() or "(no response)", tools_used

        tool_results = []
        for block in blocks:
            if block.get("type") != "tool_use":
                continue
            name = block["name"]
            tools_used.append(name)
            output = campus.call_tool(name, block.get("input") or {})
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": output,
                }
            )
        messages.append({"role": "user", "content": tool_results})

    return "Stopped after too many tool calls. Try a simpler question.", tools_used


def log_usage(visitor: str, question: str, tools_used: list) -> None:
    """Append one line per question so you can count real usage."""
    try:
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": dt.datetime.now(campus.TZ).isoformat(timespec="seconds"),
            "visitor": visitor,
            "question": question[:200],
            "tools": tools_used,
        }
        with open(USAGE_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # never let logging break a student's request


class Handler(BaseHTTPRequestHandler):
    server_version = "CampusMCP"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def do_GET(self):
        if self.path.split("?")[0] in ("/", "/index.html"):
            page = Path(__file__).resolve().parent / "index.html"
            self._send(200, page.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/health":
            self._json(
                200,
                {
                    "ok": True,
                    "tools": [t["name"] for t in campus.TOOLS],
                    "has_api_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
                },
            )
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/chat":
            self._json(404, {"error": "not found"})
            return

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            self._json(500, {"error": "ANTHROPIC_API_KEY is not set on the server."})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            self._json(400, {"error": "Invalid JSON body."})
            return

        history = body.get("messages")
        if not isinstance(history, list) or not history:
            self._json(400, {"error": "Send a non-empty 'messages' array."})
            return

        # Keep only the last 12 turns to bound cost.
        messages = [
            {"role": m["role"], "content": m["content"]}
            for m in history[-12:]
            if m.get("role") in ("user", "assistant") and m.get("content")
        ]
        question = next(
            (
                m["content"]
                for m in reversed(messages)
                if m["role"] == "user" and isinstance(m["content"], str)
            ),
            "",
        )

        try:
            reply, tools_used = run_conversation(messages, api_key)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            self._json(502, {"error": f"Anthropic API error {exc.code}: {detail}"})
            return
        except Exception as exc:
            self._json(500, {"error": f"Server error: {exc}"})
            return

        log_usage(str(body.get("visitor") or "anon")[:64], question, tools_used)
        self._json(200, {"reply": reply, "tools_used": tools_used})


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("WARNING: ANTHROPIC_API_KEY not set. Chat will return an error.")
    print(f"CampusMCP running on http://localhost:{PORT}")
    print(f"Tools available: {', '.join(t['name'] for t in campus.TOOLS)}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
