"""Thin async PostgREST client (service role). The API is the single writer to
Supabase (research R9); clients only ever read their own rows via RLS."""

from typing import Any

import httpx


class SupabaseRest:
    def __init__(self, client: httpx.AsyncClient, url: str, service_role_key: str) -> None:
        self._client = client
        self._rest_url = f"{url.rstrip('/')}/rest/v1"
        self._headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
        }

    async def rpc(self, function: str, payload: dict) -> Any:
        response = await self._client.post(
            f"{self._rest_url}/rpc/{function}", json=payload, headers=self._headers
        )
        response.raise_for_status()
        # A `returns void` function answers 204 with no body on PostgREST
        # 14+ (older versions sent 200 `null`); both mean "no value".
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    async def insert(self, table: str, rows: list[dict]) -> None:
        response = await self._client.post(
            f"{self._rest_url}/{table}",
            json=rows,
            headers={**self._headers, "Prefer": "return=minimal"},
        )
        response.raise_for_status()

    async def upsert(self, table: str, row: dict, on_conflict: str) -> dict | None:
        response = await self._client.post(
            f"{self._rest_url}/{table}",
            params={"on_conflict": on_conflict},
            json=row,
            headers={
                **self._headers,
                "Prefer": "resolution=merge-duplicates,return=representation",
            },
        )
        response.raise_for_status()
        rows = response.json()
        return rows[0] if rows else None

    async def select_one(self, table: str, filters: dict[str, str], columns: str) -> dict | None:
        params = {"select": columns, **{k: f"eq.{v}" for k, v in filters.items()}, "limit": "1"}
        response = await self._client.get(
            f"{self._rest_url}/{table}", params=params, headers=self._headers
        )
        response.raise_for_status()
        rows = response.json()
        return rows[0] if rows else None

    async def select_many(
        self,
        table: str,
        filters: dict[str, str],
        columns: str,
        order: str | None = None,
        limit: int | None = None,
        raw_filters: dict[str, str] | None = None,
    ) -> list[dict]:
        """`raw_filters`: pre-built PostgREST operator strings (e.g.
        `{"sent_at": "gte.2026-07-01T00:00:00Z"}`) for callers that need
        something other than equality (004's frequency-cap window counts) —
        `filters` stays eq-only so every existing call site is unaffected."""
        params: dict[str, str] = {
            "select": columns,
            **{k: f"eq.{v}" for k, v in filters.items()},
            **(raw_filters or {}),
        }
        if order:
            params["order"] = order
        if limit:
            params["limit"] = str(limit)
        response = await self._client.get(
            f"{self._rest_url}/{table}", params=params, headers=self._headers
        )
        response.raise_for_status()
        return response.json()

    async def update(self, table: str, filters: dict[str, str], patch: dict) -> None:
        params = {k: f"eq.{v}" for k, v in filters.items()}
        response = await self._client.patch(
            f"{self._rest_url}/{table}",
            params=params,
            json=patch,
            headers={**self._headers, "Prefer": "return=minimal"},
        )
        response.raise_for_status()

    async def delete(self, table: str, filters: dict[str, str]) -> None:
        params = {k: f"eq.{v}" for k, v in filters.items()}
        response = await self._client.delete(
            f"{self._rest_url}/{table}",
            params=params,
            headers={**self._headers, "Prefer": "return=minimal"},
        )
        response.raise_for_status()
