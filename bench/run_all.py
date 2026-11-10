import secrets
import sys
import time

from bench.harness import env_info, measure, write_csv
from core.keystore import load
from core.modarith import modexp
from core.primes import gen_rsa_key
from dsa import dsa as D
from rsa import rsa as R

DK, RK, GEN = load()
LEVELS = ("2048", "3072")
W_BEST = 8
MSG = b"Benchmark message for DSA precomputation"


def msgs():
    i = 0
    while True:
        i += 1
        yield b"msg-%d" % i


def checked(signer, key):
    out = []
    gen = msgs()

    def fn():
        m = next(gen)
        out.append((m, signer.sign(m)))

    return fn, out


def verify_all(key, out, sample=200):
    step = max(1, len(out) // sample)
    for m, sig in out[::step]:
        assert D.verify(key, m, sig, expfn=pow), "chữ ký không hợp lệ trong lúc đo!"
    return len(out[::step])


def e1():
    rows = []
    for lvl in LEVELS:
        key = DK[lvl]
        v0 = D.BaselineSigner(key)
        variants = [
            ("V0 baseline (modexp tự cài)", v0, None),
            ("V0 baseline (pow C có sẵn)", D.BaselineSigner(key, expfn=pow), None),
            (f"V2 fixed-base window (w={W_BEST})", D.FixedBaseSigner(key, "window", W_BEST), None),
            (f"V3 comb Lim-Lee (h={W_BEST})", D.FixedBaseSigner(key, "comb", W_BEST), None),
            ("V1 pool (online)", D.PoolSigner(key, v0, capacity=8000, name="V1"), "fill"),
            (
                f"V4 pool comb+batch inv (online)",
                D.PoolSigner(
                    key, D.FixedBaseSigner(key, "comb", W_BEST), batch_inverse=True, capacity=8000, name="V4"
                ),
                "fill",
            ),
        ]
        for label, signer, prep in variants:
            if prep:
                signer.pool.fill()
            fn, out = checked(signer, key)
            if prep:
                r = measure(fn, max_iter=1000, warmup=50)
                assert signer.fallbacks == 0
            else:
                r = measure(fn, budget_s=2.5, max_iter=1000)
            n = verify_all(key, out)
            rows.append({"level": lvl, "variant": label, **r, "verified_sigs": n})
            print(lvl, label, f"{r['median_us']:.1f} µs", flush=True)
    write_csv("e1_sign_latency.csv", rows)


def e2():
    rows = []
    for lvl in LEVELS:
        key = DK[lvl]
        for size in (100, 1000, 10000):
            fillers = [
                ("V1: modexp tự cài + Euclid từng k", D.BaselineSigner(key), False),
                (f"V4: comb h={W_BEST} + nghịch đảo hàng loạt", D.FixedBaseSigner(key, "comb", W_BEST), True),
                (
                    f"V4: window w={W_BEST} + nghịch đảo hàng loạt",
                    D.FixedBaseSigner(key, "window", W_BEST),
                    True,
                ),
            ]
            for label, filler, batch in fillers:
                times = []
                reps = 3 if size <= 1000 else 1
                for _ in range(reps):
                    s = D.PoolSigner(key, filler, batch_inverse=batch, capacity=size)
                    t = time.perf_counter_ns()
                    s.pool.fill()
                    dt = (time.perf_counter_ns() - t) / 1e9
                    assert len(s.pool) == size
                    times.append(dt)
                best = sorted(times)[len(times) // 2]
                rows.append(
                    {
                        "level": lvl,
                        "pool_size": size,
                        "filler": label,
                        "fill_seconds": best,
                        "us_per_triple": best / size * 1e6,
                        "runs": reps,
                    }
                )
                print(lvl, size, label, f"{best:.2f}s", flush=True)

    from core.modarith import batch_inv, modinv

    for lvl in LEVELS:
        q = DK[lvl].params.q
        ks = [secrets.randbelow(q - 1) + 1 for _ in range(1000)]
        a = measure(lambda: [modinv(k, q) for k in ks], max_iter=20, min_iter=10)
        b = measure(lambda: batch_inv(ks, q), max_iter=20, min_iter=10)
        rows.append(
            {
                "level": lvl,
                "pool_size": 1000,
                "filler": "chỉ nghịch đảo: Euclid từng k",
                "fill_seconds": a["median_us"] / 1e6,
                "us_per_triple": a["median_us"] / 1000,
                "runs": 5,
            }
        )
        rows.append(
            {
                "level": lvl,
                "pool_size": 1000,
                "filler": "chỉ nghịch đảo: hàng loạt",
                "fill_seconds": b["median_us"] / 1e6,
                "us_per_triple": b["median_us"] / 1000,
                "runs": 5,
            }
        )
    write_csv("e2_pool_fill.csv", rows)


def e3():
    from dsa.fixed_base import CombLimLee, FixedBaseWindow

    rows = []
    for lvl in LEVELS:
        P = DK[lvl].params
        ks = [secrets.randbelow(P.q) for _ in range(4096)]
        it = iter(ks * 1000)
        ref = measure(lambda: modexp(P.g, next(it), P.p), budget_s=1.5)
        rows.append(
            {
                "level": lvl,
                "method": "square-and-multiply (không bảng)",
                "w": 0,
                **ref,
                "table_entries": 0,
                "table_kb": 0,
                "build_ms": 0,
            }
        )
        refc = measure(lambda: pow(P.g, next(it), P.p), budget_s=1.5)
        rows.append(
            {
                "level": lvl,
                "method": "pow C có sẵn (không bảng)",
                "w": 0,
                **refc,
                "table_entries": 0,
                "table_kb": 0,
                "build_ms": 0,
            }
        )
        for w in range(2, 9):
            for name, cls in (("window", FixedBaseWindow), ("comb", CombLimLee)):
                t = time.perf_counter_ns()
                eng = cls(P.g, P.p, P.N, w)
                build = (time.perf_counter_ns() - t) / 1e6
                k0 = ks[0]
                assert eng.pow(k0) == pow(P.g, k0, P.p)
                r = measure(lambda: eng.pow(next(it)), budget_s=1.5)
                rows.append(
                    {
                        "level": lvl,
                        "method": name,
                        "w": w,
                        **r,
                        "table_entries": eng.entries,
                        "table_kb": eng.table_bytes / 1024,
                        "build_ms": build,
                    }
                )
                print(lvl, name, w, f"{r['median_us']:.0f} µs", f"{eng.table_bytes/1024:.0f} KB", flush=True)
    write_csv("e3_fixed_base.csv", rows)


def e4():
    rows = []
    for lvl in LEVELS:
        dk, rk = DK[lvl], RK[lvl]
        P = dk.params
        for impl, ef in (("tự cài", modexp), ("pow C", pow)):
            v0 = D.BaselineSigner(dk, expfn=ef)
            pool = D.PoolSigner(dk, D.FixedBaseSigner(dk, "comb", W_BEST), batch_inverse=True, capacity=8000)
            pool.pool.fill()
            dsig = v0.sign(MSG)
            rsig = R.sign(rk, MSG, crt=True)
            ops = [
                ("DSA V0", "sign", lambda: v0.sign(MSG)),
                (
                    f"DSA V2 window w={W_BEST}",
                    "sign",
                    (lambda s=D.FixedBaseSigner(dk, "window", W_BEST): s.sign(MSG)),
                ),
                ("DSA V4 pool (online)", "sign", lambda: pool.sign(MSG)),
                ("DSA", "verify", lambda: D.verify(dk, MSG, dsig, expfn=ef)),
                ("RSA R0", "sign", lambda: R.sign(rk, MSG, expfn=ef)),
                ("RSA R1 CRT", "sign", lambda: R.sign(rk, MSG, crt=True, expfn=ef)),
                ("RSA", "verify", lambda: R.verify(rk, MSG, rsig, expfn=ef)),
            ]
            for scheme, op, fn in ops:
                if "pool" in scheme:
                    r = measure(fn, max_iter=1000, warmup=50)
                else:
                    r = measure(fn, budget_s=2.5, max_iter=1000, min_iter=20)
                rows.append({"level": lvl, "impl": impl, "scheme": scheme, "op": op, **r})
                print(lvl, impl, scheme, op, f"{r['median_us']:.0f} µs", flush=True)

        r = measure(lambda: D.keygen(P), budget_s=1.0, max_iter=200, min_iter=20)
        rows.append(
            {"level": lvl, "impl": "tự cài", "scheme": "DSA", "op": "keygen (x, y; p,q,g dùng chung)", **r}
        )
        n_rsa = 10 if lvl == "2048" else 4
        ts = []
        for _ in range(n_rsa):
            t = time.perf_counter_ns()
            gen_rsa_key(int(lvl))
            ts.append((time.perf_counter_ns() - t) / 1000)
        ts.sort()
        rows.append(
            {
                "level": lvl,
                "impl": "tự cài",
                "scheme": "RSA",
                "op": "keygen (n, e, d)",
                "median_us": ts[len(ts) // 2],
                "p95_us": ts[-1],
                "mean_us": sum(ts) / len(ts),
                "iters_per_rep": n_rsa,
                "repeats": 1,
            }
        )
        rows.append(
            {
                "level": lvl,
                "impl": "tự cài",
                "scheme": "DSA",
                "op": "sinh tham số p,q,g (1 lần)",
                "median_us": GEN.get(f"dsa_params_{lvl}", 0) * 1e6,
                "iters_per_rep": 1,
                "repeats": 1,
            }
        )

        nb = (P.N + 7) // 8
        rows.append(
            {
                "level": lvl,
                "impl": "-",
                "scheme": "DSA",
                "op": "kích thước chữ ký (byte)",
                "median_us": 2 * nb,
            }
        )
        rows.append(
            {"level": lvl, "impl": "-", "scheme": "RSA", "op": "kích thước chữ ký (byte)", "median_us": rk.k}
        )
        rows.append(
            {
                "level": lvl,
                "impl": "-",
                "scheme": "DSA",
                "op": "khóa công khai y (byte)",
                "median_us": (P.p.bit_length() + 7) // 8,
            }
        )
        rows.append(
            {"level": lvl, "impl": "-", "scheme": "RSA", "op": "khóa công khai n (byte)", "median_us": rk.k}
        )
    write_csv("e4_dsa_vs_rsa.csv", rows)


def e5():
    rows = []
    BURST = 2000
    for lvl in LEVELS:
        key = DK[lvl]
        comb = D.FixedBaseSigner(key, "comb", W_BEST)
        cases = [
            ("V0 baseline", lambda: D.BaselineSigner(key), None),
            (f"V3 comb h={W_BEST} (không pool)", lambda: comb, None),
            ("V4 pool đầy (2000)", lambda: D.PoolSigner(key, comb, batch_inverse=True, capacity=2000), 2000),
            (
                "V4 pool một nửa (1000)",
                lambda: D.PoolSigner(key, comb, batch_inverse=True, capacity=1000),
                1000,
            ),
            ("V4 pool rỗng", lambda: D.PoolSigner(key, comb, batch_inverse=True, capacity=1), 0),
        ]
        for label, make, prefill in cases:
            vals = []
            for _ in range(3):
                s = make()
                if prefill:
                    s.pool.fill()
                elif prefill == 0:
                    pass
                t = time.perf_counter_ns()
                sigs = [s.sign(b"burst-%d" % i) for i in range(BURST)]
                dt = (time.perf_counter_ns() - t) / 1e9
                vals.append(BURST / dt)
            for i in range(0, BURST, 97):
                assert D.verify(key, b"burst-%d" % i, sigs[i], expfn=pow)
            vals.sort()
            fb = getattr(s, "fallbacks", "")
            rows.append(
                {
                    "level": lvl,
                    "case": label,
                    "burst": BURST,
                    "sigs_per_sec": vals[1],
                    "min": vals[0],
                    "max": vals[2],
                    "fallbacks_last_run": fb,
                }
            )
            print(lvl, label, f"{vals[1]:.0f} sig/s", flush=True)
    write_csv("e5_burst.csv", rows)


if __name__ == "__main__":
    print(env_info())
    todo = sys.argv[1:] or ["e1", "e2", "e3", "e4", "e5"]
    for name in todo:
        t = time.time()
        globals()[name]()
        print(f"== {name} xong trong {time.time() - t:.0f}s", flush=True)
