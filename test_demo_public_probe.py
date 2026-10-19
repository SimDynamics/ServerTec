"""Pruebas aisladas del observador publico dynv6. Sin red ni claves."""
from datetime import datetime, timezone
import json
import ssl

import pytest

import demo_public_probe as public


def test_target_is_the_assigned_name():
    assert public.PUBLIC_HOST == "servertec-demo.example.invalid"
    assert public.PUBLIC_HOST in public.DNS_SCRIPT
    assert "ydns.eu" not in public.DNS_SCRIPT


def test_only_public_global_addresses_can_be_probed():
    for value in ("127.0.0.1", "::1", "198.51.100.10", "fe80::1", "10.0.0.1",
                  "0.0.0.0", "255.255.255.255", "2001:db8::1"):
        assert public._global_address(value) is None
    assert public._global_address("1.1.1.1") is not None
    assert public._global_address("2606:4700:4700::1111") is not None


def test_dns_normalization_observes_both_families_without_ownership_claim():
    result = public._normalize_dns({
        "hostname": public.PUBLIC_HOST,
        "answers": [
            {"query_type": "A", "status": "answered", "addresses": ["1.1.1.1"]},
            {"query_type": "AAAA", "status": "answered",
             "addresses": ["2606:4700:4700::1111"]},
        ],
    })
    assert result["status"] == "resolved_public_addresses"
    assert len(result["public_addresses"]) == 2
    assert result["assignment_or_availability_verified"] is False


def test_dns_rejects_mismatched_hostname():
    with pytest.raises(ValueError):
        public._normalize_dns({"hostname": "unrelated.example", "answers": []})


def test_certificate_failure_never_claims_chrome_success(monkeypatch):
    def fail(*_args):
        raise ssl.SSLCertVerificationError("untrusted")
    monkeypatch.setattr(public, "https_get_system", fail)
    result = public.https_probe("1.1.1.1")
    assert result["status"] == "certificate_verification_failed"
    assert result["hostname"] == public.PUBLIC_HOST


def test_fresh_menu_probe_uses_exact_host_without_ca_override(monkeypatch):
    seen = []
    def request(address, port, path):
        assert address == "1.1.1.1" and port == 443
        seen.append(path)
        headers = {"cache-control": "no-store", "content-type": "text/html"}
        if path == "/":
            return 200, headers, b"<title>LearnGraphicsProgramming</title>"
        challenge = path.split("challenge=", 1)[1]
        data = {
            "status": "ok", "demo": True, "challenge": challenge,
            "run_id": "testrun", "request_id": f"req_{len(seen)}",
            "server_time_utc": datetime.now(timezone.utc).isoformat(),
        }
        return 200, {"cache-control": "no-store", "content-type": "application/json"}, json.dumps(data).encode()
    monkeypatch.setattr(public, "https_get_system", request)
    result = public.https_probe("1.1.1.1")
    assert result["status"] == "python_validated_menu_and_fresh_status"
    assert len(seen) == 3


def test_report_never_asserts_remote_access_or_chrome(monkeypatch):
    monkeypatch.setattr(public, "resolve_public_dns", lambda: {
        "status": "no_public_addresses", "public_addresses": [],
    })
    report = public.probe_public()
    assert report["hostname"] == public.PUBLIC_HOST
    assert report["external_network_verified"] is False
    assert report["chrome"]["verified"] is False
    assert report["public_access_complete"] is False
