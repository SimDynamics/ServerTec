"""Focused adversarial tests for the isolated, explicitly enabled demo listener."""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

import demo_web


HOST = b"learngraphicsprogramming.dynamics"
CHALLENGE = "f17f54fbc87e4ad297cbdceba7816be2"


def request(app, path="/", *, method="GET", headers=None, scheme="https", raw_path=None, query=b"", body=b"", more_body=False):
    async def run():
        messages = []
        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method, "scheme": scheme, "path": path,
            "raw_path": raw_path if raw_path is not None else path.encode(),
            "query_string": query, "headers": headers if headers is not None else [(b"host", HOST)],
            "client": ("127.0.0.1", 12345), "server": ("127.0.0.1", 443),
        }

        async def receive():
            return {"type": "http.request", "body": body, "more_body": more_body}

        async def send(message):
            messages.append(message)

        await app(scope, receive, send)
        start = next(message for message in messages if message["type"] == "http.response.start")
        content = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
        return start["status"], {name.decode(): value.decode() for name, value in start["headers"]}, content

    return asyncio.run(run())


@pytest.fixture
def app():
    return demo_web.create_demo_app(enable_demo=True)


def test_demo_is_closed_by_default():
    app = demo_web.create_demo_app()
    for path in ("/", "/menu.css", "/menu.js", "/demo/status"):
        assert request(app, path)[0] == 404
    assert app._assets == {}


@pytest.mark.parametrize("path,content_type", [("/", "text/html"), ("/menu.css", "text/css"), ("/menu.js", "text/javascript")])
def test_only_explicit_assets_and_bodyless_head(app, path, content_type):
    status, headers, body = request(app, path)
    head_status, head_headers, head_body = request(app, path, method="HEAD")
    assert status == head_status == 200
    assert headers["content-type"].startswith(content_type)
    assert body and not head_body
    assert int(head_headers["content-length"]) == len(body)
    assert headers["cache-control"] == "no-store, max-age=0"
    assert "access-control-allow-origin" not in headers
    assert "strict-transport-security" not in headers
    assert "worker-src 'none'" in headers["content-security-policy"]
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert headers["x-content-type-options"] == "nosniff"


def test_menu_and_scripts_have_no_external_dependencies(app):
    html = request(app)[2].decode()
    css = request(app, "/menu.css")[2].decode()
    script = request(app, "/menu.js")[2].decode()
    assert "<title>LearnGraphicsProgramming</title>" in html
    for label in ("Programación", "Matemáticas y Física", "Comprobar conexión"):
        assert label in html
    assert "Demostración: contenido todavía no integrado" in script
    assert re.findall(r'(?:src|href)="([^"]+)"', html) == ["data:,", "/menu.css", "/menu.js"]
    assert not re.search(r"https?://|//[A-Za-z]|@import|serviceWorker|localStorage|indexedDB", html + css + script)
    assert 'cache: "no-store"' in script
    assert "crypto.getRandomValues" in script
    assert "status.challenge !== challenge" in script
    assert 'credentials: "omit"' in script


@pytest.mark.parametrize("path", [
    "/health", "/docs", "/redoc", "/openapi.json", "/v1/hearts", "/v2/auth/me",
    "/v2/auth/register", "/v2/evaluations", "/v2/progress", "/admin", "/metrics",
    "/README.md", "/rules-catalog.json", "/rules-catalog-coverage.json", "/manage.py",
    "/demo_web.py", "/demo_web_assets/index.html", "/state/servertec.db", "/servertec.db",
    "/device-hmac.key", "/ca.key", "/backups", "/reports", "/.git/config", "/menu.css/",
    "/demo/status/", "/favicon.ico", "//", "/../", "/state/../menu.js",
    "/C:/Windows/win.ini", "/D:/Projects/ServerTec/state/servertec.db", "/menu.js\\..\\manage.py",
])
def test_non_allowlisted_paths_never_expose_files_or_business(app, path):
    status, headers, body = request(app, path)
    assert status == 404
    assert json.loads(body) == {"error": "not_found"}
    assert "no-store" in headers["cache-control"]


@pytest.mark.parametrize("raw_path,path", [
    (b"/%2e%2e/menu.js", "/../menu.js"),
    (b"/%6denu.js", "/menu.js"),
    (b"/%2fmenu.js", "//menu.js"),
    (b"/state/../menu.js", "/menu.js"),
    (b"/%252e%252e/manage.py", "/%2e%2e/manage.py"),
    (b"/menu.js%00", "/menu.js\x00"),
    (b"\\menu.js", "/menu.js"),
])
def test_encoded_and_normalized_paths_are_rejected(app, raw_path, path):
    assert request(app, path, raw_path=raw_path)[0] == 404


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"])
@pytest.mark.parametrize("path", ["/", "/menu.css", "/menu.js", "/demo/status"])
def test_methods_are_explicitly_restricted(app, path, method):
    status, headers, body = request(app, path, method=method)
    assert status == 405
    assert headers["allow"] == ("GET" if path == "/demo/status" else "GET, HEAD")
    assert json.loads(body) == {"error": "method_not_allowed"}


def test_status_head_is_not_exposed(app):
    status, headers, body = request(app, "/demo/status", method="HEAD")
    assert status == 405 and not body
    assert headers["allow"] == "GET"


@pytest.mark.parametrize("host", [
    b"localhost", b"127.0.0.1", b"[::1]", b"learngraphicsprogramming.dynamics.evil",
    b"learngraphicsprogramming.dynamics.", b"LEARNGRAPHICSPROGRAMMING.DYNAMICS",
    b"learngraphicsprogramming.dynamics:0", b"learngraphicsprogramming.dynamics:65536",
    b"learngraphicsprogramming.dynamics:abc", b"learngraphicsprogramming.dynamics@evil",
    b"learngraphicsprogramming.dynamics,evil", b"learngraphicsprogramming.dynamics:443:443",
])
def test_host_must_be_literal_expected_name(app, host):
    assert request(app, headers=[(b"host", host)])[0] == 400


@pytest.mark.parametrize("port", [b"443", b"8443", b"65535"])
def test_named_host_allows_explicit_test_port(app, port):
    assert request(app, headers=[(b"host", HOST + b":" + port)])[0] == 200


@pytest.mark.parametrize("hostname", demo_web.ALLOWED_DEMO_HOSTS)
@pytest.mark.parametrize("port", [b"", b":443", b":8443"])
def test_selected_hostname_is_exact_and_does_not_add_an_alias(hostname, port):
    selected = demo_web.create_demo_app(enable_demo=True, hostname=hostname)
    assert selected.hostname == hostname
    assert request(selected, headers=[(b"host", hostname.encode() + port)])[0] == 200
    other = next(name for name in demo_web.ALLOWED_DEMO_HOSTS if name != hostname)
    assert request(selected, headers=[(b"host", other.encode() + port)])[0] == 400


@pytest.mark.parametrize("suffix", [b".evil", b".", b":0", b":65536", b":abc", b"@evil", b",evil", b":443:443", b"\r\nHost: evil"])
def test_public_candidate_host_rejects_modified_names_and_invalid_ports(suffix):
    selected = demo_web.create_demo_app(enable_demo=True, hostname=demo_web.PUBLIC_DEMO_HOST)
    assert request(selected, headers=[(b"host", demo_web.PUBLIC_DEMO_HOST.encode() + suffix)])[0] == 400


def test_public_candidate_still_requires_https_and_single_host():
    selected = demo_web.create_demo_app(enable_demo=True, hostname=demo_web.PUBLIC_DEMO_HOST)
    headers = [(b"host", demo_web.PUBLIC_DEMO_HOST.encode())]
    assert request(selected, scheme="http", headers=headers)[0] == 400
    assert request(selected, headers=headers * 2)[0] == 400
    assert request(selected, headers=[(b"host", ("sub." + demo_web.PUBLIC_DEMO_HOST).encode())])[0] == 400


@pytest.mark.parametrize("hostname", ["example.org", "127.0.0.1", "https://servertec-demo-3.example.invalid/", None])
def test_unlisted_hostname_is_rejected_before_assets_are_read(monkeypatch, hostname):
    monkeypatch.setattr(Path, "read_bytes", lambda *_: pytest.fail("Must not read assets for an unlisted hostname"))
    with pytest.raises(ValueError):
        demo_web.create_demo_app(enable_demo=True, hostname=hostname)


def test_missing_or_duplicate_host_rejected(app):
    assert request(app, headers=[])[0] == 400
    assert request(app, headers=[(b"host", HOST), (b"host", HOST)])[0] == 400


@pytest.mark.parametrize("name,value", [
    (b"forwarded", b"host=learngraphicsprogramming.dynamics;proto=https"),
    (b"x-forwarded-host", HOST), (b"x-forwarded-proto", b"https"),
    (b"x-forwarded-for", b"127.0.0.1"), (b"X-Forwarded-Host", b"evil"),
])
def test_forwarding_is_not_a_path_to_trusted_host_or_https(app, name, value):
    assert request(app, headers=[(b"host", HOST), (name, value)])[0] == 400


def test_plain_http_is_rejected_without_redirect(app):
    status, headers, body = request(app, scheme="http")
    assert status == 400 and "location" not in headers
    assert json.loads(body) == {"error": "https_required"}


def test_status_is_current_echoed_and_contains_only_public_markers(app):
    before = datetime.now(timezone.utc)
    query = ("challenge=" + CHALLENGE + "&_=" + CHALLENGE).encode()
    status, headers, body = request(app, "/demo/status", query=query)
    first = json.loads(body)
    second = json.loads(request(app, "/demo/status", query=query)[2])
    after = datetime.now(timezone.utc)
    assert status == 200 and headers["content-type"] == "application/json"
    assert set(first) == {"status", "demo", "challenge", "server_time_utc", "run_id", "request_id"}
    assert first["status"] == "ok" and first["demo"] is True and first["challenge"] == CHALLENGE
    assert first["run_id"] == second["run_id"]
    assert first["request_id"] != second["request_id"]
    for marker in (first["run_id"], first["request_id"]):
        assert re.fullmatch("[a-f0-9]{32}", marker)
    assert before <= datetime.fromisoformat(first["server_time_utc"].replace("Z", "+00:00")) <= after
    assert first["server_time_utc"] != second["server_time_utc"]


@pytest.mark.parametrize("query", [
    b"", b"challenge=short", b"challenge=", b"challenge=" + b"a" * 129,
    b"challenge=" + CHALLENGE.encode() + b"&challenge=" + CHALLENGE.encode(),
    b"challenge=" + CHALLENGE.encode() + b"&private=1", b"challenge=" + b"%3Cscript%3E" * 3,
    b"challenge=" + CHALLENGE.encode() + b"&_=" , b"challenge=" + b"\xff" * 16,
    b"challenge=" + CHALLENGE.encode() + b"&", b"challenge=" + CHALLENGE.encode() + b"&_=" + CHALLENGE.encode() + b"&x=1",
])
def test_status_challenge_is_bounded_strict_and_not_arbitrary_input(app, query):
    assert request(app, "/demo/status", query=query)[0] == 400


@pytest.mark.parametrize("headers,body,more_body", [
    ([(b"host", HOST), (b"content-length", b"1")], b"x", False),
    ([(b"host", HOST), (b"content-length", b"0"), (b"content-length", b"0")], b"", False),
    ([(b"host", HOST), (b"transfer-encoding", b"chunked")], b"", False),
    ([(b"host", HOST)], b"x", False), ([(b"host", HOST)], b"", True),
])
def test_no_request_bodies_or_uploads(app, headers, body, more_body):
    assert request(app, headers=headers, body=body, more_body=more_body)[0] == 413


def test_bounded_headers_target_and_global_request_rate(app, monkeypatch):
    assert request(app, headers=[(b"host", HOST)] + [(b"x-a", b"a")] * 32)[0] == 431
    assert request(app, headers=[(b"host", HOST), (b"x-a", b"a" * 4096)])[0] == 431
    assert request(app, headers=[(b"host", HOST)] + [(b"x-a", b"a" * 1000)] * 9)[0] == 431
    assert request(app, query=b"a" * 513)[0] == 414
    monkeypatch.setattr(demo_web, "MAX_REQUESTS_PER_MINUTE", 2)
    monkeypatch.setattr(demo_web.time, "monotonic", lambda: 1000)
    app = demo_web.create_demo_app(enable_demo=True)
    assert request(app)[0] == request(app)[0] == 200
    status, headers, _ = request(app)
    assert status == 429 and headers["retry-after"] == "60"
    monkeypatch.setattr(demo_web.time, "monotonic", lambda: 1061)
    assert request(app)[0] == 200


def test_concurrency_and_slow_request_limits_release_the_slot(app, monkeypatch):
    async def run():
        entered = asyncio.Event()
        release = asyncio.Event()
        messages = []
        scope = {
            "type": "http", "scheme": "https", "method": "GET", "path": "/",
            "raw_path": b"/", "query_string": b"", "headers": [(b"host", HOST)],
        }

        async def receive():
            entered.set()
            await release.wait()
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        monkeypatch.setattr(demo_web, "MAX_CONCURRENT_REQUESTS", 1)
        first = asyncio.create_task(app(scope, receive, send))
        await entered.wait()
        rejected = []

        async def rejected_send(message):
            rejected.append(message)

        await app(scope, receive, rejected_send)
        assert rejected[0]["status"] == 503
        release.set()
        await first
        assert messages[0]["status"] == 200 and app._active == 0

        monkeypatch.setattr(demo_web, "REQUEST_BODY_TIMEOUT", .01)
        release.clear()
        messages.clear()
        await app(scope, receive, send)
        assert messages[0]["status"] == 408 and app._active == 0

    asyncio.run(run())


def test_websockets_are_closed_without_a_backend(app):
    async def run():
        messages = []

        async def receive():
            pytest.fail("Websocket request should never be read")

        async def send(message):
            messages.append(message)

        await app({"type": "websocket", "path": "/"}, receive, send)
        assert messages == [{"type": "websocket.close", "code": 1008}]

    asyncio.run(run())


def test_import_and_requests_cannot_import_backend_or_sqlite():
    code = r'''
import asyncio, importlib.abc, sys
blocked = {"manage", "servertec", "accounts", "account_ledger", "consumption_groups", "evaluations", "exercise_catalog", "offline_hearts", "sqlite3"}
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in blocked:
            raise AssertionError("Forbidden demo import: " + fullname)
sys.meta_path.insert(0, Guard())
import demo_web
app = demo_web.create_demo_app(enable_demo=True)
async def run():
    async def receive(): return {"type": "http.request", "body": b"", "more_body": False}
    async def send(message): pass
    for path in ("/", "/menu.css", "/menu.js", "/demo/status", "/v2/auth/me", "/state/servertec.db"):
        await app({"type":"http", "scheme":"https", "method":"GET", "path":path, "raw_path":path.encode(), "headers":[(b"host", b"learngraphicsprogramming.dynamics")], "query_string":b"challenge=0123456789abcdef"}, receive, send)
asyncio.run(run())
assert not blocked.intersection(sys.modules)
print(demo_web.RUN_ID)
'''
    repo = Path(__file__).resolve().parent
    first = subprocess.run([sys.executable, "-B", "-c", code], cwd=repo, capture_output=True, text=True, check=True)
    second = subprocess.run([sys.executable, "-B", "-c", code], cwd=repo, capture_output=True, text=True, check=True)
    assert re.fullmatch(r"[a-f0-9]{32}\s*", first.stdout)
    assert first.stdout != second.stdout


def test_cli_requires_explicit_opt_in_before_listener_or_file_read(monkeypatch):
    import uvicorn
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: pytest.fail("Must not start a listener"))
    with pytest.raises(SystemExit) as error:
        demo_web.main(["serve", "--cert", "missing.pem", "--key", "missing.key"])
    assert error.value.code == 2


def test_cli_only_starts_isolated_application_with_safe_defaults(tmp_path, monkeypatch):
    import uvicorn
    cert, key = tmp_path / "demo-chain.pem", tmp_path / "demo-leaf.key"
    cert.write_text("test placeholder")
    key.write_text("test placeholder")
    captured = {}

    def run(app, **kwargs):
        captured.update(kwargs)
        assert isinstance(app, demo_web.DemoWebApp)
        assert app.enabled is True
        assert app.hostname == demo_web.DEMO_HOST

    monkeypatch.setattr(uvicorn, "run", run)
    args = ["serve", "--enable-demo", "--cert", str(cert), "--key", str(key)]
    assert demo_web.main(args) == 0
    assert captured["host"] == "127.0.0.1" and captured["port"] == 443
    assert captured["proxy_headers"] is False and captured["forwarded_allow_ips"] == ""
    assert captured["ws"] == "none" and captured["server_header"] is False
    assert captured["access_log"] is False
    assert captured["ssl_certfile"] == str(cert.resolve())
    assert captured["ssl_keyfile"] == str(key.resolve())
    for extra in (["--host", "example.org"], ["--port", "0"], ["--port", "65536"]):
        with pytest.raises(SystemExit):
            demo_web.main(args + extra)


def test_cli_public_candidate_is_explicit_and_keeps_tls(tmp_path, monkeypatch):
    import uvicorn
    cert, key = tmp_path / "existing-demo-chain.pem", tmp_path / "existing-demo-leaf.key"
    cert.write_text("test placeholder")
    key.write_text("test placeholder")
    captured = {}

    def run(app, **kwargs):
        captured.update(kwargs)
        assert app.hostname == demo_web.PUBLIC_DEMO_HOST
        assert request(app, headers=[(b"host", demo_web.PUBLIC_DEMO_HOST.encode())])[0] == 200
        assert request(app)[0] == 400

    monkeypatch.setattr(uvicorn, "run", run)
    assert demo_web.main(["serve", "--enable-demo", "--hostname", demo_web.PUBLIC_DEMO_HOST,
                          "--cert", str(cert), "--key", str(key)]) == 0
    assert captured["ssl_certfile"] == str(cert.resolve())
    assert captured["ssl_keyfile"] == str(key.resolve())
    assert captured["ssl_version"] == demo_web.ssl.PROTOCOL_TLS_SERVER
    assert captured["host"] == "127.0.0.1"


def test_cli_unlisted_hostname_is_rejected_before_file_checks_or_listener(monkeypatch):
    import uvicorn
    monkeypatch.setattr(Path, "is_file", lambda *_: pytest.fail("Must not inspect identity files"))
    monkeypatch.setattr(uvicorn, "run", lambda *_, **__: pytest.fail("Must not start a listener"))
    with pytest.raises(SystemExit) as error:
        demo_web.main(["serve", "--enable-demo", "--hostname", "example.org",
                       "--cert", "missing.pem", "--key", "missing.key"])
    assert error.value.code == 2
