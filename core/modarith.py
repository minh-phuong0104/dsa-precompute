def modexp(base: int, exp: int, mod: int) -> int:
    if mod == 1:
        return 0
    if exp < 0:
        return modexp(modinv(base, mod), -exp, mod)
    base %= mod
    result = 1
    for bit in bin(exp)[2:]:
        result = result * result % mod
        if bit == "1":
            result = result * base % mod
    return result


def egcd(a: int, b: int):
    x0, y0, x1, y1 = 1, 0, 0, 1
    while b:
        qt, a, b = a // b, b, a % b
        x0, x1 = x1, x0 - qt * x1
        y0, y1 = y1, y0 - qt * y1
    return a, x0, y0


def modinv(a: int, m: int) -> int:
    g, x, _ = egcd(a % m, m)
    if g != 1:
        raise ValueError("không tồn tại nghịch đảo modulo")
    return x % m


def batch_inv(values, m: int):
    n = len(values)
    if n == 0:
        return []
    prefix = [0] * n
    acc = 1
    for i, v in enumerate(values):
        acc = acc * v % m
        prefix[i] = acc
    inv_acc = modinv(acc, m)
    out = [0] * n
    for i in range(n - 1, 0, -1):
        out[i] = inv_acc * prefix[i - 1] % m
        inv_acc = inv_acc * values[i] % m
    out[0] = inv_acc
    return out
