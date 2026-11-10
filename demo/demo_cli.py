
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
    ap.add_argument(
        "--msg",
        default="Transfer 5,000,000 VND to account A"
    )
    a = ap.parse_args()

    dk, rk, _ = load()
    key, rkey, msg = dk[a.level], rk[a.level], a.msg.encode()
    P = key.params

    print("=" * 70)
    print("DSA SIGNATURE OPTIMIZATION - PROJECT DEMONSTRATION")
    print("=" * 70)

    print(
        f"Key size: DSA (L={P.L}, N={P.N}) "
        f"vs RSA-{rkey.n.bit_length()}"
    )
    print(f"Message: {a.msg!r}\n")

    v0 = D.BaselineSigner(key)

    print("[Offline] Building fixed-base tables and filling pools...")

    t = time.perf_counter()

    win = D.FixedBaseSigner(key, "window", 8)
    comb = D.FixedBaseSigner(key, "comb", 8)

    v1 = D.PoolSigner(key, v0, capacity=200, name="V1")

    v4 = D.PoolSigner(
        key,
        comb,
        batch_inverse=True,
        capacity=200,
        name="V4"
    )

    v1.pool.fill()
    v4.pool.fill()

    print(
        f"Completed in {time.perf_counter() - t:.1f} seconds "
        f"(Window table: {win.engine.table_bytes / 1024:.0f} KB, "
        f"Comb table: {comb.engine.table_bytes / 1024:.0f} KB, "
        f"2 pools with 200 entries each)\n"
    )

    rows = []

    for name, s in [
        ("V0 Baseline", v0),
        ("V2 Window w=8", win),
        ("V3 Comb h=8", comb),
        ("V1 Pool (Online)", v1),
        ("V4 Pool (Online)", v4),
    ]:
        sig, us = timed(lambda: s.sign(msg))
        rows.append((name, us, D.verify(key, msg, sig)))

    sig, us = timed(lambda: R.sign(rkey, msg), n=3)
    rows.append(("RSA R0", us, R.verify(rkey, msg, sig)))

    sig, us = timed(
        lambda: R.sign(rkey, msg, crt=True),
        n=5
    )
    rows.append(("RSA R1 CRT", us, R.verify(rkey, msg, sig)))

    base = rows[0][1]

    print("=" * 75)
    print("SIGNING PERFORMANCE COMPARISON")
    print("=" * 75)

    print(
        f"{'Variant':<22}"
        f"{'Signing (us)':>15}"
        f"{'vs V0':>12}"
        f"{'Verification':>17}"
    )

    print("-" * 75)

    for name, us, ok in rows:
        status = "VALID" if ok else "INVALID"

        print(
            f"{name:<22}"
            f"{us:>15,.1f}"
            f"{base / us:>11.1f}x"
            f"{status:>17}"
        )

    print("-" * 75)

    r, s = v4.sign(msg)

    print("\nDIGITAL SIGNATURE DETAILS")
    print("-" * 75)

    print(
        f"DSA Signature: r={hex(r)[:22]}... "
        f"s={hex(s)[:22]}... "
        f"({2 * ((P.N + 7) // 8)} bytes)"
    )

    print(f"RSA Signature: {rkey.k} bytes")

    tampered = msg + b"0"

    is_valid = D.verify(key, tampered, (r, s))

    print("\nMESSAGE INTEGRITY TEST")
    print("-" * 75)

    print(f"Modified message: {tampered.decode()!r}")
    print(
        f"DSA verification result: "
        f"{'VALID' if is_valid else 'INVALID'}"
    )

    print("\nDemo completed successfully.")


if __name__ == "__main__":
    main()
