"""Explicitly validated HTTPS to a literal address, with the demo DNS name as SNI.

This checks transport independently of client DNS/hosts and Chrome trust. It never
changes either, starts a server, opens SQLite, or trusts system proxy settings.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import http.client
import ipaddress
import json
from pathlib import Path
import secrets
import socket
import ssl


DEMO_NAME = 'learngraphicsprogramming.dynamics'


def tls_context(ca_file: Path) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_verify_locations(cafile=str(ca_file))
    context.verify_flags |= ssl.VERIFY_X509_STRICT
    # No create_default_context: SSLKEYLOGFILE must not export TLS session keys.
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    return context


def https_get(address: str, port: int, path: str, ca_file: Path, *,
              server_name: str = DEMO_NAME) -> tuple[int, dict[str, str], bytes]:
    ipaddress.ip_address(address)
    if not 1 <= port <= 65535:
        raise ValueError('Puerto fuera de rango')
    if not path.startswith('/') or any(ord(char) < 33 or ord(char) > 126 for char in path):
        raise ValueError('Ruta HTTP no valida')
    if server_name not in (DEMO_NAME, 'wrong-name.invalid'):
        raise ValueError('Nombre de prueba no valido')
    context = tls_context(ca_file)
    with socket.create_connection((address, port), timeout=5) as connection:
        with context.wrap_socket(connection, server_hostname=server_name) as stream:
            stream.sendall((f'GET {path} HTTP/1.1\r\nHost: {DEMO_NAME}'
                            '\r\nConnection: close\r\nCache-Control: no-cache\r\n\r\n').encode('ascii'))
            with http.client.HTTPResponse(stream) as response:
                response.begin()
                body = response.read(131073)
                if len(body) > 131072:
                    raise ValueError('Respuesta demasiado grande')
                return response.status, {k.lower(): v for k, v in response.getheaders()}, body


def verify_demo(directory: Path, address: str, port: int = 443) -> dict:
    ca_file = directory / 'public' / 'authority.pem'
    checks = []
    for path, content_type in [('/', 'text/html'), ('/menu.css', 'text/css'),
                               ('/menu.js', 'javascript')]:
        status, headers, body = https_get(address, port, path, ca_file)
        if status != 200 or content_type not in headers.get('content-type', '') or not body:
            raise ValueError('Menu o recurso local no disponible')
        if 'no-store' not in headers.get('cache-control', '').split(', '):
            raise ValueError('Falta no-store')
    checks.append('menu_y_recursos_locales_https')
    responses = []
    for _ in range(2):
        challenge = secrets.token_hex(24)
        status, headers, body = https_get(address, port, '/demo/status?challenge=' + challenge, ca_file)
        payload = json.loads(body)
        if status != 200 or payload.get('status') != 'ok' or payload.get('demo') is not True:
            raise ValueError('Estado demo no valido')
        if payload.get('challenge') != challenge or 'no-store' not in headers.get('cache-control', '').split(', '):
            raise ValueError('Respuesta de conexion no actual')
        moment = datetime.fromisoformat(payload['server_time_utc'].replace('Z', '+00:00'))
        if abs((datetime.now(timezone.utc) - moment).total_seconds()) > 120:
            raise ValueError('Hora del servidor fuera de la ventana de prueba')
        if not payload.get('run_id') or not payload.get('request_id'):
            raise ValueError('Faltan identificadores de prueba')
        responses.append(payload)
    if (responses[0]['run_id'] != responses[1]['run_id'] or
            responses[0]['request_id'] == responses[1]['request_id']):
        raise ValueError('Identificadores de conexion no validos')
    checks.append('dos_respuestas_frescas_misma_ejecucion')
    for path in ('/state/servertec.db', '/server-key.pem', '/authority/authority-key.pem',
                 '/README.md', '/rules-catalog.json', '/docs', '/openapi.json',
                 '/v2/auth/me', '/v2/evaluations', '/v1/progress',
                 '/%2e%2e/manage.py', '/demo_web_assets/../manage.py'):
        status, _, _ = https_get(address, port, path, ca_file)
        if status != 404:
            raise ValueError('Una ruta ajena a la demo esta accesible')
    checks.append('rutas_privadas_y_de_negocio_inaccesibles')
    try:
        https_get(address, port, '/', ca_file, server_name='wrong-name.invalid')
    except ssl.SSLCertVerificationError:
        checks.append('nombre_tls_incorrecto_rechazado')
    else:
        raise ValueError('Se acepto un nombre TLS incorrecto')
    return {'checks': checks, 'run_id': responses[-1]['run_id'],
            'server_time_utc': responses[-1]['server_time_utc'],
            'transport': 'TLS con CA explicita y nombre exacto',
            'dns_or_chrome_verified': False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path(r'D:\Projects\ServerTec\demo-web-20261019'))
    parser.add_argument('--address', default='127.0.0.1', help='IP literal, sin cambiar DNS/hosts')
    parser.add_argument('--port', type=int, default=443)
    args = parser.parse_args()
    print(json.dumps(verify_demo(args.directory.resolve(), args.address, args.port),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
