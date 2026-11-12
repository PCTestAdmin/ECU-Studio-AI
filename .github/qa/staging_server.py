"""Isolated STAGING update source for the in-app update test of a release candidate.

Only for a fresh GitHub-hosted runner (installer_test.ps1 -Mode InApp). The installed old version asks
https://api.github.com/repos/<repo>/releases/latest and downloads from https://github.com/<repo>/releases/download/...
(hard-coded in core/updates.py). On the runner, the hosts file points both names to 127.0.0.1, this server answers
with a release payload for the candidate, and a throw-away test CA (created here, trusted only on this runner,
removed afterwards) makes TLS verification pass. Nothing is published: no tag, no GitHub release.

  python staging_server.py <work dir> <package dir> <repository>

Writes <work>/ca.cer (to be imported into the runner's root store), <work>/ready when listening, and logs every
request to <work>/requests.log. When the package contains the setup.exe with its .sha256, the payload lists them
too, exactly as release.yml publishes them (installations made with the installer update with it from 1.20.1).
"""
import datetime
import hashlib
import http.server
import json
import ssl
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

WORK, PACKAGE, REPOSITORY = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
WORK.mkdir(parents=True, exist_ok=True)
HOSTS = ['api.github.com', 'github.com']


def certificates():
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key, key = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'ECU Studio QA staging CA (runner only)')])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=5))
          .not_valid_after(now + datetime.timedelta(days=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .sign(ca_key, hashes.SHA256()))
    leaf = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, HOSTS[0])])).issuer_name(ca_name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(True, False, False, False, False, False, False, False, False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(h) for h in HOSTS]), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    (WORK / 'ca.cer').write_bytes(ca.public_bytes(serialization.Encoding.DER))
    (WORK / 'server.pem').write_bytes(leaf.public_bytes(serialization.Encoding.PEM)
                                      + ca.public_bytes(serialization.Encoding.PEM))
    (WORK / 'server.key').write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                                        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))


version = (PACKAGE / 'VERSION.txt').read_text(encoding='utf-8').strip()
archive = PACKAGE / f'ECU-Studio-AI-{version}-windows-x64.zip'
checksum = PACKAGE / f'{archive.name}.sha256'
notes_file = PACKAGE / 'release-notes.md'
notes = notes_file.read_text(encoding='utf-8') if notes_file.is_file() else ''
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
if checksum.read_text(encoding='ascii').split()[0].lower() != digest:
    raise SystemExit('package .sha256 does not match the archive')
tag = f'v{version}'
download = f'https://github.com/{REPOSITORY}/releases/download/{tag}/'
ASSETS = [(archive, digest), (checksum, None)]
setup = PACKAGE / f'ECU-Studio-AI-{version}-setup.exe'
setup_checksum = PACKAGE / f'{setup.name}.sha256'
if setup.is_file() and setup_checksum.is_file():
    setup_digest = hashlib.sha256(setup.read_bytes()).hexdigest()
    if setup_checksum.read_text(encoding='ascii').split()[0].lower() != setup_digest:
        raise SystemExit('package .sha256 does not match the setup')
    ASSETS += [(setup, setup_digest), (setup_checksum, None)]
FILES = {f'/{REPOSITORY}/releases/download/{tag}/{p.name}': p for p, _ in ASSETS}
PAYLOAD = json.dumps({
    'tag_name': tag, 'name': f'ECU Studio AI {version} (QA staging, not published)', 'draft': False,
    'prerelease': False, 'html_url': f'https://github.com/{REPOSITORY}/releases/tag/{tag}',
    'body': notes + '\n---\nQA staging source on an isolated runner.\n',
    'assets': [dict({'name': p.name, 'size': p.stat().st_size, 'browser_download_url': download + p.name},
                    **({'digest': f'sha256:{d}'} if d else {})) for p, d in ASSETS]}).encode('utf-8')
LATEST = f'/repos/{REPOSITORY}/releases/latest'


class Handler(http.server.BaseHTTPRequestHandler):
    def _log(self, status, size):
        with open(WORK / 'requests.log', 'a', encoding='utf-8') as log:
            log.write(json.dumps({'host': self.headers.get('Host'), 'path': self.path, 'status': status, 'bytes': size,
                                  'agent': self.headers.get('User-Agent')}) + '\n')

    def do_GET(self):
        host = (self.headers.get('Host') or '').split(':')[0]
        if host == 'api.github.com' and self.path == LATEST:
            body, kind = PAYLOAD, 'application/json'
        elif host == 'github.com' and self.path in FILES:
            body, kind = FILES[self.path].read_bytes(), 'application/octet-stream'
        else:
            self.send_response(404); self.end_headers(); self._log(404, 0); return
        self.send_response(200)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self._log(200, len(body))

    def log_message(self, *args):
        pass


certificates()
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(WORK / 'server.pem', WORK / 'server.key')
import os
server = http.server.ThreadingHTTPServer(('127.0.0.1', int(os.environ.get('QA_STAGING_PORT', '443'))), Handler)
server.socket = context.wrap_socket(server.socket, server_side=True)
(WORK / 'ready').write_text(json.dumps({'version': version, 'sha256': digest, 'archive': archive.name,
                                       'assets': [p.name for p, _ in ASSETS]}), encoding='utf-8')
server.serve_forever()
