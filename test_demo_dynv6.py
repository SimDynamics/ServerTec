"""Pruebas aisladas de nombre publico y PKI privada de demostracion."""
from pathlib import Path
from cryptography import x509
import pytest
import demo_pki
import demo_web
import demo_check

def test_name_consistency():
    assert demo_pki.PUBLIC_HOSTNAME == demo_web.PUBLIC_DEMO_HOST
    assert demo_pki.PUBLIC_HOSTNAME == demo_check.PUBLIC_DEMO_NAME

def test_new_public_identity_does_not_overwrite_private_identity(tmp_path):
    directory = tmp_path / "new-public"
    meta = demo_pki.prepare_demo(directory, None, hostname=demo_pki.PUBLIC_HOSTNAME)
    assert meta["leaf_dns_san"] == [demo_pki.PUBLIC_HOSTNAME]
    leaf = x509.load_pem_x509_certificates((directory / "runtime" / "server.pem").read_bytes())[0]
    san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert list(san) == [x509.DNSName(demo_pki.PUBLIC_HOSTNAME)]
    assert demo_pki.inspect_demo(directory, hostname=demo_pki.PUBLIC_HOSTNAME) == meta
    with pytest.raises(ValueError):
        demo_pki.inspect_demo(directory, hostname=demo_pki.HOSTNAME)
    with pytest.raises(FileExistsError):
        demo_pki.prepare_demo(directory, None, hostname=demo_pki.PUBLIC_HOSTNAME)

def test_reject_unlisted_name_without_writing(tmp_path):
    directory = tmp_path / "not-created"
    with pytest.raises(ValueError):
        demo_pki.prepare_demo(directory, None, hostname="example.org")
    assert not directory.exists()

def test_menu_is_bound_to_selected_name_only():
    app = demo_web.create_demo_app(enable_demo=True, hostname=demo_web.PUBLIC_DEMO_HOST)
    assert app.hostname == demo_pki.PUBLIC_HOSTNAME

def test_no_unapproved_host_for_verification(tmp_path):
    with pytest.raises(ValueError):
        demo_check.verify_demo(tmp_path, "127.0.0.1", hostname="other.example")
