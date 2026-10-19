"""Demo identity tests use only pytest temporary directories and loopback sockets."""
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import socket
import ssl
import subprocess
import threading

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
import pytest

import demo_pki


PASSWORD = b"test-only isolated CA passphrase"


@pytest.fixture
def prepared(tmp_path):
    target = tmp_path / "new-demo"
    metadata = demo_pki.prepare_demo(target, PASSWORD)
    return target, metadata


def test_fresh_material_separates_encrypted_authority_from_runtime(prepared):
    directory, metadata = prepared
    authority_bytes = (directory / "authority" / "authority-key.pem").read_bytes()
    assert b"BEGIN ENCRYPTED PRIVATE KEY" in authority_bytes
    with pytest.raises(ValueError):
        serialization.load_pem_private_key(authority_bytes, b"incorrect password")
    authority_key = serialization.load_pem_private_key(authority_bytes, PASSWORD)
    authority = x509.load_pem_x509_certificate((directory / "public" / "authority.pem").read_bytes())
    assert authority_key.public_key().public_numbers() == authority.public_key().public_numbers()
    assert {path.name for path in (directory / "runtime").iterdir()} == {"server.pem", "server-key.pem"}
    assert {path.name for path in (directory / "public").iterdir()} == {"authority.pem", "authority.cer", "issuer.pem", "metadata.json"}
    assert metadata["authority_key_retained"] is True
    assert metadata["issuer_key_retained"] is False
    assert metadata["schema_version"] == 2
    chain = x509.load_pem_x509_certificates((directory / "runtime" / "server.pem").read_bytes())
    issuer = x509.load_pem_x509_certificate((directory / "public" / "issuer.pem").read_bytes())
    assert len(chain) == 2 and chain[1] == issuer
    assert authority.extensions.get_extension_for_class(x509.BasicConstraints).value.path_length == 1
    assert issuer.extensions.get_extension_for_class(x509.BasicConstraints).value.path_length == 0
    assert [p.relative_to(directory).as_posix() for p in directory.rglob("*key*")] == [
        "authority/authority-key.pem", "runtime/server-key.pem"]


def test_one_shot_retains_no_authority_private_key(tmp_path):
    directory = tmp_path / "one-shot"
    metadata = demo_pki.prepare_demo(directory, None)
    assert list((directory / "authority").iterdir()) == []
    assert metadata["authority_key_retained"] is False
    assert metadata["issuer_key_retained"] is False
    assert [p.relative_to(directory).as_posix() for p in directory.rglob("*key*")] == ["runtime/server-key.pem"]
    assert demo_pki.inspect_demo(directory) == metadata


def test_fingerprints_distinguish_der_certificate_from_pem_file(prepared):
    directory, metadata = prepared
    der = (directory / "public" / "authority.cer").read_bytes()
    pem = (directory / "public" / "authority.pem").read_bytes()
    assert metadata["authority_certificate_sha256"] == hashlib.sha256(der).hexdigest()
    assert metadata["authority_pem_file_sha256"] == hashlib.sha256(pem).hexdigest()
    assert metadata["authority_certificate_sha256"] != metadata["authority_pem_file_sha256"]
    issuer_pem = (directory / "public" / "issuer.pem").read_bytes()
    issuer = x509.load_pem_x509_certificate(issuer_pem)
    chain_pem = (directory / "runtime" / "server.pem").read_bytes()
    leaf = x509.load_pem_x509_certificates(chain_pem)[0]
    leaf_pem = leaf.public_bytes(serialization.Encoding.PEM)
    assert metadata["issuer_certificate_sha256"] == issuer.fingerprint(hashes.SHA256()).hex()
    assert metadata["issuer_pem_file_sha256"] == hashlib.sha256(issuer_pem).hexdigest()
    assert metadata["leaf_certificate_sha256"] == leaf.fingerprint(hashes.SHA256()).hex()
    assert metadata["leaf_pem_file_sha256"] == hashlib.sha256(leaf_pem).hexdigest()
    assert metadata["server_chain_pem_file_sha256"] == hashlib.sha256(chain_pem).hexdigest()
    assert metadata["server_chain_pem_file_sha256"] != metadata["leaf_pem_file_sha256"]
    assert metadata["leaf_dns_san"] == [demo_pki.HOSTNAME]
    assert metadata["authority_dns_excluded_subtrees"] == ["." + demo_pki.HOSTNAME]
    assert metadata["authority_ip_excluded_subtrees"] == ["0.0.0.0/0", "::/0"]


def test_inspect_never_reads_private_keys(prepared, monkeypatch):
    directory, expected = prepared
    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text

    def read_bytes(path):
        assert "key" not in path.name
        return original_read_bytes(path)

    def read_text(path, *args, **kwargs):
        assert "key" not in path.name
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    monkeypatch.setattr(Path, "read_text", read_text)
    assert demo_pki.inspect_demo(directory) == expected


@pytest.mark.parametrize("kind", ["empty", "data", "file"])
def test_existing_target_is_never_reused_or_changed(tmp_path, kind):
    target = tmp_path / "existing"
    if kind == "file":
        target.write_bytes(b"keep this")
    else:
        target.mkdir()
        if kind == "data":
            (target / "unrelated.txt").write_bytes(b"keep this")
    before = [(p.name, p.read_bytes()) for p in target.iterdir()] if target.is_dir() else target.read_bytes()
    with pytest.raises(FileExistsError):
        demo_pki.prepare_demo(target, None)
    after = [(p.name, p.read_bytes()) for p in target.iterdir()] if target.is_dir() else target.read_bytes()
    assert after == before


def test_repository_and_production_paths_are_rejected_before_creating(tmp_path, monkeypatch):
    production = tmp_path / "production-state"
    monkeypatch.setattr(demo_pki, "PRODUCTION_STATE", production)
    for target in (demo_pki.REPOSITORY / "must-not-create-demo", production, production / "demo"):
        assert not target.exists()
        with pytest.raises(ValueError, match="FUERA"):
            demo_pki.prepare_demo(target, None)
        assert not target.exists()


def test_legacy_state_and_relative_path_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    target = tmp_path / "ServerTec" / "state" / "demo"
    with pytest.raises(ValueError, match="FUERA"):
        demo_pki.prepare_demo(target, None)
    with pytest.raises(ValueError, match="absoluta"):
        demo_pki.prepare_demo(Path("relative-demo"), None)
    assert not target.exists()


@pytest.mark.parametrize("password", [b"short", b"x" * 1024, "not bytes"])
def test_bad_passphrase_does_not_create_a_directory(tmp_path, password):
    target = tmp_path / "bad-password"
    with pytest.raises(ValueError, match="frase"):
        demo_pki.prepare_demo(target, password)
    assert not target.exists()


def test_acl_failure_leaves_no_secrets_and_never_removes_partial_directory(tmp_path, monkeypatch):
    target = tmp_path / "failed-acl"

    def fail(_):
        raise subprocess.CalledProcessError(1, ["icacls.exe"])

    monkeypatch.setattr(demo_pki, "_secure_directory", fail)
    with pytest.raises(subprocess.CalledProcessError):
        demo_pki.prepare_demo(target, None)
    assert target.is_dir() and list(target.iterdir()) == []
    with pytest.raises(FileExistsError):
        demo_pki.prepare_demo(target, None)


def test_all_directories_are_protected_before_first_write(tmp_path, monkeypatch):
    events = []
    secure = demo_pki._secure_directory
    write_new = demo_pki._write_new

    def secure_recorded(path):
        secure(path)
        events.append(("protected", path.name))

    def write_recorded(path, content):
        assert [kind for kind, _ in events[:4]] == ["protected"] * 4
        events.append(("write", path.name))
        write_new(path, content)

    monkeypatch.setattr(demo_pki, "_secure_directory", secure_recorded)
    monkeypatch.setattr(demo_pki, "_write_new", write_recorded)
    demo_pki.prepare_demo(tmp_path / "acl-before-write", PASSWORD)
    assert events[:4] == [("protected", name) for name in ("acl-before-write", "authority", "runtime", "public")]


def test_new_file_creation_never_overwrites(tmp_path):
    target = tmp_path / "existing.key"
    target.write_bytes(b"ORIGINAL")
    with pytest.raises(FileExistsError):
        demo_pki._write_new(target, b"replacement")
    assert target.read_bytes() == b"ORIGINAL"


@pytest.mark.parametrize("which", ["fingerprint", "scope", "der"])
def test_inspect_rejects_public_metadata_or_certificate_tampering(prepared, which):
    directory, metadata = prepared
    if which == "der":
        _, another, _, _, _, _ = demo_pki._make_certificates()
        (directory / "public" / "authority.cer").write_bytes(another.public_bytes(serialization.Encoding.DER))
    else:
        metadata["authority_certificate_sha256" if which == "fingerprint" else "leaf_dns_san"] = "changed"
        (directory / "public" / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError):
        demo_pki.inspect_demo(directory)


def test_cli_one_shot_and_inspect_emit_only_public_metadata(tmp_path, monkeypatch, capsys):
    target = tmp_path / "cli-demo"
    monkeypatch.setattr(demo_pki.getpass, "getpass", lambda *_: pytest.fail("Unexpected passphrase prompt"))
    demo_pki.main(["prepare", "--one-shot", "--directory", str(target)])
    first = json.loads(capsys.readouterr().out)
    demo_pki.main(["inspect", "--directory", str(target)])
    second = json.loads(capsys.readouterr().out)
    assert first == second
    assert "PRIVATE KEY" not in json.dumps(first)
    assert first["authority_key_retained"] is False


def test_cli_rejects_existing_directory_before_passphrase_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(demo_pki.getpass, "getpass", lambda *_: pytest.fail("Unexpected passphrase prompt"))
    with pytest.raises(FileExistsError):
        demo_pki.main(["prepare", "--directory", str(tmp_path)])


def _reissue(cert, signing_key, *, omit=(), extra=()):
    builder = (x509.CertificateBuilder().subject_name(cert.subject)
               .issuer_name(cert.issuer).public_key(cert.public_key())
               .serial_number(cert.serial_number)
               .not_valid_before(cert.not_valid_before_utc)
               .not_valid_after(cert.not_valid_after_utc))
    for extension in cert.extensions:
        if not isinstance(extension.value, omit):
            builder = builder.add_extension(extension.value, critical=extension.critical)
    for value, critical in extra:
        builder = builder.add_extension(value, critical=critical)
    return builder.sign(signing_key, hashes.SHA256())


@pytest.mark.parametrize("level", ["root", "intermediate"])
def test_inspection_rejects_authority_with_san_to_preserve_browser_anchor_role(level):
    authority_key, authority, _, issuer, _, server = demo_pki._make_certificates()
    target = authority if level == "root" else issuer
    modified = _reissue(target, authority_key,
                        extra=[(x509.SubjectAlternativeName([x509.DNSName(demo_pki.HOSTNAME)]), False)])
    with pytest.raises(ValueError, match="autoridad.*SAN"):
        demo_pki._check_certificates(modified if level == "root" else authority,
                                     modified if level == "intermediate" else issuer, server)


@pytest.mark.parametrize("level", ["root", "intermediate"])
@pytest.mark.parametrize("critical", [None, False])
def test_inspection_requires_critical_constraints_at_both_ca_levels(level, critical):
    authority_key, authority, _, issuer, _, server = demo_pki._make_certificates()
    target = authority if level == "root" else issuer
    extra = [] if critical is None else [(demo_pki._name_constraints(), critical)]
    modified = _reissue(target, authority_key, omit=(x509.NameConstraints,), extra=extra)
    with pytest.raises(ValueError):
        demo_pki._check_certificates(modified if level == "root" else authority,
                                     modified if level == "intermediate" else issuer, server)


@pytest.mark.parametrize("which", ["issuer", "order", "extra-root", "root-pem-extra", "issuer-pem-extra", "root-der-extra"])
def test_inspection_rejects_incomplete_or_changed_chain(prepared, which):
    directory, _ = prepared
    chain_path = directory / "runtime" / "server.pem"
    root_path = directory / "public" / "authority.pem"
    issuer_path = directory / "public" / "issuer.pem"
    chain = x509.load_pem_x509_certificates(chain_path.read_bytes())
    leaf_pem = chain[0].public_bytes(serialization.Encoding.PEM)
    issuer_pem = issuer_path.read_bytes()
    if which == "issuer":
        chain_path.write_bytes(leaf_pem)
    elif which == "order":
        chain_path.write_bytes(issuer_pem + leaf_pem)
    elif which == "extra-root":
        chain_path.write_bytes(chain_path.read_bytes() + root_path.read_bytes())
    elif which == "root-pem-extra":
        root_path.write_bytes(root_path.read_bytes() + issuer_pem)
    elif which == "issuer-pem-extra":
        issuer_path.write_bytes(issuer_pem + root_path.read_bytes())
    else:
        der_path = directory / "public" / "authority.cer"
        der_path.write_bytes(der_path.read_bytes() + b"unexpected")
    with pytest.raises(ValueError):
        demo_pki.inspect_demo(directory)


def _issue_test_leaf(authority_key, authority, san):
    key = ec.generate_private_key(ec.SECP256R1())
    start = datetime.now(timezone.utc) - timedelta(minutes=1)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, demo_pki.HOSTNAME)]))
        .issuer_name(authority.subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(start)
        .not_valid_after(start + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(demo_pki._key_usage(authority=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(authority_key.public_key()), critical=False)
        .sign(authority_key, hashes.SHA256())
    )
    return key, cert


def _exchange_tls(tmp_path, authority, key, certificate, name, *, issuer=None):
    """Validate a real TLS socket with the CA explicitly loaded, never system trust."""
    cert_path, key_path = tmp_path / "tls-server.pem", tmp_path / "tls-server-key.pem"
    chain_pem = certificate.public_bytes(serialization.Encoding.PEM)
    if issuer is not None:
        chain_pem += issuer.public_bytes(serialization.Encoding.PEM)
    cert_path.write_bytes(chain_pem)
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                          serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.minimum_version = ssl.TLSVersion.TLSv1_2
    server_context.load_cert_chain(cert_path, key_path)
    client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client_context.minimum_version = ssl.TLSVersion.TLSv1_2
    client_context.load_verify_locations(cadata=authority.public_bytes(serialization.Encoding.PEM).decode("ascii"))
    # SSLContext(PROTOCOL_TLS_CLIENT) leaves key logging disabled even when a
    # user's shell defines SSLKEYLOGFILE. Chain and hostname checks remain on.
    assert client_context.check_hostname and client_context.verify_mode == ssl.CERT_REQUIRED
    assert client_context.keylog_filename is None
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(5)
        errors = []

        def serve():
            try:
                with listener.accept()[0] as connection:
                    with server_context.wrap_socket(connection, server_side=True) as secured:
                        secured.sendall(b"validated")
            except ssl.SSLError:
                # A rejected client chain closes the peer's handshake too.
                pass
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=serve)
        thread.start()
        try:
            with socket.create_connection(listener.getsockname(), timeout=5) as connection:
                with client_context.wrap_socket(connection, server_hostname=name) as secured:
                    return secured.recv(20)
        finally:
            thread.join(timeout=6)
            assert not thread.is_alive()
            assert errors == []


@pytest.mark.parametrize("root_constraints", [True, False])
@pytest.mark.parametrize("name,should_succeed", [
    (demo_pki.HOSTNAME, True),
    ("sub." + demo_pki.HOSTNAME, False),
    ("deep.sub." + demo_pki.HOSTNAME, False),
    ("unrelated.invalid", False),
    ("127.0.0.1", False),
    ("::1", False),
])
def test_real_tls_enforces_intermediate_constraints_even_without_root_constraints(
        tmp_path, name, should_succeed, root_constraints):
    authority_key, authority, issuer_key, issuer, _, _ = demo_pki._make_certificates()
    if not root_constraints:
        # Simulate Android ignoring anchor constraints: same subject/key/AKI,
        # self-signed root reissued with NO NameConstraints at all.
        authority = _reissue(authority, authority_key, omit=(x509.NameConstraints,))
    try:
        san = x509.IPAddress(ipaddress.ip_address(name))
    except ValueError:
        san = x509.DNSName(name)
    key, server = _issue_test_leaf(issuer_key, issuer, [san])
    if should_succeed:
        assert _exchange_tls(tmp_path, authority, key, server, name, issuer=issuer) == b"validated"
    else:
        with pytest.raises(ssl.SSLCertVerificationError) as rejected:
            _exchange_tls(tmp_path, authority, key, server, name, issuer=issuer)
        assert "subtree violation" in str(rejected.value).lower()


def test_real_tls_rejects_wrong_authority(tmp_path):
    _, authority, _, issuer, key, server = demo_pki._make_certificates()
    _, unrelated_authority, _, _, _, _ = demo_pki._make_certificates()
    assert authority != unrelated_authority
    with pytest.raises(ssl.SSLCertVerificationError):
        _exchange_tls(tmp_path, unrelated_authority, key, server, demo_pki.HOSTNAME, issuer=issuer)


def test_real_tls_rejects_wrong_hostname_even_with_correct_authority(tmp_path):
    _, authority, _, issuer, key, server = demo_pki._make_certificates()
    with pytest.raises(ssl.SSLCertVerificationError):
        _exchange_tls(tmp_path, authority, key, server, "wrong.invalid", issuer=issuer)


@pytest.mark.parametrize("name", ["sub." + demo_pki.HOSTNAME, "127.0.0.1", "::1"])
def test_negative_control_without_any_constraints_accepts_the_misissued_name(tmp_path, name):
    """Prove rejection above comes from constraints, not a hostname/chain error."""
    authority_key, authority, issuer_key, issuer, _, _ = demo_pki._make_certificates()
    authority = _reissue(authority, authority_key, omit=(x509.NameConstraints,))
    issuer = _reissue(issuer, authority_key, omit=(x509.NameConstraints,))
    try:
        san = x509.IPAddress(ipaddress.ip_address(name))
    except ValueError:
        san = x509.DNSName(name)
    key, server = _issue_test_leaf(issuer_key, issuer, [san])
    assert _exchange_tls(tmp_path, authority, key, server, name, issuer=issuer) == b"validated"
