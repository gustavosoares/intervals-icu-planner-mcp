"""Tiny intervals.icu API client (stdlib only)."""

from __future__ import annotations

import base64
import datetime as dt
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

BASE_URL = "https://intervals.icu/api/v1/athlete/0"


class ApiError(Exception):
    pass


def auth_header(api_key: str) -> str:
    token = base64.b64encode(f"API_KEY:{api_key}".encode()).decode()
    return f"Basic {token}"


class Client:
    def __init__(self, api_key: str, base_url: str = BASE_URL, timeout: float = 60):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def build_request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None,
                      body: Any = None) -> urllib.request.Request:
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        data = None
        headers = {"Authorization": auth_header(self.api_key), "Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        return urllib.request.Request(url, data=data, method=method, headers=headers)

    def _send(self, req: urllib.request.Request) -> Any:
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            raise ApiError(f"HTTP {e.code} from {req.get_method()} {req.full_url}: {detail}") from None
        except urllib.error.URLError as e:
            raise ApiError(f"cannot reach intervals.icu: {e.reason}") from None
        return json.loads(raw) if raw else None

    def upsert_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        req = self.build_request("POST", "/events/bulk", {"upsert": "true"}, events)
        return self._send(req) or []

    def list_events(self, oldest: dt.date, newest: dt.date) -> List[Dict[str, Any]]:
        params = {"oldest": oldest.isoformat(), "newest": newest.isoformat()}
        return self._send(self.build_request("GET", "/events", params)) or []

    def delete_events(self, ids: List[int]) -> int:
        body = [{"id": i} for i in ids]
        res = self._send(self.build_request("PUT", "/events/bulk-delete", body=body)) or {}
        return int(res.get("eventsDeleted", len(ids)))
