"""
Donation configuration: validation, proof of ownership, and the QR code.

The rule this module enforces: Bookworm only ever displays a Bitcoin address
it can prove is Bookworm's. An address is shown only when

  1. it is a well-formed mainnet native SegWit (P2WPKH, ``bc1q...``) address
     with a valid bech32 checksum, and
  2. ``BITCOIN_SIGNATURE`` is a valid BIP137 signature of
     ``BITCOIN_SIGNED_MESSAGE`` by that same address's key.

If either check fails, the Bitcoin option disappears from every page and an
error is logged. A typo, a half-finished edit, or an address swapped without
a matching signature therefore fails closed: no donation can go to an
address the owner never signed for.

This is a guard against mistakes and lazy tampering, not a security boundary
against someone who can edit the repository (they could delete the check).
That boundary is the deploy path: 2FA on GitHub and Railway, Ben's own
commits, and the signed message being checkable by anyone.

Everything here is pure Python (secp256k1 and bech32 are implemented below),
so the check adds no dependency. The only third-party import is ``segno``,
used to draw the QR code as inline SVG.
"""

import base64
import hashlib
import logging
from functools import lru_cache

from django.conf import settings

logger = logging.getLogger(__name__)


# =============================================================================
# bech32 / bech32m (BIP173, BIP350)
# =============================================================================

_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_BECH32_CONST = 1
_BECH32M_CONST = 0x2BC830A3


def _polymod(values):
    gen = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
    chk = 1
    for v in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ v
        for i in range(5):
            chk ^= gen[i] if (top >> i) & 1 else 0
    return chk


def _hrp_expand(hrp):
    return [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]


def _convertbits(data, frombits, tobits, pad):
    acc = bits = 0
    out = []
    maxv = (1 << tobits) - 1
    for value in data:
        if value < 0 or value >> frombits:
            return None
        acc = (acc << frombits) | value
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            out.append((acc >> bits) & maxv)
    if pad:
        if bits:
            out.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return out


def decode_segwit_address(address):
    """
    Decode a SegWit address per BIP173/BIP350.

    Returns ``(hrp, witness_version, witness_program_bytes)`` or ``None`` if
    the string is not a valid SegWit address of any network.
    """
    if not isinstance(address, str) or not 14 <= len(address) <= 90:
        return None
    if address.lower() != address and address.upper() != address:
        return None  # mixed case is invalid by spec
    address = address.lower()
    pos = address.rfind("1")
    if pos < 1 or pos + 7 > len(address):
        return None
    hrp, data_part = address[:pos], address[pos + 1:]
    if any(ord(c) < 33 or ord(c) > 126 for c in hrp):
        return None
    if any(c not in _CHARSET for c in data_part):
        return None
    data = [_CHARSET.find(c) for c in data_part]
    const = _polymod(_hrp_expand(hrp) + data)
    witver = data[0]
    # v0 must use bech32; v1+ must use bech32m (BIP350).
    expected = _BECH32_CONST if witver == 0 else _BECH32M_CONST
    if const != expected:
        return None
    if witver > 16:
        return None
    program = _convertbits(data[1:-6], 5, 8, False)
    if program is None or not 2 <= len(program) <= 40:
        return None
    if witver == 0 and len(program) not in (20, 32):
        return None
    return hrp, witver, bytes(program)


def _encode_p2wpkh(hrp, program20):
    data = [0] + _convertbits(program20, 8, 5, True)
    pm = _polymod(_hrp_expand(hrp) + data + [0] * 6) ^ _BECH32_CONST
    checksum = [(pm >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(_CHARSET[d] for d in data + checksum)


def is_valid_donation_address(address):
    """True only for a mainnet P2WPKH (``bc1q...``, 20-byte program) address.

    Deliberately narrower than "any valid Bitcoin address": Bookworm's
    donation wallet is native SegWit, so anything else is a mistake.
    """
    decoded = decode_segwit_address(address)
    if decoded is None:
        return False
    hrp, witver, program = decoded
    return hrp == "bc" and witver == 0 and len(program) == 20 and address == address.lower()


# =============================================================================
# secp256k1 public-key recovery, for BIP137 signed messages
# =============================================================================

_P = 2**256 - 2**32 - 977
_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_G = (
    0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
    0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
)


def _point_add(a, b):
    if a is None:
        return b
    if b is None:
        return a
    if a[0] == b[0] and (a[1] + b[1]) % _P == 0:
        return None
    if a == b:
        lam = 3 * a[0] * a[0] * pow(2 * a[1], _P - 2, _P) % _P
    else:
        lam = (b[1] - a[1]) * pow(b[0] - a[0], _P - 2, _P) % _P
    x = (lam * lam - a[0] - b[0]) % _P
    return x, (lam * (a[0] - x) - a[1]) % _P


def _point_mul(k, point):
    result = None
    while k:
        if k & 1:
            result = _point_add(result, point)
        point = _point_add(point, point)
        k >>= 1
    return result


def _message_hash(message):
    payload = message.encode("utf-8")
    n = len(payload)
    if n < 0xFD:
        varint = bytes([n])
    elif n <= 0xFFFF:
        varint = b"\xfd" + n.to_bytes(2, "little")
    else:
        varint = b"\xfe" + n.to_bytes(4, "little")
    blob = b"\x18Bitcoin Signed Message:\n" + varint + payload
    return hashlib.sha256(hashlib.sha256(blob).digest()).digest()


def _recover_pubkey(msg_hash, r, s, recid):
    x = r + (recid // 2) * _N
    if x >= _P:
        return None
    y_sq = (pow(x, 3, _P) + 7) % _P
    y = pow(y_sq, (_P + 1) // 4, _P)
    if (y * y) % _P != y_sq:
        return None
    if y % 2 != recid % 2:
        y = _P - y
    e = int.from_bytes(msg_hash, "big")
    r_inv = pow(r, _N - 2, _N)
    q = _point_mul(r_inv, _point_add(_point_mul(s, (x, y)), _point_mul((-e) % _N, _G)))
    return q


def verify_message_signature(address, message, signature_b64):
    """
    Verify a BIP137 signed message for a P2WPKH address.

    Accepts the BIP137 native-SegWit headers (39-42), which is what Sparrow
    produces in BIP137 mode, and the compressed-key headers (31-34), which is
    what Electrum-format signatures use for SegWit addresses. In both cases
    the recovered compressed public key must hash to ``address``.
    """
    if not is_valid_donation_address(address):
        return False
    try:
        raw = base64.b64decode(signature_b64, validate=True)
    except (ValueError, TypeError):
        return False
    if len(raw) != 65:
        return False
    header = raw[0]
    if not (31 <= header <= 34 or 39 <= header <= 42):
        return False
    recid = (header - 27) & 3
    r = int.from_bytes(raw[1:33], "big")
    s = int.from_bytes(raw[33:], "big")
    if not (0 < r < _N and 0 < s < _N):
        return False
    q = _recover_pubkey(_message_hash(message), r, s, recid)
    if q is None:
        return False
    compressed = bytes([2 + (q[1] & 1)]) + q[0].to_bytes(32, "big")
    h160 = hashlib.new("ripemd160", hashlib.sha256(compressed).digest()).digest()
    return _encode_p2wpkh("bc", h160) == address


# =============================================================================
# Resolved configuration
# =============================================================================

@lru_cache(maxsize=8)
def _verified_address(address, message, signature):
    """Cached per distinct (address, message, signature): the EC maths runs
    once per process, not once per request."""
    if not address:
        return ""
    if not is_valid_donation_address(address):
        logger.error("BITCOIN_ADDRESS is not a valid mainnet bc1q address; Bitcoin option hidden.")
        return ""
    if address not in message:
        logger.error("BITCOIN_SIGNED_MESSAGE does not contain BITCOIN_ADDRESS; Bitcoin option hidden.")
        return ""
    if not verify_message_signature(address, message, signature):
        logger.error("BITCOIN_SIGNATURE does not verify for BITCOIN_ADDRESS; Bitcoin option hidden.")
        return ""
    return address


def bitcoin_address():
    """The donation address if, and only if, it is valid and proven. Else ''."""
    return _verified_address(
        getattr(settings, "BITCOIN_ADDRESS", ""),
        getattr(settings, "BITCOIN_SIGNED_MESSAGE", ""),
        getattr(settings, "BITCOIN_SIGNATURE", ""),
    )


def address_groups(address, size=4):
    """Split an address into fixed-size groups for human checking."""
    return [address[i:i + size] for i in range(0, len(address), size)]


@lru_cache(maxsize=8)
def bitcoin_qr_svg(address):
    """
    Inline SVG QR code for a BIP21 ``bitcoin:`` URI.

    Generated on the server from the same verified constant the text comes
    from, so the QR and the printed address cannot diverge. Inline SVG needs
    no img-src entry and no JavaScript.
    """
    import segno  # local import: only the support page needs it

    qr = segno.make(f"bitcoin:{address}", error="m")
    return qr.svg_inline(
        scale=4,
        dark="#1c1917",
        light="#ffffff",
        title="QR code for Bookworm's Bitcoin donation address",
        svgclass="btc-qr",
        lineclass=None,
        omitsize=True,
    )
