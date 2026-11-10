import json
import os
import time

from core.primes import gen_dsa_params, gen_rsa_key

PATH = os.path.join(os.path.dirname(__file__), "params.json")
LEVELS = {"2048": (2048, 224), "3072": (3072, 256)}


def generate(path=PATH):
    from dsa.dsa import DSAParams, keygen

    data = {"dsa": {}, "rsa": {}, "gen_seconds": {}}
    for lvl, (L, N) in LEVELS.items():
        t = time.perf_counter()
        p, q, g = gen_dsa_params(L, N)
        k = keygen(DSAParams(p, q, g), expfn=pow)
        data["gen_seconds"][f"dsa_params_{lvl}"] = time.perf_counter() - t
        data["dsa"][lvl] = {"p": hex(p), "q": hex(q), "g": hex(g), "x": hex(k.x), "y": hex(k.y)}
        t = time.perf_counter()
        n, e, d, pp, qq = gen_rsa_key(L)
        data["gen_seconds"][f"rsa_key_{lvl}"] = time.perf_counter() - t
        data["rsa"][lvl] = {"n": hex(n), "e": e, "d": hex(d), "p": hex(pp), "q": hex(qq)}
        print(
            f"level {lvl}: DSA {data['gen_seconds'][f'dsa_params_{lvl}']:.1f}s, "
            f"RSA {data['gen_seconds'][f'rsa_key_{lvl}']:.1f}s",
            flush=True,
        )
    with open(path, "w") as f:
        json.dump(data, f, indent=1)
    return data


def load(path=PATH):
    from dsa.dsa import DSAKey, DSAParams
    from rsa.rsa import RSAKey

    if not os.path.exists(path):
        generate(path)
    with open(path) as f:
        data = json.load(f)
    H = lambda s: int(s, 16)
    dsa_keys, rsa_keys = {}, {}
    for lvl, d in data["dsa"].items():
        P = DSAParams(H(d["p"]), H(d["q"]), H(d["g"]))
        dsa_keys[lvl] = DSAKey(P, H(d["x"]), H(d["y"]))
    for lvl, r in data["rsa"].items():
        rsa_keys[lvl] = RSAKey(H(r["n"]), r["e"], H(r["d"]), H(r["p"]), H(r["q"]))
    return dsa_keys, rsa_keys, data.get("gen_seconds", {})


if __name__ == "__main__":
    generate()
