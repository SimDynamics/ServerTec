"""Opt-in, isolated HTTPS identity for the public-menu demonstration.

Nothing is installed into a trust store and no production settings are imported.
The leaf has precisely one DNS SAN. The permitted DNS subtree is paired with a
leading-dot exclusion for its descendants. IP names are excluded in both families.
Both root and intermediate carry these constraints. The intermediate is sent
with the leaf so the restriction is checked even when an Android trust anchor's
constraints are ignored. Import only the root, never the intermediate as a root.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import getpass
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


HOSTNAME = "learngraphicsprogramming.dynamics"
PUBLIC_HOSTNAME = "servertec-demo.example.invalid"
ALLOWED_HOSTNAMES = (HOSTNAME, PUBLIC_HOSTNAME)
DEFAULT_DIRECTORY = Path(r"D:\Projects\ServerTec\demo-web-20261019")
REPOSITORY = Path(__file__).resolve().parent
PRODUCTION_STATE = Path(r"D:\Projects\ServerTec\state")
AUTHORITY_LIFETIME = timedelta(days=30)
ISSUER_LIFETIME = timedelta(days=7)
LEAF_LIFETIME = timedelta(days=7)
SCOPE_NOTE = (
    "The permitted DNS subtree includes the domain and descendants; the additional "
    "leading-dot DNS exclusion blocks descendants in OpenSSL/Chrome semantics. "
    "The intended DNS scope and sole leaf SAN are learngraphicsprogramming.dynamics. "
    "IPv4 and IPv6 SANs are explicitly excluded; other SAN types are not constrained. "
    "These constraints are critical in the intermediate as well as the root. "
    "Android Chrome may ignore constraints on an imported root, so import ONLY "
    "the root, never the intermediate. Android user-CA trust covers the Android "
    "user/profile and is not limited to a Chrome test profile. A retained root key "
    "could issue a different chain without this intermediate; one-shot is preferred. "
    "Verify the actual client before trusting. Empty IP constraints do not mean deny."
)


def checked_directory(directory: Path, *, must_be_new: bool) -> Path:
    """Resolve aliases before checking scope; never create anything here."""
    if not directory.is_absolute():
        raise ValueError("La carpeta de la demo debe ser una ruta absoluta")
    resolved = directory.resolve()
    excluded = [REPOSITORY, PRODUCTION_STATE.resolve()]
    local_data = os.environ.get("LOCALAPPDATA")
    if local_data:
        excluded.append((Path(local_data) / "ServerTec" / "state").resolve())
    if any(resolved == base or resolved.is_relative_to(base) for base in excluded):
        raise ValueError("La demo debe quedar FUERA del repositorio y del estado de ServerTec")
    if must_be_new and (resolved.exists() or directory.is_symlink()):
        raise FileExistsError("La carpeta de demo ya existe; usa otra carpeta nueva. No se sobrescribe nada")
    if not must_be_new and not resolved.is_dir():
        raise ValueError("No existe una carpeta de demo preparada")
    return resolved


def _secure_directory(directory: Path) -> None:
    """Protect a newly created directory before any secret is written."""
    if sys.platform == "win32":
        result = subprocess.run(
            ["whoami.exe", "/user", "/fo", "csv", "/nh"],
            check=True, capture_output=True, text=True, timeout=15,
        )
        rows = list(csv.reader(result.stdout.splitlines()))
        sid = rows[0][-1].strip() if len(rows) == 1 and rows[0] else ""
        if not re.fullmatch(r"S-1-\d+(?:-\d+)+", sid):
            raise ValueError("No se pudo identificar al usuario para proteger la demo")
        subprocess.run(
            ["icacls.exe", str(directory), "/inheritance:r", "/grant:r",
             f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F"],
            check=True, capture_output=True, text=True, timeout=15,
        )
    else:
        directory.chmod(0o700)


def _write_new(path: Path, content: bytes) -> None:
    # The protected parent is already in place; refuse every replacement.
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
        stream.write(content)


def _key_usage(*, authority: bool) -> x509.KeyUsage:
    return x509.KeyUsage(
        digital_signature=not authority, content_commitment=False,
        key_encipherment=False, data_encipherment=False, key_agreement=False,
        key_cert_sign=authority, crl_sign=authority, encipher_only=False,
        decipher_only=False,
    )


def _name_constraints(hostname: str = hostname) -> x509.NameConstraints:
    if hostname not in ALLOWED_HOSTNAMES:
        raise ValueError('Nombre PKI no autorizado')
    return x509.NameConstraints(
        permitted_subtrees=[x509.DNSName(hostname)],
        excluded_subtrees=[x509.DNSName("." + hostname),
                           x509.IPAddress(ipaddress.ip_network("0.0.0.0/0")),
                           x509.IPAddress(ipaddress.ip_network("::/0"))],
    )


def _make_certificates(hostname: str = HOSTNAME) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate,
                                  ec.EllipticCurvePrivateKey, x509.Certificate,
                                  ec.EllipticCurvePrivateKey, x509.Certificate]:
    start = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=5)
    authority_key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"ServerTec DEMO ROOT {hostname}")])
    authority = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(authority_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(start).not_valid_after(start + AUTHORITY_LIFETIME)
        .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
        .add_extension(_key_usage(authority=True), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(authority_key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(authority_key.public_key()), critical=False)
        .add_extension(_name_constraints(hostname), critical=True)
        .sign(authority_key, hashes.SHA256())
    )
    issuer_key = ec.generate_private_key(ec.SECP256R1())
    issuer = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"ServerTec DEMO ISSUER {hostname}")]))
        .issuer_name(authority.subject).public_key(issuer_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start).not_valid_after(start + ISSUER_LIFETIME)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(_key_usage(authority=True), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(issuer_key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(authority_key.public_key()), critical=False)
        .add_extension(_name_constraints(hostname), critical=True)
        .sign(authority_key, hashes.SHA256())
    )
    server_key = ec.generate_private_key(ec.SECP256R1())
    server = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)]))
        .issuer_name(issuer.subject).public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start).not_valid_after(start + LEAF_LIFETIME)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(_key_usage(authority=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key()), critical=False)
        .sign(issuer_key, hashes.SHA256())
    )
    return authority_key, authority, issuer_key, issuer, server_key, server


def _metadata(authority: x509.Certificate, authority_pem: bytes,
              issuer: x509.Certificate, issuer_pem: bytes,
              server: x509.Certificate, server_pem: bytes, server_chain_pem: bytes,
              *, authority_key_retained: bool, hostname: str = HOSTNAME) -> dict:
    return {
        "schema_version": 2,
        "purpose": "ServerTec isolated web demonstration; no production identity",
        "hostname": hostname,
        "authority_key_retained": authority_key_retained,
        "issuer_key_retained": False,
        "authority_certificate_sha256": authority.fingerprint(hashes.SHA256()).hex(),
        "authority_pem_file_sha256": hashlib.sha256(authority_pem).hexdigest(),
        "issuer_certificate_sha256": issuer.fingerprint(hashes.SHA256()).hex(),
        "issuer_pem_file_sha256": hashlib.sha256(issuer_pem).hexdigest(),
        "leaf_certificate_sha256": server.fingerprint(hashes.SHA256()).hex(),
        "leaf_pem_file_sha256": hashlib.sha256(server_pem).hexdigest(),
        "server_chain_pem_file_sha256": hashlib.sha256(server_chain_pem).hexdigest(),
        "server_chain_order": ["leaf", "intermediate"],
        "authority_not_before_utc": authority.not_valid_before_utc.isoformat(),
        "authority_not_after_utc": authority.not_valid_after_utc.isoformat(),
        "issuer_not_before_utc": issuer.not_valid_before_utc.isoformat(),
        "issuer_not_after_utc": issuer.not_valid_after_utc.isoformat(),
        "leaf_not_before_utc": server.not_valid_before_utc.isoformat(),
        "leaf_not_after_utc": server.not_valid_after_utc.isoformat(),
        "authority_dns_permitted_subtrees": [hostname],
        "authority_dns_excluded_subtrees": ["." + hostname],
        "authority_ip_excluded_subtrees": ["0.0.0.0/0", "::/0"],
        "issuer_dns_permitted_subtrees": [hostname],
        "issuer_dns_excluded_subtrees": ["." + hostname],
        "issuer_ip_excluded_subtrees": ["0.0.0.0/0", "::/0"],
        "leaf_dns_san": [hostname],
        "name_constraints_scope": SCOPE_NOTE.replace(HOSTNAME, hostname),
        "fingerprint_meaning": "certificate_sha256 hashes the individual DER certificate; authority/issuer_pem_file_sha256 hash those public PEM files; leaf_pem_file_sha256 hashes ONLY the first PEM block of runtime/server.pem; server_chain_pem_file_sha256 hashes the complete leaf+intermediate PEM file",
        "trust_installation": "Not installed; independently compare the ROOT DER fingerprint before client trust. Import only public/authority.pem or authority.cer, NEVER public/issuer.pem as a trusted CA.",
        "replacement": "Leaf lifetime is 7 days. Remove the old CA from test clients and prepare a new identity in a NEW directory; existing material is never renewed or overwritten.",
    }


def prepare_demo(directory: Path, password: bytes | None, *, hostname: str = HOSTNAME) -> dict:
    """Create fresh demo material; None discards the CA signing key after use.

    The intermediate signing key is never retained. Retained root keys always
    use PKCS8 encryption. One-shot mode discards the root signing key as well;
    Python cannot promise memory zeroization. Neither
    mode installs trust, edits hosts/firewall, starts a listener or touches SQLite.
    A failed preparation deliberately leaves its protected partial folder intact.
    """
    if hostname not in ALLOWED_HOSTNAMES:
        raise ValueError('Nombre PKI no autorizado')
    directory = checked_directory(directory, must_be_new=True)
    if password is not None and (not isinstance(password, bytes) or not 16 <= len(password) <= 1023):
        raise ValueError("La frase privada debe tener entre 16 y 1023 bytes UTF-8")
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    _secure_directory(directory)
    for name in ("authority", "runtime", "public"):
        child = directory / name
        child.mkdir(mode=0o700, exist_ok=False)
        _secure_directory(child)
    authority_key, authority, issuer_key, issuer, server_key, server = _make_certificates(hostname)
    del issuer_key
    authority_pem = authority.public_bytes(serialization.Encoding.PEM)
    issuer_pem = issuer.public_bytes(serialization.Encoding.PEM)
    server_pem = server.public_bytes(serialization.Encoding.PEM)
    server_chain_pem = server_pem + issuer_pem
    if password is not None:
        _write_new(directory / "authority" / "authority-key.pem", authority_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(password),
        ))
    _write_new(directory / "runtime" / "server-key.pem", server_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
    ))
    del authority_key
    _write_new(directory / "runtime" / "server.pem", server_chain_pem)
    _write_new(directory / "public" / "authority.pem", authority_pem)
    _write_new(directory / "public" / "authority.cer", authority.public_bytes(serialization.Encoding.DER))
    _write_new(directory / "public" / "issuer.pem", issuer_pem)
    metadata = _metadata(authority, authority_pem, issuer, issuer_pem,
                         server, server_pem, server_chain_pem,
                         authority_key_retained=password is not None, hostname=hostname)
    _write_new(directory / "public" / "metadata.json", json.dumps(metadata, indent=2).encode("utf-8"))
    return inspect_demo(directory, hostname=hostname)


def _check_certificates(authority: x509.Certificate, issuer: x509.Certificate,
                        server: x509.Certificate, *, hostname: str = HOSTNAME) -> None:
    try:
        authority.verify_directly_issued_by(authority)
        issuer.verify_directly_issued_by(authority)
        server.verify_directly_issued_by(issuer)
        if authority.subject == issuer.subject:
            raise ValueError("La autoridad raiz y el emisor deben ser distintos")
        public_keys = {cert.public_key().public_bytes(serialization.Encoding.DER,
                                                     serialization.PublicFormat.SubjectPublicKeyInfo)
                       for cert in (authority, issuer, server)}
        if len(public_keys) != 3:
            raise ValueError("Cada nivel de la cadena de demo debe tener una clave distinta")
        for cert, parent, is_authority, path_length, lifetime in (
                (authority, authority, True, 1, AUTHORITY_LIFETIME),
                (issuer, authority, True, 0, ISSUER_LIFETIME),
                (server, issuer, False, None, LEAF_LIFETIME)):
            if is_authority and any(isinstance(extension.value, x509.SubjectAlternativeName)
                                    for extension in cert.extensions):
                raise ValueError("La autoridad raiz y el emisor de demo no deben incluir SAN")
            basic = cert.extensions.get_extension_for_class(x509.BasicConstraints)
            expected = x509.BasicConstraints(ca=is_authority, path_length=path_length)
            if not basic.critical or basic.value != expected:
                raise ValueError("BasicConstraints de demo incorrectos")
            usage = cert.extensions.get_extension_for_class(x509.KeyUsage)
            if not usage.critical or usage.value != _key_usage(authority=is_authority):
                raise ValueError("KeyUsage de demo incorrecto")
            eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
            if list(eku) != [ExtendedKeyUsageOID.SERVER_AUTH]:
                raise ValueError("EKU de demo incorrecto")
            public_key = cert.public_key()
            if not isinstance(public_key, ec.EllipticCurvePublicKey) or not isinstance(public_key.curve, ec.SECP256R1):
                raise ValueError("Clave publica de demo incorrecta")
            if not isinstance(cert.signature_hash_algorithm, hashes.SHA256):
                raise ValueError("Firma de demo incorrecta")
            if not timedelta(0) < cert.not_valid_after_utc - cert.not_valid_before_utc <= lifetime:
                raise ValueError("Vigencia de demo demasiado larga")
            now = datetime.now(timezone.utc)
            if not cert.not_valid_before_utc <= now < cert.not_valid_after_utc:
                raise ValueError("Certificado de demo caducado o todavia no vigente")
            ski = cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value
            if ski != x509.SubjectKeyIdentifier.from_public_key(public_key):
                raise ValueError("SKI de demo incorrecto")
            aki = cert.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value
            if aki != x509.AuthorityKeyIdentifier.from_issuer_public_key(parent.public_key()):
                raise ValueError("AKI de demo incorrecto")
            if (cert.not_valid_before_utc < parent.not_valid_before_utc
                    or cert.not_valid_after_utc > parent.not_valid_after_utc):
                raise ValueError("La vigencia del certificado excede a su emisor")
            if is_authority:
                constraints = cert.extensions.get_extension_for_class(x509.NameConstraints)
                if not constraints.critical or constraints.value != _name_constraints(hostname):
                    raise ValueError("NameConstraints de demo incorrectos")
        san = server.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        if list(san) != [x509.DNSName(hostname)]:
            raise ValueError("El SAN de demo debe contener solo el nombre exacto")
    except (x509.ExtensionNotFound, InvalidSignature) as exc:
        raise ValueError("Certificados de demo incompletos o firma no valida") from exc


def inspect_demo(directory: Path, *, hostname: str | None = None) -> dict:
    """Validate only public certificates/metadata; never open a private key."""
    directory = checked_directory(directory, must_be_new=False)
    authority_pem = (directory / "public" / "authority.pem").read_bytes()
    authority = x509.load_pem_x509_certificate(authority_pem)
    if authority_pem != authority.public_bytes(serialization.Encoding.PEM):
        raise ValueError("El PEM publico de la raiz debe contener un unico certificado canonico")
    authority_der_bytes = (directory / "public" / "authority.cer").read_bytes()
    authority_der = x509.load_der_x509_certificate(authority_der_bytes)
    if authority != authority_der or authority_der_bytes != authority.public_bytes(serialization.Encoding.DER):
        raise ValueError("Los certificados publicos PEM y DER no corresponden")
    issuer_pem = (directory / "public" / "issuer.pem").read_bytes()
    issuer = x509.load_pem_x509_certificate(issuer_pem)
    if issuer_pem != issuer.public_bytes(serialization.Encoding.PEM):
        raise ValueError("El PEM publico del emisor debe contener un unico certificado canonico")
    server_chain_pem = (directory / "runtime" / "server.pem").read_bytes()
    certificates = x509.load_pem_x509_certificates(server_chain_pem)
    if len(certificates) != 2 or certificates[1] != issuer:
        raise ValueError("La cadena de demo debe contener la hoja y el emisor intermedio, en ese orden")
    server = certificates[0]
    server_pem = server.public_bytes(serialization.Encoding.PEM)
    # The exact canonical bundle forbids extra PEM material, roots or reordered blocks.
    if server_chain_pem != server_pem + issuer_pem:
        raise ValueError("El archivo de cadena de demo contiene material adicional o no canonico")
    recorded = json.loads((directory / "public" / "metadata.json").read_text(encoding="utf-8"))
    if not isinstance(recorded, dict) or type(recorded.get("authority_key_retained")) is not bool:
        raise ValueError("Metadata de demo invalida")
    selected = recorded.get("hostname")
    if selected not in ALLOWED_HOSTNAMES or (hostname is not None and selected != hostname):
        raise ValueError("El nombre de la identidad no corresponde a la seleccion")
    _check_certificates(authority, issuer, server, hostname=selected)
    expected = _metadata(authority, authority_pem, issuer, issuer_pem,
                         server, server_pem, server_chain_pem,
                         authority_key_retained=recorded["authority_key_retained"], hostname=selected)
    if recorded != expected:
        raise ValueError("La metadata o las huellas de demo no corresponden a los certificados")
    return expected


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="PKI propia y aislada para la demo web; no instala confianza")
    parser.add_argument("action", choices=("prepare", "inspect"))
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    parser.add_argument("--hostname", choices=ALLOWED_HOSTNAMES,
                        help="Nombre TLS exacto; preparacion privada por defecto")
    parser.add_argument("--one-shot", action="store_true",
                        help="Solo prepare: no conservar la clave privada de la CA ni pedir frase")
    args = parser.parse_args(argv)
    if args.action == "inspect":
        if args.one_shot:
            parser.error("--one-shot solo se usa con prepare")
        metadata = inspect_demo(args.directory, hostname=args.hostname)
    else:
        checked_directory(args.directory, must_be_new=True)
        password = None
        if not args.one_shot:
            phrase = getpass.getpass("Frase privada nueva para cifrar la CA (minimo 16 caracteres): ")
            if len(phrase) < 16:
                raise ValueError("La frase privada debe tener al menos 16 caracteres")
            if phrase != getpass.getpass("Repite la frase privada: "):
                raise ValueError("Las frases no coinciden")
            password = phrase.encode("utf-8")
        metadata = prepare_demo(args.directory, password, hostname=args.hostname or HOSTNAME)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"No se completo la operacion PKI de demo: {exc}", file=sys.stderr)
        sys.exit(1)
