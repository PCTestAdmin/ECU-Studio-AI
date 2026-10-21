"""Ed25519 against the RFC 8032 test vectors, and the update message binding."""
import pytest
from ecu_studio.core import signing

# RFC 8032, section 7.1, TEST 1 and TEST 2
VECTORS = [
    ('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60',
     'd75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a', '',
     'e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b'),
    ('4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb',
     '3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c', '72',
     '92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00'),
]


@pytest.mark.parametrize('secret,public,message,signature', VECTORS)
def test_rfc8032_vectors(secret, public, message, signature):
    sk, pk, msg, sig = (bytes.fromhex(x) for x in (secret, public, message, signature))
    assert signing.public_key(sk) == pk
    assert signing.sign(sk, msg) == sig
    assert signing.verify(pk, msg, sig)


def test_tampering_is_rejected():
    sk = bytes(range(32)); pk = signing.public_key(sk)
    msg = signing.update_message('ECU-Studio-AI-9.9.0-windows-x64.zip', 'ab' * 32)
    sig = signing.sign(sk, msg)
    assert signing.verify(pk, msg, sig)
    assert not signing.verify(pk, signing.update_message('ECU-Studio-AI-9.9.1-windows-x64.zip', 'ab' * 32), sig)
    assert not signing.verify(pk, signing.update_message('ECU-Studio-AI-9.9.0-windows-x64.zip', 'ac' * 32), sig)
    assert not signing.verify(pk, msg, sig[:-1] + bytes([sig[-1] ^ 1]))
    assert not signing.verify(signing.public_key(bytes(32)), msg, sig)
    assert not signing.verify(pk, msg, b'short')
