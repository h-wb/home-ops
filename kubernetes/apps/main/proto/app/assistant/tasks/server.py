"""Synthetic task board for the assistant prototype (stand-in until a real task system is chosen).

One board per process (TASKS_BOARD), stored in SQLite under /data. With TASKS_READ_ONLY=1 the
write tools are never registered, so a read-only instance cannot write even if a caller names a
hidden tool: that is how private gets homelab tasks read-only, whatever ToolHive's filters do.
Alert-driven tasks carry a fingerprint, so a repeated alert updates its open task instead of
adding another.
"""

import os
import sqlite3
from datetime import datetime, timezone

from mcp.server.mcpserver import MCPServer

BOARD = os.environ["TASKS_BOARD"]
READ_ONLY = os.environ.get("TASKS_READ_ONLY") == "1"
DB = f"{os.environ.get('TASKS_DATA', '/data')}/{BOARD}.db"

server = MCPServer(
    name=f"{BOARD}-tasks{'-ro' if READ_ONLY else ''}",
    instructions=f"The {BOARD} task board" + (" (read-only)." if READ_ONLY else "."),
)


def db() -> sqlite3.Connection:
    # The read-only instance also opens the file read-only, so SQLite refuses writes too.
    conn = sqlite3.connect(f"file:{DB}?mode=ro" if READ_ONLY else DB, uri=READ_ONLY, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def row(r: sqlite3.Row | None) -> dict | None:
    return dict(r) if r else None


def list_tasks(status: str = "open") -> list[dict]:
    """List tasks on this board. status: open, done or all."""
    query = "SELECT * FROM tasks" + ("" if status == "all" else " WHERE status = ?") + " ORDER BY id"
    with db() as conn:
        return [dict(r) for r in conn.execute(query, () if status == "all" else (status,))]


def get_task(task_id: int) -> dict | None:
    """Get one task by id."""
    with db() as conn:
        return row(conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())


def find_open_task_by_fingerprint(fingerprint: str) -> dict | None:
    """Find the open task for an alert fingerprint, if any."""
    with db() as conn:
        return row(
            conn.execute(
                "SELECT * FROM tasks WHERE fingerprint = ? AND status = 'open'", (fingerprint,)
            ).fetchone()
        )


def create_task(title: str, notes: str = "", fingerprint: str = "") -> dict:
    """Create a task. With a fingerprint, an open task for it is updated instead (dedup)."""
    with db() as conn:
        if fingerprint and (open_task := find_open_task_by_fingerprint(fingerprint)):
            return update_task(open_task["id"], append_notes=notes)
        cur = conn.execute(
            "INSERT INTO tasks (title, notes, fingerprint, status, created, updated) VALUES (?, ?, ?, 'open', ?, ?)",
            (title, notes, fingerprint or None, now(), now()),
        )
        return row(conn.execute("SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)).fetchone())


def update_task(task_id: int, append_notes: str = "", status: str = "") -> dict | None:
    """Append notes to a task and/or set its status (open or done)."""
    with db() as conn:
        if append_notes:
            conn.execute(
                "UPDATE tasks SET notes = trim(notes || char(10) || ?), updated = ? WHERE id = ?",
                (append_notes, now(), task_id),
            )
        if status in ("open", "done"):
            conn.execute("UPDATE tasks SET status = ?, updated = ? WHERE id = ?", (status, now(), task_id))
        return row(conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())


for tool in (list_tasks, get_task, find_open_task_by_fingerprint):
    server.add_tool(tool)
if not READ_ONLY:
    for tool in (create_task, update_task):
        server.add_tool(tool)
    with db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY, title TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
                fingerprint TEXT, status TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL)"""
        )

if __name__ == "__main__":
    server.run("streamable-http", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
