import secrets

SMALL_PRIMES = [p for p in range(3, 2000, 2) if all(p % d for d in range(3, int(p**0.5) + 1, 2))]


def is_probable_prime(n: int, rounds: int = 40) -> bool:
    if n < 2:
        return False
    if n in (2, 3):
        return True
    if n % 2 == 0:
        return False
    for sp in SMALL_PRIMES:
        if n == sp:
            return True
        if n % sp == 0:
            return False
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def random_prime(bits: int) -> int:
    while True:
        c = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if is_probable_prime(c):
            return c


def gen_dsa_params(L: int, N: int):
    q = random_prime(N)
    two_q = 2 * q
    while True:
        X = secrets.randbits(L) | (1 << (L - 1))
        p = X - (X % two_q) + 1
        if p.bit_length() == L and is_probable_prime(p, rounds=20):
            break
    e = (p - 1) // q
    h = 2
    while True:
        g = pow(h, e, p)
        if g > 1:
            break
        h += 1
    return p, q, g


def gen_rsa_key(bits: int, e: int = 65537):
    from core.modarith import modinv

    while True:
        p = random_prime(bits // 2)
        q = random_prime(bits // 2)
        if p == q:
            continue
        n = p * q
        if n.bit_length() != bits:
            continue
        phi = (p - 1) * (q - 1)
        try:
            d = modinv(e, phi)
        except ValueError:
            continue
        return n, e, d, p, q
