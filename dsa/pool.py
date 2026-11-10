import secrets
import threading
from collections import deque

from core.modarith import batch_inv


class PrecomputePool:
    def __init__(self, params, filler, batch_inverse=False, capacity=1000):
        self.params = params
        self.filler = filler
        self.batch_inverse = batch_inverse
        self.capacity = capacity
        self._q = deque()
        self._lock = threading.Lock()
        self.issued = 0
        self._bg = None
        self._stop = threading.Event()

    def __len__(self):
        return len(self._q)

    def _make_batch(self, n):
        P = self.params
        if not self.batch_inverse:
            return [self.filler.fresh_triple() for _ in range(n)]
        ks = [secrets.randbelow(P.q - 1) + 1 for _ in range(n)]
        powf = (
            self.filler.engine.pow
            if hasattr(self.filler, "engine")
            else (lambda k: self.filler.expfn(P.g, k, P.p))
        )
        rs = [powf(k) % P.q for k in ks]
        invs = batch_inv(ks, P.q)
        return list(zip(ks, invs, rs))

    def fill(self, n=None, batch=256):
        target = self.capacity if n is None else min(self.capacity, len(self) + n)
        while len(self) < target:
            chunk = self._make_batch(min(batch, target - len(self)))
            with self._lock:
                self._q.extend(chunk)

    def take(self):
        with self._lock:
            if not self._q:
                return None
            t = self._q.popleft()
            self.issued += 1
            return t

    def start_background(self, low_water=0.5, batch=64):
        def loop():
            while not self._stop.is_set():
                if len(self) < self.capacity * low_water:
                    self.fill(batch, batch=batch)
                else:
                    self._stop.wait(0.005)

        self._stop.clear()
        self._bg = threading.Thread(target=loop, daemon=True)
        self._bg.start()

    def stop_background(self):
        self._stop.set()
        if self._bg:
            self._bg.join()
            self._bg = None
