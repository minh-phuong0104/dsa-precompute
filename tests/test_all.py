import secrets
import threading
import unittest

from core.keystore import load
from core.modarith import batch_inv, modexp, modinv
from dsa import dsa as D
from dsa.fixed_base import CombLimLee, FixedBaseWindow
from rsa import rsa as R

DSA_KEYS, RSA_KEYS, _ = load()


class TestArith(unittest.TestCase):
    def test_modexp_matches_pow(self):
        for _ in range(200):
            m = secrets.randbits(2048) | 1
            b, e = secrets.randbits(2048), secrets.randbits(300)
            self.assertEqual(modexp(b, e, m), pow(b, e, m))

    def test_modinv_and_batch(self):
        q = DSA_KEYS["2048"].params.q
        xs = [secrets.randbelow(q - 1) + 1 for _ in range(500)]
        invs = batch_inv(xs, q)
        for x, i in zip(xs, invs):
            self.assertEqual(x * i % q, 1)
            self.assertEqual(i, modinv(x, q))


class TestFixedBase(unittest.TestCase):
    def test_window_and_comb_match_pow_1000_random_k(self):
        for lvl in ("2048", "3072"):
            P = DSA_KEYS[lvl].params
            for w in range(2, 9):
                win, comb = FixedBaseWindow(P.g, P.p, P.N, w), CombLimLee(P.g, P.p, P.N, w)
                for _ in range(1000 if w == 6 else 60):
                    k = secrets.randbelow(P.q)
                    ref = pow(P.g, k, P.p)
                    self.assertEqual(win.pow(k), ref)
                    self.assertEqual(comb.pow(k), ref)


def all_signers(key):
    v0 = D.BaselineSigner(key)
    comb = D.FixedBaseSigner(key, "comb", 8)
    v1 = D.PoolSigner(key, v0, capacity=50, name="V1")
    v4 = D.PoolSigner(key, comb, batch_inverse=True, capacity=50, name="V4")
    v1.pool.fill()
    v4.pool.fill()
    return [v0, D.BaselineSigner(key, expfn=pow), D.FixedBaseSigner(key, "window", 6), comb, v1, v4]


class TestDSA(unittest.TestCase):
    def test_sign_verify_all_variants(self):
        for lvl, key in DSA_KEYS.items():
            for s in all_signers(key):
                for i in range(30):
                    msg = f"msg {lvl} {s.name} {i}".encode()
                    sig = s.sign(msg)
                    self.assertTrue(D.verify(key, msg, sig), s.name)
                    self.assertFalse(D.verify(key, msg + b"x", sig), s.name)
                    self.assertFalse(D.verify(key, msg, (sig[0], (sig[1] + 1) % key.params.q)), s.name)

    def test_cross_check_pycryptodome(self):
        from Crypto.Hash import SHA256
        from Crypto.PublicKey import DSA
        from Crypto.Signature import DSS

        for lvl, key in DSA_KEYS.items():
            P = key.params
            ck = DSA.construct((key.y, P.g, P.p, P.q, key.x))
            nb = (P.N + 7) // 8
            for s in all_signers(key):
                msg = f"cross {lvl} {s.name}".encode()
                r, ss = s.sign(msg)
                DSS.new(ck, "fips-186-3").verify(
                    SHA256.new(msg), r.to_bytes(nb, "big") + ss.to_bytes(nb, "big")
                )

            msg = b"from pycryptodome"
            sig = DSS.new(ck, "fips-186-3").sign(SHA256.new(msg))
            self.assertTrue(
                D.verify(key, msg, (int.from_bytes(sig[:nb], "big"), int.from_bytes(sig[nb:], "big")))
            )


class TestPool(unittest.TestCase):
    def test_no_k_issued_twice_under_threads(self):
        key = DSA_KEYS["2048"]
        signer = D.PoolSigner(
            key, D.FixedBaseSigner(key, "comb", 8), batch_inverse=True, capacity=2000, name="V4"
        )
        signer.pool.fill()
        taken, lock = [], threading.Lock()

        def worker():
            while True:
                t = signer.pool.take()
                if t is None:
                    return
                with lock:
                    taken.append(t[0])

        ths = [threading.Thread(target=worker) for _ in range(8)]
        [t.start() for t in ths]
        [t.join() for t in ths]
        self.assertEqual(len(taken), 2000)
        self.assertEqual(len(set(taken)), 2000, "pool đã cấp trùng k")
        self.assertEqual(len(signer.pool), 0)

    def test_fallback_when_empty(self):
        key = DSA_KEYS["2048"]
        signer = D.PoolSigner(key, D.BaselineSigner(key), capacity=3)
        signer.pool.fill()
        for i in range(6):
            self.assertTrue(D.verify(key, b"m%d" % i, signer.sign(b"m%d" % i)))
        self.assertEqual(signer.fallbacks, 3)

    def test_triples_consistent(self):
        key = DSA_KEYS["3072"]
        P = key.params
        s = D.PoolSigner(
            key, D.FixedBaseSigner(key, "window", 6), batch_inverse=True, capacity=100, name="V4"
        )
        s.pool.fill()
        while (t := s.pool.take()) is not None:
            k, kinv, r = t
            self.assertEqual(k * kinv % P.q, 1)
            self.assertEqual(pow(P.g, k, P.p) % P.q, r)

    def test_background_fill(self):
        import time

        key = DSA_KEYS["2048"]
        signer = D.PoolSigner(
            key, D.FixedBaseSigner(key, "comb", 8), batch_inverse=True, capacity=64, name="V4"
        )
        signer.pool.start_background(low_water=0.5, batch=16)
        deadline = time.time() + 20
        while len(signer.pool) < 32 and time.time() < deadline:
            time.sleep(0.01)
        signer.pool.stop_background()
        self.assertGreaterEqual(len(signer.pool), 32)
        for i in range(10):
            m = b"bg %d" % i
            self.assertTrue(D.verify(key, m, signer.sign(m)))
        self.assertEqual(signer.fallbacks, 0)


class TestRSA(unittest.TestCase):
    def test_sign_verify_and_crt(self):
        for lvl, key in RSA_KEYS.items():
            for i in range(5):
                msg = b"rsa %d" % i
                a, b = R.sign(key, msg), R.sign(key, msg, crt=True)
                self.assertEqual(a, b)
                self.assertTrue(R.verify(key, msg, a))
                self.assertFalse(R.verify(key, msg + b"!", a))

    def test_cross_check_pycryptodome(self):
        from Crypto.Hash import SHA256
        from Crypto.PublicKey import RSA as CR
        from Crypto.Signature import pkcs1_15

        for lvl, key in RSA_KEYS.items():
            ck = CR.construct((key.n, key.e, key.d, key.p, key.q))
            msg = b"cross rsa " + lvl.encode()
            self.assertEqual(R.sign(key, msg, crt=True), pkcs1_15.new(ck).sign(SHA256.new(msg)))
            pkcs1_15.new(ck).verify(SHA256.new(msg), R.sign(key, msg))


if __name__ == "__main__":
    unittest.main(verbosity=2)
