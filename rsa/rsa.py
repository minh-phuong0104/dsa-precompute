import hashlib
from dataclasses import dataclass

from core.modarith import modexp, modinv

SHA256_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


@dataclass
class RSAKey:
    n: int
    e: int
    d: int
    p: int
    q: int

    def __post_init__(self):
        self.dp = self.d % (self.p - 1)
        self.dq = self.d % (self.q - 1)
        self.qinv = modinv(self.q, self.p)
        self.k = (self.n.bit_length() + 7) // 8


def emsa_pkcs1_v15(msg: bytes, k: int) -> int:
    t = SHA256_PREFIX + hashlib.sha256(msg).digest()
    if k < len(t) + 11:
        raise ValueError("modulo quá ngắn")
    em = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    return int.from_bytes(em, "big")


def sign(key: RSAKey, msg: bytes, crt=False, expfn=modexp) -> bytes:
    m = emsa_pkcs1_v15(msg, key.k)
    if crt:
        s1 = expfn(m % key.p, key.dp, key.p)
        s2 = expfn(m % key.q, key.dq, key.q)
        h = key.qinv * (s1 - s2) % key.p
        s = s2 + h * key.q
    else:
        s = expfn(m, key.d, key.n)
    return s.to_bytes(key.k, "big")


def verify(key: RSAKey, msg: bytes, sig: bytes, expfn=modexp) -> bool:
    if len(sig) != key.k:
        return False
    s = int.from_bytes(sig, "big")
    if s >= key.n:
        return False
    return expfn(s, key.e, key.n) == emsa_pkcs1_v15(msg, key.k)
