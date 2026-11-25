"""Sign in with intervals.icu: OAuth 2 for a public client, with PKCE.

The app is registered on intervals.icu as a public client, so there is no
client secret: PKCE (S256) proves the token request comes from whoever started
the sign-in. The browser is sent back to ``http://localhost:<port>/callback``,
where a one-shot local server picks up the code (intervals.icu ignores the
port of a registered localhost redirect).

intervals.icu access tokens don't expire and there are no refresh tokens. A
new sign-in replaces the previous token.

The token is kept in the system keychain (via ``keyring``), or, where no
keychain is available, in a file only the user can read. It is never printed
or logged.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import html
import json
import os
import secrets
import threading
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

CLIENT_ID = 2022
AUTHORIZE_URL = "https://intervals.icu/oauth/authorize"
TOKEN_URL = "https://intervals.icu/api/oauth/token"
DISCONNECT_URL = "https://intervals.icu/api/v1/disconnect-app"
# CALENDAR: planned workouts and notes. LIBRARY: the workout library (list_library).
SCOPES = ("CALENDAR:WRITE", "LIBRARY:READ", "WELLNESS:READ", "ACTIVITY:READ")
CALLBACK_PATH = "/callback"
LOGIN_TIMEOUT = 300.0  # seconds to wait for the user to approve in the browser
USER_AGENT = "intervals-icu-planner-mcp"

KEYRING_SERVICE = "intervals-icu-planner-mcp"
KEYRING_USER = "oauth-token"


class OAuthError(Exception):
    """Signing in failed. The message never contains a code or a token."""


@dataclass(frozen=True)
class Token:
    access_token: str = field(repr=False)
    scope: str = ""
    athlete_id: str = ""
    athlete_name: str = ""

    def to_json(self) -> str:
        return json.dumps(
            {
                "access_token": self.access_token,
                "scope": self.scope,
                "athlete_id": self.athlete_id,
                "athlete_name": self.athlete_name,
            }
        )

    @classmethod
    def from_response(cls, data: Any) -> Token:
        if not isinstance(data, dict) or not data.get("access_token"):
            raise OAuthError("intervals.icu sent no access token")
        athlete = data.get("athlete")
        if not isinstance(athlete, dict):
            athlete = {}
        return cls(
            access_token=str(data["access_token"]),
            scope=str(data.get("scope") or ""),
            athlete_id=str(athlete.get("id") or data.get("athlete_id") or ""),
            athlete_name=str(athlete.get("name") or data.get("athlete_name") or ""),
        )

    @property
    def who(self) -> str:
        return self.athlete_name or self.athlete_id or "your intervals.icu account"


# -------------------------------------------------------------------- storage


class TokenStore(Protocol):
    def load(self) -> str | None: ...
    def save(self, value: str) -> None: ...
    def clear(self) -> None: ...


class KeyringStore:
    """The system keychain: macOS Keychain, Windows Credential Manager, Secret Service."""

    def load(self) -> str | None:
        import keyring

        return keyring.get_password(KEYRING_SERVICE, KEYRING_USER)

    def save(self, value: str) -> None:
        import keyring

        keyring.set_password(KEYRING_SERVICE, KEYRING_USER, value)

    def clear(self) -> None:
        import keyring
        import keyring.errors

        with contextlib.suppress(keyring.errors.PasswordDeleteError):
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)


class FileStore:
    """A JSON file readable only by the user, for systems without a keychain."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> str | None:
        try:
            return self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def save(self, value: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(value)
        os.replace(tmp, self.path)

    def clear(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()


def _config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "intervals-icu-planner"


def _keyring_usable() -> bool:
    try:
        import keyring
        from keyring.backends import fail
    except Exception:  # pragma: no cover - keyring is a dependency
        return False
    try:
        backend = keyring.get_keyring()
    except Exception:  # pragma: no cover - a broken keyring config
        return False
    return not isinstance(backend, fail.Keyring) and getattr(backend, "priority", 0) > 0


def default_store() -> TokenStore:
    """The keychain if there is one, otherwise ``~/.config/intervals-icu-planner/token.json``."""
    if _keyring_usable():
        return KeyringStore()
    return FileStore(_config_dir() / "token.json")


def load_token(store: TokenStore | None = None) -> Token | None:
    """The saved sign-in, or None. An unreadable or corrupt entry counts as none."""
    store = store or default_store()
    try:
        raw = store.load()
    except Exception:
        return None
    if not raw:
        return None
    try:
        return Token.from_response(json.loads(raw))
    except (ValueError, OAuthError):
        return None


def save_token(token: Token, store: TokenStore | None = None) -> None:
    (store or default_store()).save(token.to_json())


# ----------------------------------------------------------------------- PKCE


def make_verifier() -> str:
    """A PKCE code verifier: 64 URL-safe characters (RFC 7636 allows 43-128)."""
    return secrets.token_urlsafe(48)


def challenge_for(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def redirect_uri(port: int) -> str:
    return f"http://localhost:{port}{CALLBACK_PATH}"


def authorize_url(*, port: int, state: str, verifier: str) -> str:
    params = {
        "client_id": str(CLIENT_ID),
        "redirect_uri": redirect_uri(port),
        "response_type": "code",
        "scope": ",".join(SCOPES),
        "state": state,
        "code_challenge": challenge_for(verifier),
        "code_challenge_method": "S256",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code(
    code: str, *, port: int, verifier: str, transport: httpx.BaseTransport | None = None
) -> Token:
    """Trade the authorization code for an access token (no client secret: PKCE)."""
    data = {
        "client_id": str(CLIENT_ID),
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": redirect_uri(port),
        "grant_type": "authorization_code",
    }
    try:
        with httpx.Client(
            timeout=30.0, headers={"User-Agent": USER_AGENT}, transport=transport
        ) as http:
            resp = http.post(TOKEN_URL, data=data, headers={"Accept": "application/json"})
    except httpx.HTTPError as e:
        raise OAuthError(f"cannot reach intervals.icu ({type(e).__name__})") from None
    if resp.is_error:
        # The body may echo the code; keep only a short, code-free summary.
        raise OAuthError(f"intervals.icu refused the sign-in (HTTP {resp.status_code})")
    try:
        return Token.from_response(resp.json())
    except ValueError:
        raise OAuthError("intervals.icu sent an unreadable token response") from None


def disconnect(token: Token, *, transport: httpx.BaseTransport | None = None) -> bool:
    """Ask intervals.icu to revoke the token. False if that failed (the caller still forgets it)."""
    try:
        with httpx.Client(
            timeout=30.0, headers={"User-Agent": USER_AGENT}, transport=transport
        ) as http:
            resp = http.delete(
                DISCONNECT_URL, headers={"Authorization": f"Bearer {token.access_token}"}
            )
    except httpx.HTTPError:
        return False
    return resp.is_success or resp.status_code == 401  # 401: already revoked


# ------------------------------------------------------------------- sign-in

_PAGE = """<!doctype html><meta charset="utf-8"><title>intervals.icu Planner</title>
<body style="font-family: system-ui, sans-serif; max-width: 32em; margin: 4em auto">
<h1>{title}</h1><p>{text}</p></body>"""


class Login:
    """One sign-in attempt: a local callback server waiting for the browser.

    :meth:`start` opens the browser and returns at once; the server runs in a
    background thread until the callback arrives, the attempt times out, or
    :meth:`cancel` is called. :meth:`wait` blocks for the result.
    """

    def __init__(
        self,
        *,
        store: TokenStore | None = None,
        open_browser: Callable[[str], Any] = webbrowser.open,
        timeout: float = LOGIN_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ):
        self._store = store
        self._open_browser = open_browser
        self._timeout = timeout
        self._transport = transport
        self._verifier = make_verifier()
        self._state = secrets.token_urlsafe(24)
        self._done = threading.Event()
        self.token: Token | None = None
        self.error: str | None = None
        self._server = HTTPServer(("127.0.0.1", 0), self._handler())
        self.port: int = self._server.server_address[1]
        self.url = authorize_url(port=self.port, state=self._state, verifier=self._verifier)

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        login = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parts = urlsplit(self.path)
                if parts.path != CALLBACK_PATH:
                    self.send_error(404)
                    return
                title, text = login._callback(parse_qs(parts.query))
                body = _PAGE.format(title=html.escape(title), text=html.escape(text))
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))

            def log_message(self, format: str, *args: Any) -> None:
                pass  # the URL holds the code: never log it

        return Handler

    def _callback(self, query: dict[str, list[str]]) -> tuple[str, str]:
        if self._done.is_set():
            return "Already handled", "You can close this tab."
        state = query.get("state", [""])[0]
        if not secrets.compare_digest(state, self._state):
            # Not ours (or forged): ignore it and keep waiting for the real one.
            return "Sign-in not recognised", "Start the sign-in again from Claude or the CLI."
        if "error" in query:
            denied = query["error"][0] == "access_denied"
            self._finish(error="you declined access" if denied else "intervals.icu sent an error")
            return "Not connected", "You can close this tab."
        code = query.get("code", [""])[0]
        if not code:
            self._finish(error="intervals.icu sent no authorization code")
            return "Not connected", "Something went wrong. Please try again."
        try:
            token = exchange_code(
                code, port=self.port, verifier=self._verifier, transport=self._transport
            )
            save_token(token, self._store)
        except OAuthError as e:
            self._finish(error=str(e))
            return "Not connected", str(e)
        except Exception as e:  # e.g. the keychain refused
            self._finish(error=f"could not save the sign-in ({type(e).__name__})")
            return "Not connected", "Could not save the sign-in on this computer."
        self._finish(token=token)
        return (
            f"Connected as {token.who}",
            "intervals.icu Planner can now use your calendar. You can close this tab.",
        )

    def _finish(self, *, token: Token | None = None, error: str | None = None) -> None:
        self.token, self.error = token, error
        self._done.set()

    def _serve(self) -> None:
        self._server.timeout = 0.5
        deadline = threading.Event()
        timer = threading.Timer(self._timeout, deadline.set)
        timer.daemon = True
        timer.start()
        try:
            while not self._done.is_set():
                if deadline.is_set():
                    self._finish(error="timed out waiting for the browser")
                    break
                self._server.handle_request()
        finally:
            timer.cancel()
            self._server.server_close()

    def start(self) -> Login:
        threading.Thread(target=self._serve, name="oauth-callback", daemon=True).start()
        with contextlib.suppress(Exception):
            self._open_browser(self.url)
        return self

    def wait(self, timeout: float | None = None) -> bool:
        """True once the attempt has finished (check ``token`` or ``error``)."""
        return self._done.wait(timeout)

    def cancel(self) -> None:
        if not self._done.is_set():
            self._finish(error="cancelled")

    @property
    def finished(self) -> bool:
        return self._done.is_set()
