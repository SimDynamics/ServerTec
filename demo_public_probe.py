"""Observe the assigned dynv6 zone without configuring or publishing anything.

DNS, TCP443, system-trusted HTTPS and real Chrome acceptance are independent.
This process runs on the server PC: its requests never prove another-network
access, ownership of the candidate, or Android/Windows Chrome behavior.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import http.client
import ipaddress
import json
import os
import secrets
import socket
import ssl
import subprocess

PUBLIC_HOST = "servertec-demo.example.invalid"
MAX_PUBLIC_ADDRESSES = 4
TCP_TIMEOUT = 3.0
DNS_MODE = "windows_Resolve-DnsName_DnsOnly_NoHostsFile"

# The only target is a constant, not interpolated shell input. No host file,
# alternate resolver, account, authentication, or dynv6 update API is involved.
DNS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$target = 'servertec-demo.example.invalid'
$answers = @()
foreach ($kind in @('A', 'AAAA')) {
    try {
        $records = @(Resolve-DnsName -Name $target -Type $kind -DnsOnly -NoHostsFile -ErrorAction Stop)
        $addresses = @($records | Where-Object {
            $_.PSObject.Properties.Name -contains 'IPAddress'
        } | ForEach-Object { [string]$_.IPAddress })
        $answers += [pscustomobject]@{ query_type=$kind; status='answered'; addresses=$addresses }
    } catch {
        $errorCode = ([string]$_.FullyQualifiedErrorId).Split(',')[0]
        $resultStatus = 'error'
        if ($errorCode -eq 'DNS_ERROR_RCODE_NAME_ERROR') { $resultStatus = 'nxdomain' }
        if ($errorCode -eq 'DNS_INFO_NO_RECORDS') { $resultStatus = 'no_records' }
        $answers += [pscustomobject]@{ query_type=$kind; status=$resultStatus; addresses=@(); error_code=$errorCode }
    }
}
[pscustomobject]@{ hostname=$target; answers=$answers } | ConvertTo-Json -Depth 5 -Compress
"""


def _global_address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    # is_global alone includes multicast in some Python versions. Never contact
    # private, local, unspecified, multicast, scoped or mapped candidate addresses.
    if (not address.is_global or address.is_multicast or address.is_unspecified
            or address.is_reserved or address.is_loopback or address.is_link_local
            or "%" in value or getattr(address, "ipv4_mapped", None) is not None):
        return None
    return address


def _normalize_dns(payload: dict) -> dict:
    if not isinstance(payload, dict) or payload.get("hostname") != PUBLIC_HOST:
        raise ValueError("Respuesta DNS inesperada")
    answers = payload.get("answers")
    if not isinstance(answers, list) or len(answers) != 2:
        raise ValueError("Faltan resultados DNS A/AAAA independientes")
    records = []
    public_addresses = []
    rejected = []
    seen_types = set()
    seen_addresses = set()
    for answer in answers:
        if not isinstance(answer, dict):
            raise ValueError("Resultado DNS no valido")
        kind = answer.get("query_type")
        status = answer.get("status")
        if kind not in ("A", "AAAA") or kind in seen_types:
            raise ValueError("Tipo DNS inesperado o repetido")
        if status not in ("answered", "nxdomain", "no_records", "error"):
            raise ValueError("Estado DNS inesperado")
        seen_types.add(kind)
        addresses = answer.get("addresses", [])
        if not isinstance(addresses, list) or len(addresses) > 64:
            raise ValueError("Lista DNS no valida o demasiado grande")
        if status != "answered" and addresses:
            raise ValueError("DNS fallido contiene direcciones")
        record = {"query_type": kind, "status": status, "addresses": []}
        for value in addresses:
            if not isinstance(value, str) or len(value) > 128:
                raise ValueError("Direccion DNS no valida")
            address = _global_address(value)
            if address is None or address.version != (4 if kind == "A" else 6):
                rejected.append({"query_type": kind, "address": value,
                                 "reason": "not_public_global_for_record_type"})
                continue
            canonical = str(address)
            record["addresses"].append(canonical)
            if canonical not in seen_addresses:
                seen_addresses.add(canonical)
                public_addresses.append(canonical)
        if status == "error":
            # Error identifiers come from a local resolver; no exception text or
            # arbitrary resolver response is printed as a command or credential.
            code = answer.get("error_code", "dns_lookup_error")
            record["error_code"] = str(code)[:160]
        records.append(record)
    statuses = {record["status"] for record in records}
    if public_addresses:
        state = "resolved_public_addresses"
    elif statuses == {"nxdomain"}:
        state = "nxdomain"
    elif "error" in statuses:
        state = "lookup_error"
    else:
        state = "no_public_addresses"
    return {
        "status": state,
        "mode": DNS_MODE,
        "records": records,
        "public_addresses": public_addresses[:MAX_PUBLIC_ADDRESSES],
        "address_limit": MAX_PUBLIC_ADDRESSES,
        "unprobed_public_address_count": max(0, len(public_addresses) - MAX_PUBLIC_ADDRESSES),
        "rejected_addresses": rejected,
        "assignment_or_availability_verified": False,
        "note": "NXDOMAIN no demuestra disponibilidad; una respuesta DNS no demuestra asignacion o propiedad.",
    }


def resolve_public_dns() -> dict:
    base = {"mode": DNS_MODE, "public_addresses": [],
            "assignment_or_availability_verified": False}
    if os.name != "nt":
        return {**base, "status": "unsupported_platform",
                "reason": "Se requiere el resolvedor normal de Windows con -DnsOnly -NoHostsFile."}
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", DNS_SCRIPT],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=35, shell=False,
        )
        if result.returncode != 0 or len(result.stdout) > 65536:
            return {**base, "status": "lookup_error", "reason": "dns_process_failed"}
        return _normalize_dns(json.loads(result.stdout.lstrip("\ufeff")))
    except subprocess.TimeoutExpired:
        return {**base, "status": "lookup_error", "reason": "dns_process_timeout"}
    except (OSError, ValueError, TypeError):
        return {**base, "status": "lookup_error", "reason": "dns_process_or_output_invalid"}


def tcp_probe(address: str) -> dict:
    if _global_address(address) is None:
        raise ValueError("Solo se prueban direcciones publicas globales")
    try:
        with socket.create_connection((address, 443), timeout=TCP_TIMEOUT):
            pass
        return {"address": address, "status": "connected", "port": 443}
    except OSError as error:
        return {"address": address, "status": "failed", "port": 443,
                "error_type": type(error).__name__, "errno": error.errno}


def _fresh_status(body: bytes, challenge: str, now: datetime) -> dict:
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("Estado JSON no valido")
    if (payload.get("status") != "ok" or payload.get("demo") is not True
            or payload.get("challenge") != challenge):
        raise ValueError("Estado o desafio no valido")
    for field in ("run_id", "request_id"):
        value = payload.get(field)
        if (not isinstance(value, str) or not 1 <= len(value) <= 128
                or any(not (char.isascii() and (char.isalnum() or char in "_-")) for char in value)):
            raise ValueError("Identificador de respuesta no valido")
    timestamp = payload.get("server_time_utc")
    if not isinstance(timestamp, str):
        raise ValueError("Hora de servidor ausente")
    moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if moment.utcoffset() is None or abs((now - moment).total_seconds()) > 120:
        raise ValueError("Hora de servidor fuera de ventana")
    return {field: payload[field] for field in ("run_id", "request_id", "server_time_utc")}



def https_get_system(address: str, port: int, path: str) -> tuple[int, dict[str, str], bytes]:
    """Request only the public demo over system-trusted TLS, never our private CA.

    This is a Python/OS store probe. It does NOT prove Chrome trusts the chain.
    No browser trust changes, proxies, client certificates or TLS bypasses.
    """
    if _global_address(address) is None or port != 443:
        raise ValueError("Solo IP global y TCP 443 para la demo")
    if (not path.startswith("/") or len(path) > 512
            or any(ord(char) < 33 or ord(char) > 126 for char in path)):
        raise ValueError("Ruta HTTP no valida")
    # Explicit context avoids SSLKEYLOGFILE exporting TLS session secrets.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_default_certs(ssl.Purpose.SERVER_AUTH)
    if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
        raise ValueError("No esta habilitada la verificacion del certificado")
    with socket.create_connection((address, port), timeout=TCP_TIMEOUT) as plain:
        with context.wrap_socket(plain, server_hostname=PUBLIC_HOST) as tls:
            tls.settimeout(TCP_TIMEOUT)
            tls.sendall(
                (f"GET {path} HTTP/1.1\r\nHost: {PUBLIC_HOST}\r\n"
                 "Connection: close\r\nCache-Control: no-cache\r\n\r\n").encode("ascii")
            )
            with http.client.HTTPResponse(tls) as response:
                response.begin()
                body = response.read(131073)
                if len(body) > 131072:
                    raise ValueError("Respuesta HTTPS demasiado grande")
                return response.status, {key.lower(): val for key, val in response.getheaders()}, body


def https_probe(address: str) -> dict:
    if _global_address(address) is None:
        raise ValueError("Solo se prueban direcciones publicas globales")
    result = {"address": address, "trust": "system_certificate_store",
              "hostname": PUBLIC_HOST, "hostname_validation": True}
    try:
        status, headers, body = https_get_system(address, 443, "/")
        if (status != 200 or "text/html" not in headers.get("content-type", "")
                or b"<title>LearnGraphicsProgramming</title>" not in body
                or "no-store" not in headers.get("cache-control", "").split(", ")):
            raise ValueError("Menu HTTPS no valido")
        responses = []
        for _ in range(2):
            challenge = secrets.token_hex(24)
            status, headers, body = https_get_system(
                address, 443, "/demo/status?challenge=" + challenge)
            if (status != 200 or "application/json" not in headers.get("content-type", "")
                    or "no-store" not in headers.get("cache-control", "").split(", ")):
                raise ValueError("Respuesta JSON HTTPS no valida")
            responses.append(_fresh_status(body, challenge, datetime.now(timezone.utc)))
        if (responses[0]["run_id"] != responses[1]["run_id"]
                or responses[0]["request_id"] == responses[1]["request_id"]):
            raise ValueError("Respuestas no acreditan misma ejecucion y solicitudes distintas")
        return {**result, "status": "python_validated_menu_and_fresh_status",
                "run_id": responses[-1]["run_id"],
                "server_time_utc": responses[-1]["server_time_utc"],
                "request_ids": [entry["request_id"] for entry in responses],
                "local_run_identity_compared": False}
    except ssl.SSLCertVerificationError as error:
        return {**result, "status": "certificate_verification_failed",
                "verify_code": getattr(error, "verify_code", None),
                "verify_message": getattr(error, "verify_message", "certificate verification failed")}
    except ssl.SSLError as error:
        return {**result, "status": "tls_failed", "error_type": type(error).__name__}
    except OSError as error:
        return {**result, "status": "connection_failed", "error_type": type(error).__name__,
                "errno": error.errno}
    except (ValueError, TypeError, KeyError, OverflowError):
        return {**result, "status": "menu_or_fresh_status_invalid"}


def probe_public() -> dict:
    dns = resolve_public_dns()
    # Validate again at the network boundary: even a future resolver change may
    # never redirect this observer into a private/local network or many hosts.
    addresses = []
    for address in dns.get("public_addresses", []):
        if isinstance(address, str) and _global_address(address) is not None:
            canonical = str(ipaddress.ip_address(address))
            if canonical not in addresses:
                addresses.append(canonical)
    addresses = addresses[:MAX_PUBLIC_ADDRESSES]
    tcp_results = []
    https_results = []
    for address in addresses:
        tcp = tcp_probe(address)
        tcp_results.append(tcp)
        if tcp["status"] == "connected":
            https_results.append(https_probe(address))
        else:
            https_results.append({"address": address, "status": "not_run_tcp_failed"})
    connected = sum(result["status"] == "connected" for result in tcp_results)
    validated = sum(result["status"] == "python_validated_menu_and_fresh_status"
                    for result in https_results)
    tcp_status = ("not_run_no_public_addresses" if not addresses else
                  "all_connected" if connected == len(addresses) else
                  "some_connected" if connected else "all_failed")
    https_status = ("not_run_no_tcp_connection" if not connected else
                    "all_probed_addresses_validated_by_python" if validated == len(addresses) else
                    "some_probed_addresses_validated_by_python" if validated else "failed")
    return {
        "schema_version": 1,
        "observed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "mode": "observational_no_configuration_changes",
        "hostname": PUBLIC_HOST,
        "url": "https://" + PUBLIC_HOST + "/",
        "dns": dns,
        "tcp443": {"status": tcp_status, "results": tcp_results, "timeout_seconds": TCP_TIMEOUT},
        "https": {"status": https_status, "results": https_results,
                  "trust": "system_certificate_store", "hostname_validation": True},
        "chrome": {"status": "pending_manual_windows_and_android_from_another_network",
                   "verified": False, "visitor_protection_changes": False},
        "external_network_verified": False,
        "ownership_or_assignment_verified": False,
        "public_access_complete": False,
        "limits": ["Se ejecuta desde esta PC; no prueba entrada desde otra red ni Chrome.",
                   "DNS no demuestra disponibilidad, asignacion o propiedad del candidato.",
                   "No configura DNS, cuentas, certificados, confianza, router, firewall ni listeners."],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(probe_public(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
