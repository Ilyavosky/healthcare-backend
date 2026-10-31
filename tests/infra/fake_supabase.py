from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import httpx
from postgrest.exceptions import APIError

DEFAULTS: dict[str, dict[str, Any]] = {
    "rooms": {"status": "open", "doctors": 1},
    "patients": {"attended_at": None, "doctor": None},
    "solves": {"same_cost": None, "baseline_gap_pct": None, "alerts": []},
    "solve_results": {"weight": 1, "steps": [], "left_out": [], "limit_attempts": []},
}
UNIQUE: dict[str, tuple[str, ...]] = {
    "patients": ("room_id", "label"),
    "solve_results": ("solve_id", "algorithm"),
}


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {name: [] for name in DEFAULTS}
        self.fail_with: Exception | None = None
        self.fail_table: str | None = None
        self.calls: list[tuple[str, str]] = []

    def table(self, name: str) -> "FakeQuery":
        return FakeQuery(self, name)


class FakeQuery:
    def __init__(self, db: FakeSupabase, table: str) -> None:
        self.db = db
        self.name = table
        self.action = "select"
        self.payload: Any = None
        self.filters: list[tuple[str, str]] = []
        self.ordering: tuple[str, bool] | None = None
        self.max_rows: int | None = None

    def select(self, columns: str = "*") -> "FakeQuery":
        self.action = "select"
        return self

    def insert(self, rows: Any) -> "FakeQuery":
        self.action, self.payload = "insert", rows
        return self

    def update(self, values: dict[str, Any]) -> "FakeQuery":
        self.action, self.payload = "update", values
        return self

    def delete(self) -> "FakeQuery":
        self.action = "delete"
        return self

    def eq(self, column: str, value: str) -> "FakeQuery":
        self.filters.append((column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> "FakeQuery":
        self.ordering = (column, desc)
        return self

    def limit(self, count: int) -> "FakeQuery":
        self.max_rows = count
        return self

    def execute(self) -> SimpleNamespace:
        self.db.calls.append((self.name, self.action))
        if self.db.fail_with is not None and self.db.fail_table in (None, self.name):
            error, self.db.fail_with = self.db.fail_with, None
            raise error
        rows = self.db.tables[self.name]
        if self.action == "insert":
            new = [self._new_row(row) for row in _as_list(self.payload)]
            for row in new:
                self._check_unique(row, rows)
                rows.append(row)
            return SimpleNamespace(data=[dict(r) for r in new])
        matching = [r for r in rows if all(str(r.get(c)) == v for c, v in self.filters)]
        if self.action == "update":
            for row in matching:
                candidate = {**row, **self.payload}
                self._check_unique(candidate, [r for r in rows if r is not row])
                row.update(self.payload)
        if self.action == "delete":
            self.db.tables[self.name] = [r for r in rows if r not in matching]
            self._cascade(matching)
        if self.ordering is not None:
            column, desc = self.ordering
            matching = sorted(matching, key=lambda r: r[column], reverse=desc)
        if self.max_rows is not None:
            matching = matching[: self.max_rows]
        return SimpleNamespace(data=[dict(r) for r in matching])

    def _new_row(self, row: dict[str, Any]) -> dict[str, Any]:
        created = datetime.now(UTC).isoformat()
        base = {"id": str(uuid4()), **DEFAULTS[self.name], **row}
        if self.name != "solve_results":
            base.setdefault("created_at", created)
        return base

    def _check_unique(self, row: dict[str, Any], others: list[dict[str, Any]]) -> None:
        columns = UNIQUE.get(self.name)
        if columns and any(all(o[c] == row[c] for c in columns) for o in others):
            raise APIError(
                {
                    "code": "23505",
                    "message": "duplicate key value",
                    "details": None,
                    "hint": None,
                }
            )

    def _cascade(self, deleted: list[dict[str, Any]]) -> None:
        ids = {r["id"] for r in deleted}
        children = {
            "rooms": [("patients", "room_id"), ("solves", "room_id")],
            "solves": [("solve_results", "solve_id")],
        }
        for table, column in children.get(self.name, []):
            gone = [r for r in self.db.tables[table] if r[column] in ids]
            self.db.tables[table] = [
                r for r in self.db.tables[table] if r[column] not in ids
            ]
            if gone:
                FakeQuery(self.db, table)._cascade(gone)


def _as_list(payload: Any) -> list[dict[str, Any]]:
    return payload if isinstance(payload, list) else [payload]


def network_error() -> Exception:
    return httpx.ConnectError("sin red")
