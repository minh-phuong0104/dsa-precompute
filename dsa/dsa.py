import hashlib
import secrets
from dataclasses import dataclass

from core.modarith import modexp, modinv
from dsa.fixed_base import CombLimLee, FixedBaseWindow
from dsa.pool import PrecomputePool


@dataclass
class DSAParams:
    p: int
    q: int
    g: int

    @property
    def L(self):
        return self.p.bit_length()

    @property
    def N(self):
        return self.q.bit_length()


@dataclass
class DSAKey:
    params: DSAParams
    x: int
    y: int


def keygen(params: DSAParams, expfn=modexp) -> DSAKey:
    x = secrets.randbelow(params.q - 1) + 1
    return DSAKey(params, x, expfn(params.g, x, params.p))


def hash_to_int(msg: bytes, N: int) -> int:
    digest = hashlib.sha256(msg).digest()
    z = int.from_bytes(digest, "big")
    if len(digest) * 8 > N:
        z >>= len(digest) * 8 - N
    return z


def verify(key: DSAKey, msg: bytes, sig, expfn=modexp) -> bool:
    p, q, g = key.params.p, key.params.q, key.params.g
    r, s = sig
    if not (0 < r < q and 0 < s < q):
        return False
    w = modinv(s, q)
    z = hash_to_int(msg, key.params.N)
    u1, u2 = z * w % q, r * w % q
    v = expfn(g, u1, p) * expfn(key.y, u2, p) % p % q
    return v == r


def _finish(key: DSAKey, msg: bytes, k_inv: int, r: int):
    q = key.params.q
    z = hash_to_int(msg, key.params.N)
    return r, k_inv * (z + key.x * r) % q


class Signer:
    name = "?"

    def __init__(self, key: DSAKey):
        self.key = key

    def fresh_triple(self):
        raise NotImplementedError

    def sign(self, msg: bytes):
        while True:
            k, k_inv, r = self.fresh_triple()
            if r == 0:
                continue
            r_, s = _finish(self.key, msg, k_inv, r)
            if s != 0:
                return r_, s


class BaselineSigner(Signer):
    name = "V0"

    def __init__(self, key, expfn=modexp):
        super().__init__(key)
        self.expfn = expfn

    def fresh_triple(self):
        P = self.key.params
        k = secrets.randbelow(P.q - 1) + 1
        return k, modinv(k, P.q), self.expfn(P.g, k, P.p) % P.q


class FixedBaseSigner(Signer):
    def __init__(self, key, kind="window", w=6):
        super().__init__(key)
        P = key.params
        cls = FixedBaseWindow if kind == "window" else CombLimLee
        self.engine = cls(P.g, P.p, P.N, w)
        self.name = ("V2" if kind == "window" else "V3") + f"(w={w})"

    def fresh_triple(self):
        P = self.key.params
        k = secrets.randbelow(P.q - 1) + 1
        return k, modinv(k, P.q), self.engine.pow(k) % P.q


class PoolSigner(Signer):
    def __init__(self, key, filler: Signer, batch_inverse=False, capacity=1000, name="V1"):
        super().__init__(key)
        self.filler = filler
        self.name = name
        self.pool = PrecomputePool(key.params, filler, batch_inverse=batch_inverse, capacity=capacity)
        self.fallbacks = 0

    def fresh_triple(self):
        t = self.pool.take()
        if t is None:
            self.fallbacks += 1
            return self.filler.fresh_triple()
        return t
