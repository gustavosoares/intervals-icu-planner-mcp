"""Sign in with intervals.icu: PKCE, the local callback, token storage, credentials."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import stat
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest
import respx

from intervals_icu_planner_mcp import cli, config, oauth, server
from intervals_icu_planner_mcp.client import ApiError, IntervalsClient

from .conftest import API, FAKE_KEY

TOKEN = "tok-not-real-123"
CODE = "code-not-real-456"
TOKEN_JSON = {
    "token_type": "Bearer",
    "access_token": TOKEN,
    "scope": "CALENDAR:WRITE,LIBRARY:READ,WELLNESS:READ,ACTIVITY:READ",
    "athlete": {"id": "i42", "name": "Test Athlete"},
}


def params_of(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


class TokenEndpoint:
    """A fake intervals.icu token endpoint (an httpx transport) that records requests."""

    def __init__(self, response: httpx.Response | None = None):
        self.response = response or httpx.Response(200, json=TOKEN_JSON)
        self.forms: list[dict[str, str]] = []
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        assert str(request.url) == oauth.TOKEN_URL
        self.forms.append({k: v[0] for k, v in parse_qs(request.content.decode()).items()})
        return self.response


def browser(**override: str):
    """A fake browser: approves at once by calling the redirect with a code."""
    pages: list[str] = []

    def open_url(url: str) -> None:
        p = params_of(url)
        query = {"code": CODE, "state": p["state"], **override}
        with urllib.request.urlopen(f"{p['redirect_uri']}?{urlencode(query)}", timeout=5) as r:
            pages.append(r.read().decode())

    open_url.pages = pages  # type: ignore[attr-defined]
    return open_url


def store():
    return oauth.default_store()  # the per-test file store from conftest


# ----------------------------------------------------------------------- PKCE


def test_challenge_is_unpadded_base64url_sha256_of_the_verifier():
    import base64
    import hashlib

    verifier = oauth.make_verifier()
    challenge = oauth.challenge_for(verifier)
    assert "=" not in challenge and len(challenge) == 43
    decoded = base64.urlsafe_b64decode(challenge + "=")
    assert decoded == hashlib.sha256(verifier.encode()).digest()


def test_verifier_is_long_enough_and_url_safe():
    v = oauth.make_verifier()
    assert 43 <= len(v) <= 128
    assert set(v) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


def test_authorize_url():
    url = oauth.authorize_url(port=5123, state="s1", verifier="v" * 50)
    assert url.startswith("https://intervals.icu/oauth/authorize?")
    assert params_of(url) == {
        "client_id": "2022",
        "redirect_uri": "http://localhost:5123/callback",
        "response_type": "code",
        "scope": "CALENDAR:WRITE,LIBRARY:READ,WELLNESS:READ,ACTIVITY:READ",
        "state": "s1",
        "code_challenge": oauth.challenge_for("v" * 50),
        "code_challenge_method": "S256",
    }


# -------------------------------------------------------------------- sign-in


def test_login_exchanges_the_code_with_pkce_and_saves_the_token():
    endpoint = TokenEndpoint()
    b = browser()
    login = oauth.Login(open_browser=b, transport=endpoint.transport, timeout=10)
    challenge = params_of(login.url)["code_challenge"]
    login.start()
    assert login.wait(10)

    assert login.error is None
    assert login.token is not None and login.token.who == "Test Athlete"
    (form,) = endpoint.forms
    assert form["client_id"] == "2022"
    assert form["code"] == CODE
    assert oauth.challenge_for(form["code_verifier"]) == challenge
    assert form["redirect_uri"] == f"http://localhost:{login.port}/callback"
    assert "client_secret" not in form
    assert "Connected as Test Athlete" in b.pages[0]

    saved = oauth.load_token()
    assert saved is not None and saved.access_token == TOKEN and saved.athlete_id == "i42"


def test_a_callback_with_the_wrong_state_is_ignored():
    endpoint = TokenEndpoint()
    login = oauth.Login(open_browser=lambda url: None, transport=endpoint.transport, timeout=10)
    login.start()
    redirect = oauth.redirect_uri(login.port)
    with urllib.request.urlopen(f"{redirect}?code=evil&state=forged", timeout=5) as r:
        assert "not recognised" in r.read().decode()
    assert not login.finished
    assert endpoint.forms == []

    state = params_of(login.url)["state"]
    urllib.request.urlopen(f"{redirect}?code={CODE}&state={state}", timeout=5).close()
    assert login.wait(10) and login.token is not None


def test_declining_access():
    login = oauth.Login(open_browser=browser(error="access_denied"), timeout=10).start()
    assert login.wait(10)
    assert login.token is None
    assert login.error == "you declined access"
    assert oauth.load_token() is None


def test_a_refused_exchange_saves_nothing_and_never_echoes_the_code():
    endpoint = TokenEndpoint(httpx.Response(400, text=f"bad code {CODE}"))
    login = oauth.Login(open_browser=browser(), transport=endpoint.transport, timeout=10)
    login.start()
    assert login.wait(10)
    assert login.error == "intervals.icu refused the sign-in (HTTP 400)"
    assert CODE not in login.error
    assert oauth.load_token() is None


def test_login_times_out():
    login = oauth.Login(open_browser=lambda url: None, timeout=0.2).start()
    assert login.wait(5)
    assert login.error == "timed out waiting for the browser"


def test_other_paths_on_the_callback_server_are_404():
    login = oauth.Login(open_browser=lambda url: None, timeout=10).start()
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(f"http://localhost:{login.port}/favicon.ico", timeout=5)
    assert e.value.code == 404
    login.cancel()


# -------------------------------------------------------------------- storage


def test_file_store_is_private(tmp_path):
    s = oauth.FileStore(tmp_path / "cfg" / "token.json")
    oauth.save_token(oauth.Token(TOKEN, athlete_name="A"), s)
    assert stat.S_IMODE((tmp_path / "cfg" / "token.json").stat().st_mode) == 0o600
    loaded = oauth.load_token(s)
    assert loaded is not None and loaded.access_token == TOKEN
    s.clear()
    assert oauth.load_token(s) is None
    s.clear()  # twice is fine


def test_a_corrupt_entry_counts_as_signed_out(tmp_path):
    s = oauth.FileStore(tmp_path / "token.json")
    s.save("not json")
    assert oauth.load_token(s) is None
    s.save(json.dumps({"scope": "x"}))
    assert oauth.load_token(s) is None


def test_token_repr_hides_the_token():
    t = oauth.Token(TOKEN, athlete_name="A")
    assert TOKEN not in repr(t)


# ---------------------------------------------------------------- credentials


def test_the_api_key_is_used_first():
    oauth.save_token(oauth.Token(TOKEN))
    c = config.make_client({config.ENV_VAR: FAKE_KEY})
    assert c is not None and c.oauth_client_id is None
    c.close()


def test_a_saved_sign_in_is_used_without_a_key():
    oauth.save_token(oauth.Token(TOKEN))
    c = config.make_client({})
    assert c is not None and c.oauth_client_id == oauth.CLIENT_ID
    assert TOKEN not in repr(c)
    c.close()


def test_an_unfilled_desktop_key_field_counts_as_unset():
    assert config.find_api_key({config.ENV_VAR: "${user_config.api_key}"}) is None
    assert config.make_client({config.ENV_VAR: "${user_config.api_key}"}) is None


@respx.mock
def test_requests_send_the_bearer_token_and_a_401_says_to_connect_again():
    route = respx.get(f"{API}/wellness").mock(return_value=httpx.Response(401))
    day = dt.date(2026, 1, 1)
    with IntervalsClient.from_token(TOKEN, oauth_client_id=2022) as c, pytest.raises(ApiError) as e:
        c.list_wellness(day, day)
    assert route.calls.last.request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert "connect again" in str(e.value)
    assert TOKEN not in str(e.value)


def test_disconnect_revokes_with_the_bearer_token():
    seen: list[httpx.Request] = []

    def handle(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200)

    assert oauth.disconnect(oauth.Token(TOKEN), transport=httpx.MockTransport(handle))
    assert seen[0].method == "DELETE" and str(seen[0].url) == oauth.DISCONNECT_URL
    assert seen[0].headers["Authorization"] == f"Bearer {TOKEN}"

    already = httpx.MockTransport(lambda r: httpx.Response(401))
    assert oauth.disconnect(oauth.Token(TOKEN), transport=already)

    def down(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    assert not oauth.disconnect(oauth.Token(TOKEN), transport=httpx.MockTransport(down))


# ----------------------------------------------------------------- front ends


class FakeLogin:
    """Stands in for oauth.Login: finishes at once with a token."""

    def __init__(self, **kw: Any):
        self.url = "https://intervals.icu/oauth/authorize?fake"
        self.token: oauth.Token | None = oauth.Token(TOKEN, athlete_name="Test Athlete")
        self.error: str | None = None

    def start(self) -> FakeLogin:
        if self.token:
            oauth.save_token(self.token)
        return self

    def wait(self, timeout: float | None = None) -> bool:
        return True

    @property
    def finished(self) -> bool:
        return True


@pytest.fixture
def fake_login(monkeypatch):
    monkeypatch.setattr(oauth, "Login", FakeLogin)
    monkeypatch.setattr(server, "_login", None)


def call_tool(name: str, **args: Any) -> str:
    result = asyncio.run(server.mcp.call_tool(name, args))
    return str(result)


def test_connect_tool_signs_in(fake_login):
    assert "Connected to intervals.icu as Test Athlete" in call_tool("connect")
    assert "Already connected to intervals.icu as Test Athlete" in call_tool("connect")
    assert "Connected to intervals.icu as" in call_tool("connect", again=True)


def test_connect_tool_with_an_api_key_does_nothing(fake_login, monkeypatch):
    monkeypatch.setenv(config.ENV_VAR, FAKE_KEY)
    assert "Already connected with an intervals.icu API key" in call_tool("connect")


def test_connect_tool_reports_a_waiting_sign_in(monkeypatch):
    class Pending(FakeLogin):
        def __init__(self, **kw: Any):
            super().__init__()
            self.token = None

        def wait(self, timeout: float | None = None) -> bool:
            return False

        @property
        def finished(self) -> bool:
            return False

    monkeypatch.setattr(oauth, "Login", Pending)
    monkeypatch.setattr(server, "_login", None)
    out = call_tool("connect")
    assert "Waiting for the user to approve" in out
    assert "https://intervals.icu/oauth/authorize?fake" in out


def test_cli_login_and_logout(fake_login, capsys, monkeypatch):
    assert cli.main(["login"]) == 0
    assert "Connected to intervals.icu as Test Athlete" in capsys.readouterr().out

    revoked: list[oauth.Token] = []

    def disconnect(token: oauth.Token) -> bool:
        revoked.append(token)
        return True

    monkeypatch.setattr(oauth, "disconnect", disconnect)
    assert cli.main(["logout"]) == 0
    assert "Signed out" in capsys.readouterr().out
    assert revoked[0].access_token == TOKEN
    assert oauth.load_token() is None
    assert cli.main(["logout"]) == 0
    assert "Not signed in" in capsys.readouterr().out


def test_cli_login_failure(monkeypatch, capsys):
    class Declined(FakeLogin):
        def __init__(self, **kw: Any):
            super().__init__()
            self.token, self.error = None, "you declined access"

    monkeypatch.setattr(oauth, "Login", Declined)
    assert cli.main(["login"]) == 1
    assert "not connected: you declined access" in capsys.readouterr().err
    assert oauth.load_token() is None
