"""Opt-in HTTPS menu demo, isolated from ServerTec business data and imports."""

from __future__ import annotations

import argparse
import asyncio
from collections import deque
from datetime import datetime, timezone
import ipaddress
from pathlib import Path
import re
import secrets
import ssl
import time
from urllib.parse import parse_qs

from starlette.responses import JSONResponse, Response


DEMO_HOST = "learngraphicsprogramming.dynamics"
PUBLIC_DEMO_HOST = "servertec-demo.example.invalid"
ALLOWED_DEMO_HOSTS = (DEMO_HOST, PUBLIC_DEMO_HOST)
MAX_HEADERS = 32
MAX_HEADER_BYTES = 8192
MAX_HEADER_FIELD_BYTES = 4096
MAX_QUERY_BYTES = 512
MAX_CONCURRENT_REQUESTS = 16
MAX_REQUESTS_PER_MINUTE = 240
REQUEST_BODY_TIMEOUT = 2.0
RUN_ID = secrets.token_hex(16)  # Public run marker; never an authentication token.
_CHALLENGE_PATTERN = re.compile(r"[A-Za-z0-9_-]{16,128}")
_ASSET_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/menu.css": ("menu.css", "text/css; charset=utf-8"),
    "/menu.js": ("menu.js", "text/javascript; charset=utf-8"),
}
_SECURITY_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; img-src data:; font-src 'none'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'none'; worker-src 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Resource-Policy": "same-origin",
}


class DemoWebApp:
    """A literal four-path ASGI allowlist, with no directory serving or backend."""

    def __init__(self, *, enable_demo: bool = False, hostname: str = DEMO_HOST):
        if hostname not in ALLOWED_DEMO_HOSTS:
            raise ValueError("El nombre de la demo debe ser uno de los nombres exactos permitidos")
        self.hostname = hostname
        self._host_pattern = re.compile(re.escape(hostname.encode("ascii")) + rb"(?::([1-9][0-9]{0,4}))?")
        self.enabled = enable_demo is True
        self._active = 0
        self._requests: deque[float] = deque()
        self._assets: dict[str, tuple[bytes, str]] = {}
        if self.enabled:
            asset_dir = Path(__file__).resolve().parent / "demo_web_assets"
            for route, (filename, media_type) in _ASSET_FILES.items():
                self._assets[route] = ((asset_dir / filename).read_bytes(), media_type)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http":
            return

        async def reply(status, code=None, *, payload=None, body=None, media_type=None, extra=None):
            headers = dict(_SECURITY_HEADERS)
            if extra:
                headers.update(extra)
            if payload is not None:
                response = JSONResponse(payload, status_code=status, headers=headers)
            elif body is not None:
                headers["Content-Type"] = media_type
                response = Response(body, status_code=status, headers=headers)
            else:
                response = JSONResponse({"error": code}, status_code=status, headers=headers)
            if scope.get("method") == "HEAD":
                response.body = b""  # Keep the GET representation's Content-Length.
            await response(scope, receive, send)

        if not self.enabled:
            await reply(404, "not_found")
            return
        headers = scope.get("headers", [])
        if (
            len(headers) > MAX_HEADERS
            or sum(len(name) + len(value) + 4 for name, value in headers) > MAX_HEADER_BYTES
            or any(len(name) + len(value) > MAX_HEADER_FIELD_BYTES for name, value in headers)
        ):
            await reply(431, "headers_too_large", extra={"Connection": "close"})
            return
        hosts = [value for name, value in headers if name.lower() == b"host"]
        host_match = self._host_pattern.fullmatch(hosts[0]) if len(hosts) == 1 else None
        if not host_match or (host_match[1] and int(host_match[1]) > 65535):
            await reply(400, "invalid_host", extra={"Connection": "close"})
            return
        if any(name.lower() == b"forwarded" or name.lower().startswith(b"x-forwarded-") for name, _ in headers):
            await reply(400, "forwarded_headers_not_supported", extra={"Connection": "close"})
            return
        if scope.get("scheme") != "https":
            await reply(400, "https_required", extra={"Connection": "close"})
            return

        now = time.monotonic()
        while self._requests and self._requests[0] <= now - 60:
            self._requests.popleft()
        if len(self._requests) >= MAX_REQUESTS_PER_MINUTE:
            await reply(429, "request_limit", extra={"Retry-After": "60", "Connection": "close"})
            return
        self._requests.append(now)
        if self._active >= MAX_CONCURRENT_REQUESTS:
            await reply(503, "busy", extra={"Retry-After": "2", "Connection": "close"})
            return

        path = scope.get("path", "")
        raw_path = scope.get("raw_path", b"")
        allowed_methods = ("GET",) if path == "/demo/status" else ("GET", "HEAD")
        # Requiring the literal raw path also rejects encoded slashes/dots and traversal.
        if path not in {*_ASSET_FILES, "/demo/status"} or raw_path != path.encode("ascii"):
            await reply(404, "not_found")
            return
        if scope.get("method") not in allowed_methods:
            await reply(405, "method_not_allowed", extra={"Allow": ", ".join(allowed_methods)})
            return
        query = scope.get("query_string", b"")
        if len(query) > MAX_QUERY_BYTES:
            await reply(414, "query_too_long", extra={"Connection": "close"})
            return
        lengths = [value for name, value in headers if name.lower() == b"content-length"]
        if len(lengths) > 1 or (lengths and lengths[0] != b"0") or any(name.lower() == b"transfer-encoding" for name, _ in headers):
            await reply(413, "body_not_allowed", extra={"Connection": "close"})
            return
        self._active += 1
        try:
            try:
                event = await asyncio.wait_for(receive(), timeout=REQUEST_BODY_TIMEOUT)
            except TimeoutError:
                await reply(408, "request_timeout", extra={"Connection": "close"})
                return
            if event["type"] == "http.disconnect":
                return
            if event.get("body") or event.get("more_body"):
                await reply(413, "body_not_allowed", extra={"Connection": "close"})
                return
            if path != "/demo/status":
                body, content_type = self._assets[path]
                await reply(200, body=body, media_type=content_type)
                return
            try:
                params = parse_qs(query.decode("ascii"), keep_blank_values=True, strict_parsing=True, max_num_fields=2)
            except (UnicodeDecodeError, ValueError):
                await reply(400, "invalid_challenge")
                return
            challenge_values = params.get("challenge", [])
            if (
                set(params) - {"challenge", "_"}
                or len(challenge_values) != 1
                or not _CHALLENGE_PATTERN.fullmatch(challenge_values[0])
                or ("_" in params and (len(params["_"]) != 1 or not _CHALLENGE_PATTERN.fullmatch(params["_"][0])))
            ):
                await reply(400, "invalid_challenge")
                return
            await reply(200, payload={
                "status": "ok",
                "demo": True,
                "challenge": challenge_values[0],
                "server_time_utc": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
                "run_id": RUN_ID,
                "request_id": secrets.token_hex(16),
            })
        finally:
            self._active -= 1


def create_demo_app(*, enable_demo: bool = False, hostname: str = DEMO_HOST) -> DemoWebApp:
    """Disabled unless explicitly opted in; never reads ServerTec state."""
    return DemoWebApp(enable_demo=enable_demo, hostname=hostname)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Menú HTTPS aislado y opcional de LearnGraphicsProgramming.")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Iniciar únicamente el listener de demostración.")
    serve.add_argument("--enable-demo", action="store_true", help="Consentimiento explícito para activar esta demo.")
    serve.add_argument("--cert", required=True, type=Path, help="Cadena PEM del certificado de servidor de la demo.")
    serve.add_argument("--key", required=True, type=Path, help="Clave PEM de ejecución del servidor de la demo (nunca la CA).")
    serve.add_argument("--host", default="127.0.0.1", help="IP literal local a la que enlazar; por defecto 127.0.0.1.")
    serve.add_argument("--hostname", default=DEMO_HOST, choices=ALLOWED_DEMO_HOSTS,
                       help="Unico nombre Host permitido; no asigna DNS ni modifica certificados.")
    serve.add_argument("--port", default=443, type=int)
    args = parser.parse_args(argv)
    if not args.enable_demo:
        parser.error("La demo está desactivada: añade --enable-demo para iniciarla.")
    try:
        ipaddress.ip_address(args.host)
    except ValueError:
        parser.error("--host debe ser una dirección IP literal local.")
    if not 1 <= args.port <= 65535:
        parser.error("--port debe estar entre 1 y 65535.")
    if not args.cert.is_file() or not args.key.is_file():
        parser.error("--cert y --key deben existir; usa solamente material separado de la demo.")
    import uvicorn

    uvicorn.run(
        create_demo_app(enable_demo=True, hostname=args.hostname),
        host=args.host,
        port=args.port,
        ssl_certfile=str(args.cert.resolve()),
        ssl_keyfile=str(args.key.resolve()),
        ssl_version=ssl.PROTOCOL_TLS_SERVER,
        ssl_ciphers="ECDHE+AESGCM:ECDHE+CHACHA20",
        proxy_headers=False,
        forwarded_allow_ips="",
        access_log=False,
        server_header=False,
        interface="asgi3",
        ws="none",
        lifespan="on",
        limit_concurrency=MAX_CONCURRENT_REQUESTS,
        h11_max_incomplete_event_size=MAX_HEADER_BYTES,
        timeout_keep_alive=5,
        timeout_graceful_shutdown=5,
        backlog=64,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
