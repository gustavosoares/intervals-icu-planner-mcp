"""A small intervals.icu API client.

It knows nothing about MCP, plans or uids: it sends requests and returns JSON.
Authentication is any ``httpx.Auth``, so OAuth can be added later without
touching the callers; :meth:`IntervalsClient.from_api_key` covers the API-key case.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from types import TracebackType
from typing import Any

import httpx

BASE_URL = "https://intervals.icu/api/v1"
USER_AGENT = "intervals-icu-planner-mcp"

JSON = dict[str, Any]


class ApiError(Exception):
    """A request to intervals.icu failed. The message never contains credentials."""

    def __init__(self, message: str, status: int | None = None):
        self.status = status
        super().__init__(message)


class IntervalsClient:
    def __init__(
        self,
        auth: httpx.Auth,
        *,
        athlete_id: str = "0",
        base_url: str = BASE_URL,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ):
        # athlete "0" means "the athlete who owns the credentials".
        self._http = httpx.Client(
            base_url=f"{base_url.rstrip('/')}/athlete/{athlete_id}",
            auth=auth,
            timeout=timeout,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            transport=transport,
        )

    @classmethod
    def from_api_key(cls, api_key: str, **kwargs: Any) -> IntervalsClient:
        return cls(httpx.BasicAuth("API_KEY", api_key), **kwargs)

    def __repr__(self) -> str:
        return f"IntervalsClient(base_url={str(self._http.base_url)!r})"

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> IntervalsClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        body: Any = None,
    ) -> Any:
        try:
            resp = self._http.request(method, path, params=params, json=body)
        except httpx.HTTPError as e:
            raise ApiError(f"cannot reach intervals.icu ({type(e).__name__})") from None
        if resp.status_code in (401, 403):
            raise ApiError(
                f"HTTP {resp.status_code} from {method} {path}: check your intervals.icu API key",
                resp.status_code,
            )
        if resp.is_error:
            detail = resp.text[:300].strip()
            raise ApiError(
                f"HTTP {resp.status_code} from {method} {path}: {detail}", resp.status_code
            )
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            raise ApiError(f"{method} {path}: response is not JSON") from None

    # ------------------------------------------------------------------ events

    def list_events(self, oldest: dt.date, newest: dt.date) -> list[JSON]:
        """Calendar events (planned workouts, notes, ...) between two dates, inclusive."""
        params = {"oldest": oldest.isoformat(), "newest": newest.isoformat()}
        return self._request("GET", "/events", params) or []

    def upsert_events(self, events: Sequence[JSON]) -> list[JSON]:
        """Create events, updating any with a matching external_id."""
        res = self._request("POST", "/events/bulk", {"upsert": "true"}, list(events))
        return res or []

    def delete_events(self, ids: Sequence[int]) -> int:
        """Delete events by id. Returns how many intervals.icu deleted."""
        body = [{"id": i} for i in ids]
        res = self._request("PUT", "/events/bulk-delete", body=body) or {}
        return int(res.get("eventsDeleted", len(body)))

    # ------------------------------------------------------- fitness/activities

    def list_wellness(self, oldest: dt.date, newest: dt.date) -> list[JSON]:
        """Daily wellness records, including ctl (fitness) and atl (fatigue)."""
        params = {"oldest": oldest.isoformat(), "newest": newest.isoformat()}
        return self._request("GET", "/wellness", params) or []

    def list_folders(self) -> list[JSON]:
        """The workout library: folders and plans, each with its workouts in ``children``."""
        return self._request("GET", "/folders") or []

    def list_activities(self, oldest: dt.date, newest: dt.date) -> list[JSON]:
        """Completed activities, newest first. Strava imports come back as stubs."""
        params = {"oldest": oldest.isoformat(), "newest": newest.isoformat()}
        return self._request("GET", "/activities", params) or []
