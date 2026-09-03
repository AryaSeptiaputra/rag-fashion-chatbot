"""Fixture bersama: Supabase palsu supaya test jalan tanpa jaringan."""

from typing import Any

import pytest


class FakeResponse:
    """Tiruan APIResponse PostgREST."""

    def __init__(self, data: Any) -> None:
        self.data = data


class FakeQuery:
    """Tiruan query builder PostgREST dengan chaining seperti aslinya."""

    def __init__(self, rows: list[dict[str, Any]], recorder: dict[str, Any]) -> None:
        self._rows = rows
        self._recorder = recorder

    def select(self, *_args: Any, **_kwargs: Any) -> "FakeQuery":
        return self

    def insert(self, payload: Any) -> "FakeQuery":
        self._recorder.setdefault("inserts", []).append(payload)
        rows = payload if isinstance(payload, list) else [payload]
        self._rows = [{"id": f"generated-{index}", **row} for index, row in enumerate(rows)]
        return self

    def update(self, payload: dict[str, Any]) -> "FakeQuery":
        self._recorder.setdefault("updates", []).append(payload)
        return self

    def delete(self) -> "FakeQuery":
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self._recorder.setdefault("filters", []).append((column, value))
        return self

    def neq(self, _column: str, _value: Any) -> "FakeQuery":
        return self

    def gt(self, _column: str, _value: Any) -> "FakeQuery":
        return self

    def order(self, *_args: Any, **_kwargs: Any) -> "FakeQuery":
        return self

    def limit(self, count: int) -> "FakeQuery":
        self._rows = self._rows[:count]
        return self

    def execute(self) -> FakeResponse:
        return FakeResponse(self._rows)


class FakeSupabaseClient:
    """Client Supabase palsu yang mengembalikan baris yang sudah disiapkan test."""

    def __init__(
        self,
        table_rows: dict[str, list[dict[str, Any]]] | None = None,
        rpc_rows: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self.table_rows = table_rows or {}
        self.rpc_rows = rpc_rows or {}
        self.calls: dict[str, Any] = {}

    def table(self, name: str) -> FakeQuery:
        """Kembalikan query builder untuk sebuah tabel/view."""
        self.calls.setdefault("tables", []).append(name)
        return FakeQuery(list(self.table_rows.get(name, [])), self.calls)

    def rpc(self, name: str, params: dict[str, Any]) -> FakeQuery:
        """Kembalikan query builder untuk sebuah RPC."""
        self.calls.setdefault("rpc", []).append((name, params))
        return FakeQuery(list(self.rpc_rows.get(name, [])), self.calls)


@pytest.fixture
def fake_supabase() -> type[FakeSupabaseClient]:
    """Sediakan kelas client Supabase palsu untuk dipakai test."""
    return FakeSupabaseClient
