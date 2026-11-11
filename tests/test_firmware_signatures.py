"""Firmware signature status (core/firmware_signatures.py) with SYNTHETIC test keys only.

The keys are derived here from fixed seeds; they belong to no manufacturer and sign only synthetic images. The
tests prove the status rules: valid/invalid only after a real cryptographic check with a trusted key, never with a
key taken from the file, no signature ever changes the checksum status, and the module offers no way to create,
change or remove a signature in firmware.
"""
import hashlib
import inspect
import json
import random

import numpy as np
import pytest

from ecu_studio.core import firmware_signatures as fs
from ecu_studio.core import integrity as ig
from ecu_studio.core import signing
from ecu_studio.core.model import BinaryImage

SIGNED = ((0x1000, 0x1FFF), (0x4000, 0x47FF))
SIG_AT = 0x8000


# --- synthetic keys ----------------------------------------------------------------------------------------------

def _is_probable_prime(n, rng, rounds=40):
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        x = pow(rng.randrange(2, n - 1), d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime(bits, rng):
    while True:
        c = rng.getrandbits(bits) | (1 << (bits - 1)) | (1 << (bits - 2)) | 1
        if _is_probable_prime(c, rng):
            return c


@pytest.fixture(scope='module')
def rsa_key():
    """Synthetic 2048-bit RSA test key (seeded, built here, used nowhere else)."""
    rng = random.Random(20261111)
    e = 65537
    while True:
        p, q = _prime(1024, rng), _prime(1024, rng)
        phi = (p - 1) * (q - 1)
        if p != q and (p * q).bit_length() == 2048 and phi % e:
            return p * q, e, pow(e, -1, phi)


def rsa_sign(key, message):
    n, e, d = key
    k = (n.bit_length() + 7) // 8
    t = fs._SHA256_DIGEST_INFO + hashlib.sha256(message).digest()
    em = b'\x00\x01' + b'\xff' * (k - len(t) - 3) + b'\x00' + t
    return pow(int.from_bytes(em, 'big'), d, n).to_bytes(k, 'big')


ED_SECRET = hashlib.sha256(b'ECU Studio AI synthetic firmware signature test key').digest()
ED_PUBLIC = signing.public_key(ED_SECRET)


def image(seed=5, size=0x10000):
    return bytearray(np.random.default_rng(seed).integers(0, 256, size, dtype=np.uint8).tobytes())


def ed_candidate(data, key_id='test-ed25519'):
    sig = signing.sign(ED_SECRET, fs.signed_bytes(bytes(data), SIGNED))
    data[SIG_AT:SIG_AT + 64] = sig
    return fs.SignatureCandidate('Synthetische Testsignatur', 'ed25519', SIGNED, sig, SIG_AT, key_id)


def rsa_candidate(data, key, key_id='test-rsa'):
    sig = rsa_sign(key, fs.signed_bytes(bytes(data), SIGNED))
    data[SIG_AT:SIG_AT + len(sig)] = sig
    return fs.SignatureCandidate('Synthetische Testsignatur', 'rsa-pkcs1v15-sha256', SIGNED, sig, SIG_AT, key_id)


def store(rsa=None):
    keys = {'test-ed25519': fs.TrustedKey('test-ed25519', 'ed25519', ED_PUBLIC, 'synthetischer Testschlüssel')}
    if rsa:
        keys['test-rsa'] = fs.TrustedKey('test-rsa', 'rsa-pkcs1v15-sha256', rsa[:2], 'synthetischer Testschlüssel')
    return keys


# --- verification ------------------------------------------------------------------------------------------------

def test_ed25519_valid_then_invalid_after_any_change_of_the_signed_bytes():
    data = image()
    cand = ed_candidate(data)
    assert fs.verify_candidate(bytes(data), cand, store()).state == fs.GUELTIG
    outside = bytearray(data)
    outside[0x3000] ^= 1                                               # not signed
    assert fs.verify_candidate(bytes(outside), cand, store()).state == fs.GUELTIG
    for offset in (0x1000, 0x1FFF, 0x4000, 0x47FF):
        changed = bytearray(data)
        changed[offset] ^= 1
        assert fs.verify_candidate(bytes(changed), cand, store()).state == fs.UNGUELTIG
    forged = fs.SignatureCandidate(cand.kind, cand.scheme, cand.ranges, bytes([cand.signature[0] ^ 1]) + cand.signature[1:],
                                   cand.location, cand.key_id)
    assert fs.verify_candidate(bytes(data), forged, store()).state == fs.UNGUELTIG


def test_rsa_valid_then_invalid(rsa_key):
    data = image(6)
    cand = rsa_candidate(data, rsa_key)
    assert fs.verify_candidate(bytes(data), cand, store(rsa_key)).state == fs.GUELTIG
    data[0x4100] ^= 0x80
    assert fs.verify_candidate(bytes(data), cand, store(rsa_key)).state == fs.UNGUELTIG


def test_rsa_verifier_fails_closed_on_malformed_input(rsa_key):
    n, e, d = rsa_key
    msg = b'synthetische Nachricht'
    sig = rsa_sign(rsa_key, msg)
    assert fs.rsa_pkcs1v15_sha256_verify(n, e, msg, sig)
    assert not fs.rsa_pkcs1v15_sha256_verify(n, e, msg + b'!', sig)
    assert not fs.rsa_pkcs1v15_sha256_verify(n, e, msg, sig[1:])                    # wrong length
    assert not fs.rsa_pkcs1v15_sha256_verify(n, e, msg, (n + 1).to_bytes(256, 'big'))   # s >= n
    assert not fs.rsa_pkcs1v15_sha256_verify(n, 4, msg, sig)                          # even exponent
    small = 0xC5 << 1000 | 1
    assert not fs.rsa_pkcs1v15_sha256_verify(small, e, msg, sig[:126])               # modulus < 2048 bit
    # another digest (SHA-1 DigestInfo) with correct padding is not accepted as SHA-256
    k = 256
    t = bytes.fromhex('3021300906052b0e03021a05000414') + hashlib.sha1(msg).digest()
    em = b'\x00\x01' + b'\xff' * (k - len(t) - 3) + b'\x00' + t
    assert not fs.rsa_pkcs1v15_sha256_verify(n, e, msg, pow(int.from_bytes(em, 'big'), d, n).to_bytes(k, 'big'))


def test_without_a_trusted_key_the_signature_is_only_recognised():
    data = image()
    cand = ed_candidate(data)
    assert fs.verify_candidate(bytes(data), cand, None).state == fs.ERKANNT
    assert fs.verify_candidate(bytes(data), cand, {}).state == fs.ERKANNT
    anonymous = fs.SignatureCandidate(cand.kind, cand.scheme, cand.ranges, cand.signature, cand.location, None)
    assert fs.verify_candidate(bytes(data), anonymous, store()).state == fs.ERKANNT
    unknown_id = fs.SignatureCandidate(cand.kind, cand.scheme, cand.ranges, cand.signature, cand.location, 'other')
    assert fs.verify_candidate(bytes(data), unknown_id, store()).state == fs.ERKANNT


def test_key_found_in_the_firmware_is_no_trust_anchor():
    """Whoever changes the firmware can replace an embedded key too: a self-signed image stays "erkannt"."""
    data = image(8)
    attacker_secret = hashlib.sha256(b'someone else').digest()
    data[0x9000:0x9020] = signing.public_key(attacker_secret)               # key shipped inside the image
    sig = signing.sign(attacker_secret, fs.signed_bytes(bytes(data), SIGNED))
    cand = fs.SignatureCandidate('Eingebetteter Schlüssel', 'ed25519', SIGNED, sig, SIG_AT, None)
    assert fs.verify_candidate(bytes(data), cand, store()).state == fs.ERKANNT
    # and against the trusted key with the same id it is invalid, never valid
    same_id = fs.SignatureCandidate(cand.kind, cand.scheme, SIGNED, sig, SIG_AT, 'test-ed25519')
    assert fs.verify_candidate(bytes(data), same_id, store()).state == fs.UNGUELTIG


def test_unsupported_scheme_wrong_scheme_and_ranges_outside_the_file():
    data = image()
    cand = ed_candidate(data)
    pss = fs.SignatureCandidate(cand.kind, 'rsa-pss-sha256', SIGNED, cand.signature, SIG_AT, 'test-ed25519')
    assert fs.verify_candidate(bytes(data), pss, store()).state == fs.NICHT_UNTERSTUETZT
    mixed = fs.SignatureCandidate(cand.kind, 'rsa-pkcs1v15-sha256', SIGNED, cand.signature, SIG_AT, 'test-ed25519')
    assert fs.verify_candidate(bytes(data), mixed, store()).state == fs.ERKANNT
    for ranges in (((0x1000, 0x20000),), ((0x2000, 0x1000),), ((-1, 4),), ()):
        out = fs.SignatureCandidate(cand.kind, 'ed25519', ranges, cand.signature, SIG_AT, 'test-ed25519')
        assert fs.verify_candidate(bytes(data), out, store()).state == fs.ERKANNT


def test_trust_store_is_explicit_and_fails_closed(tmp_path, rsa_key):
    path = tmp_path / 'trust.json'
    good = {'format': 1, 'keys': {
        'ed': {'scheme': 'ed25519', 'public_key': ED_PUBLIC.hex(), 'source': 'synthetisch'},
        'rsa': {'scheme': 'rsa-pkcs1v15-sha256', 'n': f'{rsa_key[0]:x}', 'e': rsa_key[1], 'source': 'synthetisch'},
        'ohne-herkunft': {'scheme': 'ed25519', 'public_key': ED_PUBLIC.hex()},
        'kurz': {'scheme': 'ed25519', 'public_key': ED_PUBLIC.hex()[:62], 'source': 'x'},
        'rsa-klein': {'scheme': 'rsa-pkcs1v15-sha256', 'n': f'{(1 << 1023) | 1:x}', 'e': 65537, 'source': 'x'},
        'rsa-e-gerade': {'scheme': 'rsa-pkcs1v15-sha256', 'n': f'{rsa_key[0]:x}', 'e': 4, 'source': 'x'},
        'fremd': {'scheme': 'dsa', 'public_key': '00', 'source': 'x'}}}
    path.write_text(json.dumps(good), encoding='utf-8')
    assert sorted(fs.load_trust_store(path)) == ['ed', 'rsa']
    for broken in ('', '{', '[]', '{"format": 2, "keys": {}}', '{"format": 1, "keys": []}'):
        path.write_text(broken, encoding='utf-8')
        assert fs.load_trust_store(path) == {}
    assert fs.load_trust_store(tmp_path / 'fehlt.json') == {}


def test_module_only_verifies():
    """No function creates, changes, removes or bypasses a firmware signature."""
    public = {name for name, obj in vars(fs).items() if callable(obj) and not name.startswith('_')
              and getattr(obj, '__module__', '') == fs.__name__}
    assert public == {'TrustedKey', 'SignatureCandidate', 'SignatureResult', 'rsa_pkcs1v15_sha256_verify',
                      'load_trust_store', 'signed_bytes', 'verify_candidate'}
    source = inspect.getsource(fs)
    assert 'signing.sign(' not in source and '.write(' not in source


# --- integrity report --------------------------------------------------------------------------------------------

def test_signature_status_never_changes_the_checksum_status():
    data = image(9)
    cand = ed_candidate(data)
    plain = ig.check_integrity(BinaryImage(bytes(data)))
    signed = ig.check_integrity(BinaryImage(bytes(data)), signatures=[cand], trust=store())
    assert signed.status == plain.status == ig.UNKNOWN                    # a valid signature is no checksum proof
    assert [(s.kind, s.state) for s in signed.signatures] == [('Synthetische Testsignatur', 'gueltig')]
    assert signed.asdict()['flash_approved'] is False and 'kryptographisch' in ig.SIGNATURE_TEXT['gueltig']
    image_ = BinaryImage(bytes(data))
    image_.write(0x1100, bytes([data[0x1100] ^ 1]))
    changed = ig.check_integrity(image_, signatures=[cand], trust=store())
    assert [s.state for s in changed.signatures] == ['ungueltig'] and changed.status == ig.UNKNOWN
    assert any('Herstellersignatur stimmt nicht' in r for r in changed.reasons)
    unverified = ig.check_integrity(BinaryImage(bytes(data)), signatures=[cand])
    assert [s.state for s in unverified.signatures] == ['erkannt']


def test_every_state_has_a_text_in_report_and_ui():
    assert set(ig.SIGNATURE_TEXT) == set(fs.STATES) and set(fs.STATE_TEXT) == set(fs.STATES)
    assert fs.SignatureResult('x', fs.GUELTIG).domain == 'oem-firmware'
