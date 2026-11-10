def _elem_bytes(x: int) -> int:
    return (x.bit_length() + 7) // 8


class FixedBaseWindow:
    def __init__(self, g: int, p: int, nbits: int, w: int):
        self.p, self.w = p, w
        self.digits = -(-nbits // w)
        self.mask = (1 << w) - 1
        self.table = []
        base = g % p
        for _ in range(self.digits):
            row = [1] * (1 << w)
            for j in range(1, 1 << w):
                row[j] = row[j - 1] * base % p
            self.table.append(row)
            base = row[-1] * base % p

    def pow(self, k: int) -> int:
        p, w, mask = self.p, self.w, self.mask
        result = 1
        for row in self.table:
            d = k & mask
            if d:
                result = result * row[d] % p
            k >>= w
        return result

    @property
    def entries(self) -> int:
        return self.digits * (1 << self.w)

    @property
    def table_bytes(self) -> int:
        return sum(_elem_bytes(x) for row in self.table for x in row)


class CombLimLee:
    def __init__(self, g: int, p: int, nbits: int, h: int):
        self.p, self.h = p, h
        self.a = a = -(-nbits // h)

        gj = [g % p]
        for _ in range(1, h):
            x = gj[-1]
            for _ in range(a):
                x = x * x % p
            gj.append(x)
        table = [1] * (1 << h)
        for u in range(1, 1 << h):
            low = u & -u
            j = low.bit_length() - 1
            table[u] = table[u ^ low] * gj[j] % p
        self.table = table

    def pow(self, k: int) -> int:
        p, h, a, table = self.p, self.h, self.a, self.table
        result = 1
        for i in range(a - 1, -1, -1):
            result = result * result % p
            u = 0
            for j in range(h):
                u |= ((k >> (j * a + i)) & 1) << j
            if u:
                result = result * table[u] % p
        return result

    @property
    def entries(self) -> int:
        return 1 << self.h

    @property
    def table_bytes(self) -> int:
        return sum(_elem_bytes(x) for x in self.table)
