# Complete Project Explanation

**Project title:** Optimizing DSA Signature Performance Through Precomputation and Experimental Comparison with RSA

The code in this repository has no explanatory comments. This document serves as a detailed companion to the source code: it explains the idea, mathematical formulas, every file and major function, testing, benchmarking, and how to interpret the results.

## Table of Contents

1. Project Idea
2. Directory Structure and How to Run the Project
3. Mathematical Foundations (`core/`)
4. Basic DSA Implementation (`dsa/dsa.py`)
5. Optimization Techniques V1–V4 (`dsa/pool.py`, `dsa/fixed_base.py`)
6. RSA and RSA-CRT (`rsa/rsa.py`)
7. Testing (`tests/test_all.py`)
8. Performance Measurement (`bench/`)
9. Experimental Results
10. Security Analysis
11. Demo, `main.py`, and Docker
12. Quick Function Reference
13. References

---

## 1. Project Idea

A DSA signature consists of two numbers, `(r, s)`:

```text
r = (g^k mod p) mod q            independent of the message; expensive
                                (modular exponentiation modulo a 2048–3072-bit p)

s = k⁻¹ · (H(m) + x·r) mod q     depends on the message; inexpensive
                                (a few modular multiplications modulo a 224–256-bit q)
```

Most of the cost comes from `g^k mod p`, which can be computed **before the message arrives**. This project explores that observation in two main ways and then combines them:

| Approach | How it works | Variant |
| --- | --- | --- |
| Move calculations earlier | Prepare a `(k, k⁻¹, r)` triple while the system is idle and store it in a pool | V1 |
| Make calculations cheaper | Because `g` is fixed, build a table of powers of `g` once, then use table lookups | V2 (window), V3 (comb) |
| Combine both ideas | Fill the pool using fixed-base tables and batch inversion | V4 |

RSA is used as a comparison baseline (R0 and R1). The encoded message appears in the signing calculation `s = m^d mod n`, which limits the kind of precomputation used for DSA. RSA-CRT precomputes `dp`, `dq`, and `qinv` for reuse when signing.

The DSA and RSA algorithms are implemented in Python. The project uses the following supporting tools:

- **PyCryptodome:** used only in tests to independently check that the generated signatures are compatible with the standard.
- **Python's built-in `pow()` (implemented in C):** used as a performance reference, to check results, and to speed up parameter and key generation.
- **Matplotlib:** generates charts from the benchmark CSV files.

---

## 2. Directory Structure and How to Run the Project

```text
dsa-precompute/
├── main.py              Common entry point: params | test | demo | bench | plots | all
├── requirements.txt     pycryptodome, matplotlib
├── Dockerfile           Docker packaging
├── README.md            Short usage guide
├── EXPLAIN.md           Detailed project explanation
├── core/
│   ├── modarith.py      Modular exponentiation, extended Euclid, modular/batch inverses
│   ├── primes.py        Miller–Rabin, prime generation, DSA parameters, RSA keys
│   ├── keystore.py      Generate once and reload parameters/keys from params.json
│   └── params.json      Shared TEST parameters and keys used by all benchmarks
├── dsa/
│   ├── dsa.py           DSA parameters, keys, signing, verification, V0–V4 signers
│   ├── pool.py          PrecomputePool: stores (k, k⁻¹, r) triples
│   └── fixed_base.py    FixedBaseWindow (V2) and CombLimLee (V3)
├── rsa/
│   └── rsa.py           RSA PKCS#1 v1.5: standard signing (R0), CRT signing (R1), verification
├── tests/
│   └── test_all.py      11 correctness tests
├── bench/
│   ├── harness.py       Shared measurement functions, CSV output, environment details
│   ├── run_all.py       Five experiments, E1–E5
│   ├── plots.py         Generate charts
│   ├── results/         Benchmark CSVs and env.json
│   └── plots/           Five PNG charts
└── demo/
    └── demo_cli.py      Command-line demonstration
```

### How to Run

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py test
python main.py demo
python main.py bench
python main.py plots
```

See [README.md](README.md) for selected benchmarks, the 3072-bit demo, and the `all` command. Run times depend on the machine. The repository includes test keys. Running `python main.py params` overwrites them. Rerun the benchmarks and regenerate the charts if you change the keys or parameters.

With Docker:

```bash
docker build -t dsa-precompute .
docker run --rm dsa-precompute demo
docker run --rm dsa-precompute test
```

Python 3.8 or later is required. All commands must be run from the repository root.

---

## 3. Mathematical Foundations (`core/`)

### 3.1 Modular Exponentiation — `modexp(base, exp, mod)`

This function uses the **square-and-multiply** algorithm, processing the exponent's bits from most significant to least significant:

```text
result = 1
for each bit b of exp (from left to right):
    result = result² mod m
    if b == 1:
        result = result · base mod m
```

**Why it works:** after processing a prefix `e'` of the exponent, `result = base^e'`. Appending the next bit `b` changes the exponent prefix to `2e' + b`, so the algorithm squares the current value and, if `b = 1`, multiplies by `base`.

**Cost:** for a `t`-bit exponent, about `t` squarings and an average of `t/2` additional multiplications, or approximately **1.5t modular multiplications**.

| Operation | Exponent | Approximate multiplications at the 2048-bit level |
| --- | --- | ---: |
| DSA signing | `k`, 224 bits | 336 |
| DSA verification | `u₁` and `u₂`, each 224 bits | 672 |
| RSA R0 signing | `d`, 2048 bits | 3,072 |
| RSA verification | `e = 65537`, 17 bits with two set bits | 19 in the current implementation |

This table helps explain two benchmark results: DSA signing is faster than standard RSA signing because its exponent is much shorter; RSA verification is faster than DSA verification because the public exponent `e` is small.

The implementation also handles two edge cases: if `mod == 1`, it returns `0`; for a negative exponent, it uses the modular inverse with the corresponding positive exponent.

### 3.2 Extended Euclidean Algorithm and Modular Inverse — `egcd`, `modinv`

`egcd(a, b)` returns `(g, x, y)` such that `a·x + b·y = g = gcd(a, b)`. The iterative algorithm updates the following values:

```text
(a, b)    <- (b, a mod b)
(x₀, x₁) <- (x₁, x₀ − floor(a/b)·x₁)
(y₀, y₁) <- (y₁, y₀ − floor(a/b)·y₁)
```

For `modinv(a, m)`, if `gcd(a, m) = 1`, then `a·x ≡ 1 (mod m)`, so `a⁻¹ = x mod m`. If the gcd is not 1, the inverse does not exist and the function raises an error.

### 3.3 Batch Inversion — `batch_inv(values, m)` (Montgomery Trick)

Suppose we need the inverses of `n` values `a₁, …, aₙ`. Instead of running the extended Euclidean algorithm `n` times, batch inversion runs it **only once**:

```text
Step 1 — Prefix products:
    c₁ = a₁
    cᵢ = cᵢ₋₁ · aᵢ (mod m)

Step 2 — One inverse:
    inv = cₙ⁻¹ (mod m)

Step 3 — Work backward, i = n, ..., 2:
    aᵢ⁻¹ = inv · cᵢ₋₁ (mod m)
    inv  = inv · aᵢ (mod m)   # Now inv = cᵢ₋₁⁻¹

Finally:
    a₁⁻¹ = inv
```

Step 3 is correct because `cᵢ⁻¹ · cᵢ₋₁ = (cᵢ₋₁ · aᵢ)⁻¹ · cᵢ₋₁ = aᵢ⁻¹`.

**Cost:** the algorithm needs one modular inversion and `3(n − 1)` modular multiplications. Our implementation starts with `acc = 1` and includes the first multiplication, so it performs `3n − 2` multiplications for `n > 0`. An empty input returns an empty list.

**Example:** compute the inverses of 7, 3, and 5 modulo 11.

| Step | Calculation | Result |
| --- | --- | --- |
| Prefix products | `7`; `7·3 = 21 ≡ 10`; `10·5 = 50 ≡ 6` | `c = (7, 10, 6)` |
| Invert once | `6⁻¹ mod 11` | `2`, since `6·2 = 12 ≡ 1` |
| `i = 3` | `5⁻¹ = 2·10 = 20 ≡ 9`; `inv = 2·5 ≡ 10` | `5·9 ≡ 1` |
| `i = 2` | `3⁻¹ = 10·7 = 70 ≡ 4`; `inv = 10·3 ≡ 8` | `3·4 ≡ 1` |
| `i = 1` | `7⁻¹ = 8` | `7·8 ≡ 1` |

### 3.4 Miller–Rabin Primality Test — `is_probable_prime(n, rounds)`

1. Reject small numbers and values divisible by any prime below 2,000 (the `SMALL_PRIMES` list).
2. Express `n − 1 = 2^s · d`, where `d` is odd.
3. In each round, choose a random `a` in `[2, n − 2]` and calculate `x = a^d mod n`. The round passes if `x = 1` or `x = n − 1`. Otherwise, repeatedly square `x`, at most `s − 1` times. If `n − 1` appears, the round passes; otherwise, `n` is composite.
4. A composite number passes `k` rounds with probability at most `4^(−k)`. The project uses 40 rounds for `q` and RSA primes and 20 rounds for DSA's `p`.

`random_prime(bits)` uses `secrets` to generate a random candidate, sets the highest bit so the required bit length is reached, sets the lowest bit to ensure an odd number, and repeats until a probable prime is found.

### 3.5 DSA Parameter Generation — `gen_dsa_params(L, N)`

```text
q = an N-bit prime
repeat:
    X = a random L-bit integer
    p = X − (X mod 2q) + 1   # p − 1 is divisible by 2q, so q divides p − 1
until p is prime and has exactly L bits

e = (p − 1) / q
g = h^e mod p for h = 2, 3, ... until g > 1
```

Since `g^q = h^(p−1) = 1 (mod p)` by Fermat's little theorem, and `q` is prime, a `g` different from 1 has order exactly `q`. The generated `p` has the required FIPS 186 mathematical structure, but the implementation does not provide a seed for independent verification of parameter generation.

### 3.6 RSA Key Generation — `gen_rsa_key(bits, e=65537)`

Generate distinct primes `p` and `q`, each approximately `bits/2` bits, such that `n = p·q` has exactly `bits` bits. Compute `φ = (p−1)(q−1)` and `d = e⁻¹ mod φ`. If `e` has no inverse modulo `φ`, generate a new pair of primes.

### 3.7 Key Store — `core/keystore.py`

- `LEVELS = {"2048": (2048, 224), "3072": (3072, 256)}`: two parameter levels corresponding to roughly 112-bit and 128-bit security, respectively, as discussed in NIST SP 800-57.
- `generate()`: generate DSA parameters, DSA keys, and RSA keys for both levels; save hexadecimal values and generation times to `params.json`.
- `load()`: load `params.json` (generating it if missing) and return `(dsa_keys, rsa_keys, gen_seconds)`.

The purpose is to use **the same parameters and keys** in all variants and benchmark runs, making comparisons consistent.

---

## 4. Basic DSA Implementation (`dsa/dsa.py`)

### 4.1 Data Structures

- `DSAParams(p, q, g)`, with properties `L = bit_length(p)` and `N = bit_length(q)`.
- `DSAKey(params, x, y)`, where `x` is the private key and `y = g^x mod p` is the public key.

### 4.2 Operations

```text
Key generation:
    x <- random integer in [1, q−1]
    y = g^x mod p

hash_to_int:
    z = the leftmost N bits of SHA-256(message), according to FIPS 186

Signing:
    k <- random integer in [1, q−1]
    r = (g^k mod p) mod q
    s = k⁻¹ · (z + x·r) mod q
    if r == 0 or s == 0, choose another k

Verification:
    check 0 < r < q and 0 < s < q
    w  = s⁻¹ mod q
    u₁ = z·w mod q
    u₂ = r·w mod q
    v  = (g^u₁ · y^u₂ mod p) mod q
    valid if and only if v == r
```

**Why verification works:** from the formula for `s`, we get `k = s⁻¹(z + x·r) = u₁ + x·u₂ (mod q)`. Because `g` has order `q`, `g^u₁ · y^u₂ = g^(u₁ + x·u₂) = g^k (mod p)`. Therefore `v = r`.

### 4.3 Hand-Worked Example

Parameters: `p = 23`, `q = 11` (`11` divides `22`), and `h = 2`, giving `g = 2² = 4`. Check: `4¹¹ mod 23 = 1`.

Private key: `x = 3`. Public key: `y = 4³ mod 23 = 64 mod 23 = **18**`.

**Sign** with `z = 5`, choosing `k = 7`:

| Quantity | Calculation | Value |
| --- | --- | --- |
| `g^k mod p` | `4⁷ mod 23` | 8 |
| `r` | `8 mod 11` | **8** |
| `k⁻¹ mod q` | `7·8 = 56 = 5·11 + 1` | 8 |
| `s` | `8·(5 + 3·8) = 232 mod 11` | **1** |

**Verify** the signature `(8, 1)`:

| Quantity | Calculation | Value |
| --- | --- | --- |
| `w` | `1⁻¹ mod 11` | 1 |
| `u₁, u₂` | `5·1, 8·1` | 5, 8 |
| `g^u₁ mod p` | `4⁵ mod 23` | 12 |
| `y^u₂ mod p` | `18⁸ mod 23` | 16 |
| `v` | `12·16 = 192 mod 23 = 8; 8 mod 11` | **8 = r → valid** |

### 4.4 Signer Class Design

Every DSA variant exposes the same interface, `sign(msg) -> (r, s)`. They differ only in **how they obtain a `(k, k⁻¹, r)` triple**:

```text
Signer.sign(msg):
    repeat:
        (k, k⁻¹, r) = self.fresh_triple()  # Implemented by each variant
        if r == 0: continue
        s = k⁻¹ · (z + x·r) mod q          # Shared _finish function
        if s != 0: return (r, s)
```

| Class | How `fresh_triple()` obtains `(k, k⁻¹, r)` | Variant |
| --- | --- | --- |
| `BaselineSigner(key, expfn)` | Random `k`, inverse by Euclid, `r` by `expfn` (custom `modexp` by default; pass `pow` for a C reference) | V0 |
| `FixedBaseSigner(key, "window", w)` | Like V0, but computes `g^k` using the window table | V2 |
| `FixedBaseSigner(key, "comb", h)` | Like V0, but computes `g^k` using the comb table | V3 |
| `PoolSigner(key, filler, batch_inverse=False)` | Takes a triple from the pool; uses `filler` as fallback if the pool is empty | V1 |
| `PoolSigner(key, FixedBaseSigner(...), batch_inverse=True)` | Uses a pool filled with fixed-base exponentiation and batch inversion | V4 |

This design ensures that all variants share the same calculation for `s` and the same verification function. Performance differences therefore come from how they produce or retrieve the `(k, k⁻¹, r)` triple.

---

## 5. Optimization Techniques

### 5.1 V1 — Precomputation Pool (`dsa/pool.py`, `PrecomputePool`)

```text
OFFLINE (while the machine is idle):
    repeat:
        (k, k⁻¹, r) <- filler.fresh_triple()
        append the triple to the queue

ONLINE (when message m arrives):
    (k, k⁻¹, r) <- remove one triple from the queue
                     (each triple must be used EXACTLY ONCE)
    s = k⁻¹ · (H(m) + x·r) mod q
```

In the example from Section 4.3, the pool can already contain `(7, 8, 8)`. When the message arrives, only `s = 8·(z + 24) mod 11` needs to be computed.

**Online cost:** one SHA-256 calculation and two modular multiplications modulo the 224-bit `q`, instead of roughly 336 multiplications modulo a 2048-bit `p` plus an extended Euclidean inversion.

**Main methods:**

| Method | Purpose |
| --- | --- |
| `__init__(params, filler, batch_inverse, capacity)` | Set up the `deque` queue, `Lock`, `issued` counter, and background-thread stop flag |
| `_make_batch(n)` | Create `n` triples; without batch inversion, call `filler.fresh_triple()` repeatedly; with batch inversion, generate `k` values, compute `r` using the filler engine, and calculate inverses with `batch_inv` |
| `fill(n=None, batch=256)` | Fill the pool in batches up to the configured capacity; append each batch under a lock |
| `take()` | Remove one triple with `popleft()` under the lock; return `None` if empty |
| `start_background(low_water, batch)` | Start a background thread that refills when the pool falls below `capacity × low_water` |
| `stop_background()` | Stop the refill thread |
| `__len__()` | Return the number of remaining triples |

**Safety with multiple threads:** the lock around `popleft()` ensures that each queue entry is taken once. The test `test_no_k_issued_twice_under_threads` used eight threads and found no repeated `k` among 2,000 prepared triples. The random nonce generator does not check for duplicates across all generated values.

**Fallback:** if `take()` returns `None`, `PoolSigner` calls `filler.fresh_triple()` directly and increments `fallbacks`. This allows signing to continue and lets benchmarks count the signatures that could not benefit from precomputation.

### 5.2 V2 — Fixed-Base Windowing (`FixedBaseWindow`)

**Idea:** express `k` in base `2^w`, splitting it into `d = ceil(N/w)` digits of `w` bits each:

```text
k = k₀ + k₁·2^w + k₂·2^(2w) + ... + k_(d−1)·2^((d−1)w)
0 <= kᵢ < 2^w

g^k = product over i of g^(kᵢ · 2^(w·i))
```

**Precomputed table** (built in `__init__`):

```text
T[i][j] = g^(j · 2^(w·i)) mod p
for i = 0,...,d−1 and j = 0,...,2^w−1
```

To build the table, row `i` starts with `base = g^(2^(w·i))`. Each entry is computed as `T[i][j] = T[i][j−1] · base`. Multiplying the last entry by `base` gives `base^(2^w)`, which becomes the base for the next row.

**Computing `g^k`** (`pow` method): extract digits using `k & mask`, then shift `k` right by `w` bits:

```text
g^k = T[0][k₀] · T[1][k₁] · ... · T[d−1][k_(d−1)] mod p
```

**Cost:** at most `d = ceil(N/w)` multiplications, with no squarings during the lookup stage. Multiplications for zero digits can be skipped.

| Method | Multiplications for N = 224 | Table entries | Approximate table size at 2048 bits |
| --- | ---: | ---: | ---: |
| Square-and-multiply | 336 | 0 | 0 |
| Window `w = 4` | 56 | `56 × 16 = 896` | 210 KB |
| Window `w = 8` | 28 | `28 × 256 = 7,168` | 1.8 MB |

Each table element requires roughly `L/8` bytes (256 bytes when `L = 2048`).

**Example:** `p = 23`, `g = 4`, `k = 7`, `w = 2`:

- Base-4 representation: `7 = 3 + 1·4`, so `k₀ = 3` and `k₁ = 1`.
- `T[0][3] = 4³ mod 23 = 18`; `T[1][1] = 4⁴ mod 23 = 3`.
- `g⁷ = 18·3 = 54 mod 23 = **8**`, matching Section 4.3.

### 5.3 V3 — Lim–Lee Comb (`CombLimLee`)

**Idea:** arrange the `N` bits of `k` into `h` rows, each containing `a = ceil(N/h)` bits. Row `j` contains bits from position `j·a` to `j·a + a − 1`. Then process the bits **column by column**.

**Precomputed table:**

```text
gⱼ = g^(2^(j·a)) mod p, for j = 0,...,h−1
     (gⱼ₊₁ is obtained by squaring gⱼ exactly a times)

G[u] = product of gⱼ for every set bit j of u,
       for u = 0,...,2^h−1
```

`G` is built efficiently by finding the lowest set bit of `u` (`low = u & −u`, corresponding to bit index `j`), then using `G[u] = G[u xor low] · gⱼ`. Each entry requires one multiplication.

**Computing `g^k`:** process columns `i` from `a − 1` down to 0:

```text
result = result²
u = (bit i of row 0)
    | ((bit i of row 1) << 1)
    | ...
    | ((bit i of row h−1) << (h−1))
if u != 0:
    result = result · G[u]
```

**Why it works:** `k = Σⱼ Σᵢ bit(j·a + i) · 2^(j·a + i)`, so `g^k = ∏ᵢ (∏ⱼ gⱼ^bit(j·a+i))^(2^i) = ∏ᵢ G[uᵢ]^(2^i)`. The main loop is a Horner-style evaluation over the columns.

**Cost:** `a` squarings plus up to `a` multiplications. With `N = 224`, `h = 8`, that is about `28 + 28 = 56` operations.

**Table size:** only `2^h` entries. With `h = 8`, this means 256 elements, about **64 KB**, roughly 28 times smaller than the `w = 8` window table.

**Example:** `p = 23`, `g = 4`, `k = 7 = 0111₂`, `h = 2`, `a = 2`:

- Row 0 contains bits 0 and 1: `(1, 1)`; row 1 contains bits 2 and 3: `(1, 0)`.
- `g₀ = 4`, `g₁ = 4^(2²) = 4⁴ mod 23 = 3`. Table entries: `G[1] = 4`, `G[2] = 3`, `G[3] = 12`.
- Column `i = 1`: `u = 1`, so `result = 1² · G[1] = 4`.
- Column `i = 0`: `u = 3`, so `result = 4² · 12 = 192 mod 23 = **8**`.

**Window versus comb:** at equal `w = h`, comb is about twice as slow because it still performs squarings, but its table is about `ceil(N/w)` times smaller. At comparable speeds, comb tends to save memory (see Section 9.3).

Both classes provide `entries` (the number of table entries) and `table_bytes` (the bytes needed to represent their integer values) for Experiment E3. The memory used by Python's `int` and `list` objects is additional.

### 5.4 V4 — Combined Pool

```text
OFFLINE:
    generate a batch of n random k values
    rᵢ = (g^kᵢ mod p) mod q    # Compute with window or comb
    kᵢ⁻¹                     # Batch inversion: only one Euclidean inverse

ONLINE:
    same signing path as V1
```

In code, V4 is `PoolSigner(key, FixedBaseSigner(...), batch_inverse=True)`.

---

## 6. RSA and RSA-CRT (`rsa/rsa.py`)

### 6.1 Keys — `RSAKey(n, e, d, p, q)`

```text
n = p·q
φ(n) = (p−1)(q−1)
e = 65537
d = e⁻¹ mod φ(n)
```

The `__post_init__` method prepares CRT parameters: `dp = d mod (p−1)`, `dq = d mod (q−1)`, `qinv = q⁻¹ mod p`, and `k`, the modulus length in bytes.

### 6.2 Message Encoding — `emsa_pkcs1_v15(msg, k)`

According to RFC 8017, Section 9.2:

```text
T  = DigestInfo(SHA-256) || SHA-256(msg)
     # DigestInfo uses the fixed 19-byte SHA256_PREFIX

EM = 0x00 || 0x01 || 0xFF...0xFF || 0x00 || T
     # Total length k bytes; at least eight 0xFF bytes

m  = the integer representation of EM
```

### 6.3 Signing and Verification

```text
R0:           s = m^d mod n

R1 (CRT):     s₁ = m^dp mod p
              s₂ = m^dq mod q
              h  = qinv · (s₁ − s₂) mod p
              s  = s₂ + h·q            # Garner recombination

Verification: Check signature length == k bytes, s < n,
              and s^e mod n == EM
```

**Why CRT is correct:** by Fermat's little theorem, `m^d ≡ m^(d mod (p−1)) = s₁ (mod p)`; the equivalent statement holds modulo `q`. Garner's formula combines the two congruences: `s ≡ s₂ (mod q)` and `s ≡ s₂ + (s₁−s₂) = s₁ (mod p)`.

**Why CRT is roughly four times faster in theory:** for this implementation, modular exponentiation cost is roughly proportional to `(exponent bit length) × (modulus bit length)²`, approximately `L³`. Replacing one full-size exponentiation with two half-size ones yields `2 × (1/2)³ = 1/4` of the approximate cost.

**Example:** `p = 5`, `q = 11`, `n = 55`, `e = 3`, `d = 27` because `3·27 = 81 ≡ 1 (mod 40)`, with `m = 2`:

| Quantity | Calculation | Value |
| --- | --- | --- |
| `dp, dq, qinv` | `27 mod 4`; `27 mod 10`; `11⁻¹ mod 5` | 3, 7, 1 |
| `s₁` | `2³ mod 5` | 3 |
| `s₂` | `2⁷ mod 11 = 128 mod 11` | 7 |
| `h` | `1·(3 − 7) mod 5` | 1 |
| `s` | `7 + 1·11` | **18** |
| Check | `18³ mod 55 = 5832 mod 55` | **2 = m ✓** |

PKCS#1 v1.5 signing is **deterministic**: R0 and R1 must produce exactly the same signature bytes for the same key and message. The tests check this property.

---

## 7. Testing (`tests/test_all.py`)

Run tests with `python3 main.py test`. The project includes 11 tests, all reported as passing.

| Category | Test | What it checks |
| --- | --- | --- |
| Arithmetic | `test_modexp_matches_pow` | Custom `modexp` agrees with Python `pow()` on 200 random cases with 2048-bit moduli and 300-bit exponents |
| Arithmetic | `test_modinv_and_batch` | `batch_inv` agrees with `modinv` for 500 values and each `a·a⁻¹ ≡ 1` |
| Fixed-base | `test_window_and_comb_match_pow_1000_random_k` | Window and comb agree with `pow(g,k,p)` for widths 2–8 at both levels; width 6 is tested with 1,000 random `k` values |
| DSA | `test_sign_verify_all_variants` | Six DSA configurations × two levels × 30 messages: valid signatures are accepted, while modified messages or `s` values are rejected |
| DSA | `test_cross_check_pycryptodome` | PyCryptodome's `Crypto.Signature.DSS` verifies signatures from every variant, and the custom verifier accepts PyCryptodome signatures |
| Pool | `test_no_k_issued_twice_under_threads` | Eight threads take 2,000 triples; there are 2,000 distinct `k` values and the pool is empty afterward |
| Pool | `test_fallback_when_empty` | A pool with three entries signs six messages successfully and reports `fallbacks = 3` |
| Pool | `test_triples_consistent` | Every V4 triple at the 3072-bit level satisfies `k·k⁻¹ ≡ 1` and `r = (g^k mod p) mod q` |
| Pool | `test_background_fill` | A background thread fills the pool to its threshold; ten signatures then require no fallback |
| RSA | `test_sign_verify_and_crt` | R0 and R1 produce the same signature; valid signatures pass and changed messages fail |
| RSA | `test_cross_check_pycryptodome` | R1's signature matches PyCryptodome `pkcs1_15` byte-for-byte, and PyCryptodome verifies R0 signatures |

The `all_signers(key)` helper creates all six DSA configurations for reuse across tests.

---
## 8. Performance Measurement (`bench/`)

### 8.1 Common Measurement Function — `harness.measure(fn, ...)`

1. Run `fn` once to estimate its execution time; use that estimate to choose `M`, the number of iterations per repetition, so one repetition lasts approximately `budget_s` seconds. `M` is bounded by `[min_iter, max_iter]`.
2. Perform a warm-up of up to 50 calls without recording the results.
3. Measure five repetitions, each containing `M` calls. Use `time.perf_counter_ns()` and convert durations to microseconds.
4. Return these statistics:
   - `median_us`: median of all measured samples; the main reported metric.
   - `p95_us`: 95th percentile; about 95% of measurements fall at or below this value.
   - `mean_us`: arithmetic mean.
   - `rep_median_min_us`, `rep_median_max_us`: the smallest and largest median across the five repetitions, indicating stability.
   - `iters_per_rep`, `repeats`: measurement configuration.

The project reports the **median** rather than the mean as its primary metric because a few unusually slow samples (for example, due to operating-system scheduling or Python garbage collection) have less influence on the median.

Useful derived metrics:

```text
Speedup factor    = median(V0) / median(Vx)
Cost per triple   = pool fill time / pool size
Throughput        = number of signatures in a burst / total burst time
```

`write_csv(name, rows)` saves results in `bench/results/`. `env_info()` records information about the CPU, RAM, and Python version in `env.json`.

### 8.2 Experiments — `bench/run_all.py`

Every experiment covers the 2048-bit and 3072-bit levels. `W_BEST = 8` specifies the window/comb width used for V2, V3, and V4 in the main comparisons.

**Checks during measurement:** E1 signs different messages with `checked(signer, key)`, then verifies approximately 200 sampled signatures and stops if a check fails. E3 checks one exponent against `pow()` for each table. E5 verifies a sample from the final run. E4 measures signing and verification on the same message without the `checked` wrapper. These checks supplement the test suite.

| Experiment | Function | What is measured | Method | CSV file |
| --- | --- | --- | --- | --- |
| E1 | `e1()` | Online signing latency for custom V0, built-in-`pow` V0, V2, V3, V1, and V4 | Pool has 8,000 entries—more than enough for the measured calls—so online samples never need a fallback (`assert fallbacks == 0`) | `e1_sign_latency.csv` |
| E2 | `e2()` | Pool filling with three methods and pool sizes 100, 1,000, and 10,000 | Median of three runs (one run for the 10,000-entry pool); separate comparison of individual Euclidean inversions against batch inversion for 1,000 values | `e2_pool_fill.csv` |
| E3 | `e3()` | Time for `g^k` and table size for window and comb, widths 2–8 | Compare against square-and-multiply and Python `pow()`; check each table against `pow()` before measurement | `e3_fixed_base.csv` |
| E4 | `e4()` | DSA signing (V0, V2, V4), DSA verification, RSA signing (R0, R1), RSA verification, key generation, and sizes | Compare `modexp` and `pow()` for DSA V0, DSA verification, and RSA. DSA V2 and V4 keep the same fixed-base engine. Repeat RSA key generation 10 times at 2048 bits and four times at 3072 bits, then report the upper middle value | `e4_dsa_vs_rsa.csv` |
| E5 | `e5()` | Throughput when signing 2,000 messages sequentially | Five conditions: V0, V3 without a pool, V4 full pool, V4 half-full pool, and V4 empty pool; three runs per condition, reporting the median | `e5_burst.csv` |

### 8.3 Charts — `bench/plots.py`

The plotting script reads the CSV files and produces five PNG charts, each with panels for 2048-bit and 3072-bit results:

| File | Chart type | Notes |
| --- | --- | --- |
| `e1_sign_latency.png` | Bar chart, logarithmic axis | Error bars show p95; labels show time and speedup |
| `e2_pool_fill.png` | Grouped bar chart | Milliseconds per triple, grouped by pool size |
| `e3_fixed_base.png` | Line chart, log–log axes | Runtime versus table size, with square-and-multiply and `pow()` reference lines |
| `e4_dsa_vs_rsa.png` | Bar chart, logarithmic axis | Milliseconds per operation |
| `e5_burst.png` | Horizontal bar chart, logarithmic axis | Signatures per second |

Logarithmic axes are necessary because the measurements span several orders of magnitude—from a few microseconds to tens of milliseconds.

---

## 9. Experimental Results

**Benchmark environment:** Intel Xeon 2.10 GHz virtual machine, two CPU cores, 8 GB RAM, Linux, CPython 3.13.18. The following values are **medians**, as reported in the project data.

### 9.1 E1 — Online Signing Latency

| Variant | 2048-bit time | Speedup | 3072-bit time | Speedup |
| --- | ---: | ---: | ---: | ---: |
| V0 (custom exponentiation) | 4,034 µs | 1.0× | 9,604 µs | 1.0× |
| V0 (C-backed `pow`) | 3,174 µs | 1.3× | 7,625 µs | 1.3× |
| V2 window, `w = 8` | 414 µs | 9.7× | 924 µs | 10.4× |
| V3 comb, `h = 8` | 729 µs | 5.5× | 1,656 µs | 5.8× |
| V1 pool (online) | 2.1 µs | ≈1,900× | 2.1 µs | ≈4,500× |
| V4 pool (online) | 3.3 µs | ≈1,200× | 2.2 µs | ≈4,400× |

- When the pool is ready, online signing time is almost independent of the security level because only small-number arithmetic modulo `q` remains.
- V1 and V4 follow the same online signing path, so differences of only a few microseconds can reflect measurement noise.
- Custom modular exponentiation is only about 1.27 times slower than the C-backed `pow()` in the baseline. The large speedups therefore mainly reflect the algorithmic optimizations rather than just using a faster implementation language.

### 9.2 E2 — Pool Fill Cost

| Pool filling method (2048 bits) | Cost per triple | Time for 10,000 triples |
| --- | ---: | ---: |
| V1: custom exponentiation + individual Euclidean inversions | 4.06 ms | 40.6 s |
| V4: comb `h = 8` + batch inversion | 0.73 ms | 7.3 s |
| V4: window `w = 8` + batch inversion | 0.38 ms | 3.8 s |

At the 3072-bit level, the corresponding per-triple times are **9.76 ms**, **1.69 ms**, and **0.87 ms**.

- Time per triple remains nearly constant across pool sizes, so total fill time scales approximately linearly.
- For inversion alone, individual Euclidean inversions take 32.5 µs per number, while batch inversion takes about 1.2 µs per number—around **27 times faster**. However, inversions account for less than 1% of total triple preparation time, so V4's main benefit comes from fixed-base exponentiation.
- **V4's total cost** at the 2048-bit level (about 0.38 ms offline plus 0.002 ms online) is close to **V2 signing directly** (about 0.41 ms). The pool does not eliminate all that work: it moves most of it to idle time.

### 9.3 E3 — Window versus Comb

| Level | Method for computing `g^k` | Time | Table memory | Speedup |
| --- | --- | ---: | ---: | ---: |
| 2048 | Square-and-multiply | 3,981 µs | 0 | 1.0× |
| 2048 | C-backed `pow()` | 3,097 µs | 0 | 1.3× |
| 2048 | Comb `h = 8` | 682 µs | 64 KB | 5.8× |
| 2048 | Window `w = 4` | 699 µs | 210 KB | 5.7× |
| 2048 | Window `w = 8` | 364 µs | 1.8 MB | 10.9× |
| 3072 | Square-and-multiply | 9,445 µs | 0 | 1.0× |
| 3072 | Comb `h = 8` | 1,581 µs | 96 KB | 6.0× |
| 3072 | Window `w = 8` | 840 µs | 3.0 MB | 11.2× |

- For windowing, increasing `w` by one reduces computation time by roughly 13–23%, but increases memory use by about 1.5–1.8 times. The performance benefit becomes smaller as `w` grows.
- Comb with `h = 8` has speed comparable to window with `w = 4`, but uses a table roughly 3.3 times smaller. Window is preferable when maximum speed matters and a few megabytes are available; comb is preferable when memory is limited.
- Table construction takes only around 5–223 ms and is done once at initialization.

### 9.4 E4 — DSA versus RSA

| Operation (custom modular exponentiation) | 2048 bits | 3072 bits |
| --- | ---: | ---: |
| DSA V0 signing | 4.03 ms | 9.61 ms |
| DSA V2 signing | 0.41 ms | 0.89 ms |
| DSA V4 online signing | 1.9 µs | 2.0 µs |
| RSA R0 signing | 36.2 ms | 113.0 ms |
| RSA R1 CRT signing | 11.1 ms | 33.5 ms |
| DSA verification | 8.00 ms | 19.99 ms |
| RSA verification | 0.19 ms | 0.40 ms |
| DSA key generation `(x, y)` | 3.96 ms | 9.36 ms |
| RSA key generation | 1.03 s | 5.13 s |
| One-time DSA parameter generation `(p, q, g)` | 0.69 s | 6.65 s |
| DSA signature size | 56 bytes | 64 bytes |
| RSA signature size | 256 bytes | 384 bytes |

- **Signing:** even baseline DSA V0 is about 2.7× faster than RSA-CRT at 2048 bits and 3.5× faster at 3072 bits. With fixed-base exponentiation, the gap grows to about 27× and 38×.
- **CRT:** RSA signing becomes about 3.3–3.4× faster, close to the theoretical estimate of 4×.
- **Verification:** RSA is around 42× faster than DSA at 2048 bits and 50× faster at 3072 bits.
- **Key generation:** once shared parameters `p, q, g` are available, DSA key generation is much faster than RSA key generation.
- **Signature size:** DSA signatures are around 4.6–6 times smaller than RSA signatures in this comparison.
- Benchmarks using Python's C-backed `pow()` lead to the same overall conclusions; full results are in the CSV files.

### 9.5 E5 — Burst of 2,000 Signing Requests

| Case | 2048-bit throughput | 3072-bit throughput |
| --- | ---: | ---: |
| V0 | 241 signatures/s | 103 signatures/s |
| V3 comb, no pool | 1,207 signatures/s | 589 signatures/s |
| V4, full pool (2,000 entries) | ≈409,000 signatures/s | ≈378,000 signatures/s |
| V4, half-full pool (1,000 entries) | 2,576 signatures/s | 1,186 signatures/s |
| V4, empty pool | 1,289 signatures/s | 582 signatures/s |

A half-full pool provides only about twice the throughput of an empty pool: the remaining 1,000 messages require direct calculations, which dominate the total time. **A finite pool can absorb a short burst only as far as its prepared capacity allows.** Over a long period, sustainable signing speed remains limited by the pool refill rate—approximately 2,600 triples per second per core for window `w = 8` at 2048 bits, based on the measured fill cost.

### 9.6 Experimental Limitations

- The benchmarks ran on a two-core virtual machine using CPython. Absolute times are much slower than highly optimized native cryptographic libraries such as OpenSSL. The project therefore focuses on **relative differences** between variants within the same implementation.
- The measurements do not cover a background thread refilling the pool concurrently with ongoing signing. Because of CPython's Global Interpreter Lock (GIL), two Python threads may compete for a single core for CPU-bound work. A practical implementation could use a separate process to refill the pool.
- The Python code is not constant-time, so the experiments do not evaluate side-channel resistance or its performance overhead.

---

## 10. Security Analysis

### 10.1 Reusing `k` Reveals the Private Key

If the same `k` is used to sign two different message hashes `z₁` and `z₂`, the signatures have the same `r` and:

```text
s₁ − s₂ = k⁻¹ · (z₁ − z₂) (mod q)

k = (z₁ − z₂) · (s₁ − s₂)⁻¹ mod q
x = (s₁·k − z₁) · r⁻¹ mod q
```

Thus nonce reuse can expose the signing key. This kind of failure was involved in the Sony PlayStation 3 signing-key incident in 2010. Every pool triple must therefore be issued **exactly once**. The implementation uses `popleft()` under a lock, and a test checks this behavior with eight threads.

### 10.2 `k` Must Be Uniformly Random

If several bits of `k` are exposed or biased across enough signatures, lattice attacks related to the Hidden Number Problem may recover the private key. The implementation uses `secrets.randbelow`, backed by the operating system's cryptographically secure random number generator, and never uses Python's general-purpose `random` module for DSA nonces.

### 10.3 Pool Entries Must Be Protected Like Secret Keys

Knowledge of a prepared `(k, r)` pair can allow an attacker to derive the private key once that pair is used in a signature. The pool therefore resides in process memory rather than being deliberately written to disk. A production system would also need measures such as:

- Protecting sensitive memory against swapping to disk.
- Clearing or invalidating the pool after process forks or virtual-machine snapshot restores, because copying a pool can lead to accidental reuse of `k`.

### 10.4 Incompatibility with RFC 6979

RFC 6979 generates `k` deterministically from the private key and the message hash `H(m)`. This avoids dependence on a fresh random source at signing time, but `k` cannot be computed before the message is known. That is an important tradeoff of message-independent precomputation. The original project document also mentions a possible hybrid idea involving a keyed pseudorandom function and a counter; such a design would require separate security analysis before practical use.

### 10.5 Side Channels

Fixed-base tables are indexed using digits derived from the secret nonce `k`. Their memory-access patterns may leak information through cache behavior. A secure implementation would need constant-time table access, for example accessing all candidates and selecting the desired entry without secret-dependent branches. Python does not provide constant-time guarantees for arbitrary-precision arithmetic, so this project evaluates **performance only**, not resistance to side-channel attacks.

### 10.6 Current Standardization Status

[NIST FIPS 186-5](https://doi.org/10.6028/NIST.FIPS.186-5) retains DSA for verifying existing signatures. Fixed-base tables can also speed up point multiplication in ECDSA and Schnorr. Each scheme needs a separate design for nonce preparation. Deterministic ECDSA ([RFC 6979](https://www.rfc-editor.org/rfc/rfc6979.html#section-3.2)) and EdDSA ([RFC 8032](https://www.rfc-editor.org/rfc/rfc8032.html#section-5.1.6)) derive nonces from the message. Schnorr and EdDSA also use different signing formulas that do not require the DSA nonce inversion.

---

## 11. Demo, `main.py`, and Docker

### `demo/demo_cli.py`

Parameters: `--level 2048|3072` and `--msg "message text"`.

The demo performs these steps:

1. Load keys and display the selected key sizes.
2. **Offline stage:** build window and comb tables, then fill two pools (V1 and V4), each containing 200 triples. Display preparation time and table sizes.
3. Sign the same message using V0, V2, V3, V1, and V4 (20 calls per variant, reporting the mean); then R0 (three calls) and R1 (five calls). Display signing time, speedup relative to V0, and verification status.
4. Display shortened DSA signature components and the byte lengths of DSA and RSA signatures.
5. Modify the message by appending one character and show that the demo reports `INVALID`.

`timed(fn, n)` calls `fn` `n` times and returns the last result and average time in microseconds. **The demo timings are illustrative; the formal experimental results come from the benchmarks.**

### `main.py`

The main entry point maps user commands to Python modules and runs them through `subprocess`. The `all` command runs `test -> demo -> bench -> plots` in sequence and stops if any step fails. Arguments after a specific command are passed through unchanged, such as `main.py bench e1` or `main.py demo --level 3072`.

### `Dockerfile`

The Dockerfile uses `python:3.12-slim`, installs `requirements.txt`, copies the project files, sets `main.py` as the entry point, and uses `demo` as the default command.

---

## 12. Quick Function Reference

| File | Name | Purpose |
| --- | --- | --- |
| `core/modarith.py` | `modexp(base, exp, mod)` | Square-and-multiply modular exponentiation |
|  | `egcd(a, b)` | Extended Euclid, returns `(g, x, y)` |
|  | `modinv(a, m)` | Modular multiplicative inverse |
|  | `batch_inv(values, m)` | Batch modular inversion (Montgomery trick) |
| `core/primes.py` | `SMALL_PRIMES` | Small prime numbers below 2,000 for quick trial division |
|  | `is_probable_prime(n, rounds)` | Miller–Rabin probabilistic primality test |
|  | `random_prime(bits)` | Generate a prime of the specified bit length |
|  | `gen_dsa_params(L, N)` | Generate DSA parameters `(p, q, g)` |
|  | `gen_rsa_key(bits, e)` | Generate RSA key components `(n, e, d, p, q)` |
| `core/keystore.py` | `LEVELS` | Two supported `(L, N)` parameter sets |
|  | `generate(path)` | Generate keys and save `params.json` |
|  | `load(path)` | Read `params.json` and return DSA keys, RSA keys, and generation times |
| `dsa/dsa.py` | `DSAParams`, `DSAKey` | DSA parameter and key data |
|  | `keygen(params, expfn)` | Generate private/public key pair `(x, y)` |
|  | `hash_to_int(msg, N)` | Convert the leftmost `N` bits of SHA-256 to an integer |
|  | `verify(key, msg, sig, expfn)` | Verify a DSA signature |
|  | `_finish(key, msg, k_inv, r)` | Compute `s`; shared by every DSA variant |
|  | `Signer` | Base class; `sign()` calls `fresh_triple()` then `_finish()` |
|  | `BaselineSigner` | V0 |
|  | `FixedBaseSigner` | V2 (window) and V3 (comb) |
|  | `PoolSigner` | V1/V4 with fallback and `fallbacks` counter |
| `dsa/pool.py` | `PrecomputePool` | `fill`, `take`, `_make_batch`, `start_background`, `stop_background` |
| `dsa/fixed_base.py` | `_elem_bytes(x)` | Byte size of a stored table element |
|  | `FixedBaseWindow` | Window table `T[i][j]`, `pow(k)`, `entries`, `table_bytes` |
|  | `CombLimLee` | Comb table `G[u]`, `pow(k)`, `entries`, `table_bytes` |
| `rsa/rsa.py` | `SHA256_PREFIX` | SHA-256 DigestInfo prefix for RFC 8017 encoding |
|  | `RSAKey` | RSA key and precomputed `dp`, `dq`, `qinv`, `k` |
|  | `emsa_pkcs1_v15(msg, k)` | PKCS#1 v1.5 encoding |
|  | `sign(key, msg, crt, expfn)` | R0 if `crt=False`, R1 if `crt=True` |
|  | `verify(key, msg, sig, expfn)` | Verify an RSA signature |
| `bench/harness.py` | `measure`, `write_csv`, `env_info` | Time operations, write CSV files, describe environment |
| `bench/run_all.py` | `e1` … `e5`, `checked`, `verify_all`, `msgs` | Experiments and signature verification during measurement |
| `bench/plots.py` | `e1` … `e5`, `rows`, `short` | Draw the benchmark charts |
| `demo/demo_cli.py` | `main`, `timed` | Command-line demo |
| `main.py` | `COMMANDS`, `main` | Common command dispatcher |

---

## 13. References

1. NIST FIPS 186-4 (2013) and FIPS 186-5 (2023), *Digital Signature Standard (DSS)*.
2. NIST SP 800-57 Part 1 Rev. 5 (2020), *Recommendation for Key Management* — comparable security-strength levels.
3. K. Moriarty et al., RFC 8017 (2016), *PKCS #1: RSA Cryptography Specifications, Version 2.2*.
4. T. Pornin, RFC 6979 (2013), *Deterministic Usage of DSA and ECDSA*.
5. C. H. Lim and P. J. Lee, *More Flexible Exponentiation with Precomputation*, CRYPTO 1994.
6. E. Brickell, D. Gordon, K. McCurley, and D. Wilson, *Fast Exponentiation with Precomputation*, EUROCRYPT 1992.
7. A. Menezes, P. van Oorschot, and S. Vanstone, *Handbook of Applied Cryptography*, CRC Press, 1996, Chapters 4, 11, and 14.
8. N. Howgrave-Graham and N. Smart, *Lattice Attacks on Digital Signature Schemes*, *Designs, Codes and Cryptography*, 2001.
9. fail0verflow, *Console Hacking 2010: PS3 Epic Fail*, 27C3, 2010.
