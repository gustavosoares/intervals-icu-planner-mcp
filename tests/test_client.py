import base64
import datetime as dt

import httpx
import pytest
import respx

from intervals_icu_planner_mcp.client import ApiError, IntervalsClient

from .conftest import API, FAKE_KEY

D1, D2 = dt.date(2026, 12, 1), dt.date(2026, 12, 7)


@respx.mock
def test_basic_auth_and_query(client):
    route = respx.get(f"{API}/events").mock(return_value=httpx.Response(200, json=[{"id": 1}]))
    assert client.list_events(D1, D2) == [{"id": 1}]
    req = route.calls.last.request
    expected = base64.b64encode(f"API_KEY:{FAKE_KEY}".encode()).decode()
    assert req.headers["Authorization"] == f"Basic {expected}"
    assert dict(req.url.params) == {"oldest": "2026-12-01", "newest": "2026-12-07"}


@respx.mock
def test_upsert_uses_bulk_endpoint(client):
    route = respx.post(f"{API}/events/bulk").mock(
        return_value=httpx.Response(200, json=[{"id": 5}])
    )
    assert client.upsert_events([{"uid": "u"}]) == [{"id": 5}]
    req = route.calls.last.request
    assert req.url.params["upsert"] == "true"
    assert req.content == b'[{"uid":"u"}]'


@respx.mock
def test_delete_by_id(client):
    route = respx.put(f"{API}/events/bulk-delete").mock(
        return_value=httpx.Response(200, json={"eventsDeleted": 2})
    )
    assert client.delete_events([3, 4]) == 2
    assert route.calls.last.request.content == b'[{"id":3},{"id":4}]'


@respx.mock
def test_wellness_and_activities(client):
    respx.get(f"{API}/wellness").mock(return_value=httpx.Response(200, json=[{"id": "2026-12-01"}]))
    respx.get(f"{API}/activities").mock(return_value=httpx.Response(200, json=[]))
    assert client.list_wellness(D1, D2) == [{"id": "2026-12-01"}]
    assert client.list_activities(D1, D2) == []


@respx.mock
@pytest.mark.parametrize("status", [401, 403])
def test_auth_errors_never_echo_the_key(client, status):
    respx.get(f"{API}/events").mock(return_value=httpx.Response(status, text=f"bad {FAKE_KEY}?"))
    with pytest.raises(ApiError) as e:
        client.list_events(D1, D2)
    assert e.value.status == status
    assert "check your intervals.icu API key" in str(e.value)
    assert FAKE_KEY not in str(e.value)


@respx.mock
def test_http_error_detail(client):
    respx.post(f"{API}/events/bulk").mock(return_value=httpx.Response(422, text="bad workout"))
    with pytest.raises(ApiError, match="HTTP 422 from POST /events/bulk: bad workout"):
        client.upsert_events([])


@respx.mock
def test_network_error(client):
    respx.get(f"{API}/events").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(ApiError, match=r"cannot reach intervals.icu \(ConnectError\)"):
        client.list_events(D1, D2)


@respx.mock
def test_non_json(client):
    respx.get(f"{API}/events").mock(return_value=httpx.Response(200, text="<html>"))
    with pytest.raises(ApiError, match="not JSON"):
        client.list_events(D1, D2)


def test_repr_hides_the_key():
    c = IntervalsClient.from_api_key(FAKE_KEY)
    assert FAKE_KEY not in repr(c)
    assert FAKE_KEY not in repr(c._http.auth)
    c.close()
