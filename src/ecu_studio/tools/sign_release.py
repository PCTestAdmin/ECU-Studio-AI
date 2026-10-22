"""Signing key and release signatures for updates (Ed25519, core/signing.py).

  python -m ecu_studio.tools.sign_release keygen --secret-out C:\\sicher\\update_signing.key
      Creates a key pair. The SECRET goes to the given file (keep it outside the
      repository; store its content as GitHub secret UPDATE_SIGNING_KEY). The
      PUBLIC key is written to recognition/data/update_signing_key.pub - commit it;
      from then on the app only installs updates with a valid signature.

  python -m ecu_studio.tools.sign_release sign FILE [FILE ...]
      Signs release files with the secret from the environment variable
      UPDATE_SIGNING_KEY (hex) and writes FILE.sig (base64). Fails if a public key
      is shipped but no secret is available, or if the secret does not belong to
      the shipped key - a release the installed apps would reject is never built.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import os
import secrets
import sys
from pathlib import Path
from ecu_studio.core import signing


def keygen(key_file: Path) -> int:
    # Messages never contain the key file's path or content: console output ends
    # up in CI logs and terminal histories (CodeQL py/clear-text-logging).
    if key_file.exists():
        print('Die angegebene Schlüsseldatei existiert bereits – nicht überschrieben.', file=sys.stderr)
        return 2
    repo = Path(__file__).resolve().parents[3]
    if repo in key_file.resolve().parents:
        print('Der geheime Schlüssel darf nicht im Repository liegen.', file=sys.stderr)
        return 2
    seed = secrets.token_bytes(32)
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(seed.hex() + '\n', encoding='ascii')
    signing.PUBLIC_KEY_FILE.write_text(signing.public_key(seed).hex() + '\n', encoding='ascii')
    print('Geheimer Schlüssel in die angegebene Datei geschrieben '
          '(Inhalt als GitHub-Secret UPDATE_SIGNING_KEY hinterlegen, Datei nie committen).')
    print(f'Öffentlicher Schlüssel: {signing.PUBLIC_KEY_FILE}  (committen)')
    return 0


def sign_files(files: list[Path]) -> int:
    shipped = signing.trusted_key()
    raw = os.environ.get('UPDATE_SIGNING_KEY', '').strip()
    if not raw:
        if shipped is not None:
            print('UPDATE_SIGNING_KEY fehlt, aber die App verlangt Signaturen – Release abgebrochen.', file=sys.stderr)
            return 1
        print('Kein Signaturschlüssel konfiguriert – Dateien bleiben unsigniert.')
        return 0
    secret = bytes.fromhex(raw)
    public = signing.public_key(secret)
    if shipped is not None and public != shipped:
        print('UPDATE_SIGNING_KEY gehört nicht zum ausgelieferten öffentlichen Schlüssel – abgebrochen.', file=sys.stderr)
        return 1
    for path in files:
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        signature = signing.sign(secret, signing.update_message(path.name, sha))
        assert signing.verify(public, signing.update_message(path.name, sha), signature)
        Path(str(path) + '.sig').write_text(base64.b64encode(signature).decode('ascii') + '\n', encoding='ascii')
        print(f'signiert: {path.name}')
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    k = sub.add_parser('keygen'); k.add_argument('--secret-out', dest='key_file', type=Path, required=True)
    s = sub.add_parser('sign'); s.add_argument('files', nargs='+', type=Path)
    args = parser.parse_args(argv)
    return keygen(args.key_file) if args.command == 'keygen' else sign_files(args.files)


if __name__ == '__main__':
    raise SystemExit(main())
