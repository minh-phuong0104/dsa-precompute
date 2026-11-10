import argparse
import time

from core.keystore import load
from dsa import dsa as D
from rsa import rsa as R


def timed(fn, n=20):
    t = time.perf_counter_ns()
    for _ in range(n):
        out = fn()
    return out, (time.perf_counter_ns() - t) / n / 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", default="2048", choices=["2048", "3072"])
    ap.add_argument("--msg", default="Chuyển 5.000.000 VND cho tài khoản A")
    a = ap.parse_args()
    dk, rk, _ = load()
    key, rkey, msg = dk[a.level], rk[a.level], a.msg.encode()
    P = key.params
    print(f"Mức bảo mật: DSA (L={P.L}, N={P.N})  vs  RSA-{rkey.n.bit_length()}")
    print(f"Thông điệp : {a.msg!r}\n")

    v0 = D.BaselineSigner(key)
    print("[Offline] dựng bảng fixed-base và lấp pool...")
    t = time.perf_counter()
    win = D.FixedBaseSigner(key, "window", 8)
    comb = D.FixedBaseSigner(key, "comb", 8)
    v1 = D.PoolSigner(key, v0, capacity=200, name="V1")
    v4 = D.PoolSigner(key, comb, batch_inverse=True, capacity=200, name="V4")
    v1.pool.fill()
    v4.pool.fill()
    print(
        f"          xong sau {time.perf_counter() - t:.1f} s (bảng window {win.engine.table_bytes/1024:.0f} KB, "
        f"comb {comb.engine.table_bytes/1024:.0f} KB, 2 pool x 200 bộ)\n"
    )

    rows = []
    for name, s in [
        ("V0 baseline", v0),
        ("V2 window w=8", win),
        ("V3 comb h=8", comb),
        ("V1 pool (online)", v1),
        ("V4 pool (online)", v4),
    ]:
        sig, us = timed(lambda: s.sign(msg))
        rows.append((name, us, D.verify(key, msg, sig)))
    sig, us = timed(lambda: R.sign(rkey, msg), n=3)
    rows.append(("RSA R0", us, R.verify(rkey, msg, sig)))
    sig, us = timed(lambda: R.sign(rkey, msg, crt=True), n=5)
    rows.append(("RSA R1 CRT", us, R.verify(rkey, msg, sig)))

    base = rows[0][1]
    print(f"{'Biến thể':<20}{'Ký (µs)':>12}{'So với V0':>12}   Xác minh")
    for name, us, ok in rows:
        print(f"{name:<20}{us:>12,.1f}{base / us:>11.1f}x   {'HỢP LỆ' if ok else 'SAI'}")

    r, s = v4.sign(msg)
    print(f"\nChữ ký DSA: r={hex(r)[:22]}...  s={hex(s)[:22]}...  ({2 * ((P.N + 7) // 8)} byte)")
    print(f"Chữ ký RSA: {rkey.k} byte")
    tampered = msg + b"0"
    print(f"Sửa thông điệp thành {tampered.decode()!r} -> xác minh DSA: {D.verify(key, tampered, (r, s))}")


if __name__ == "__main__":
    main()
