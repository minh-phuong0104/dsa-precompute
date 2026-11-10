import csv
import json
import os
import platform
import statistics
import time

RESULTS = os.path.join(os.path.dirname(__file__), "results")
REPEATS = 5


def measure(fn, budget_s=3.0, max_iter=1000, min_iter=40, warmup=None, repeats=REPEATS):
    t0 = time.perf_counter_ns()
    fn()
    one_call_seconds = (time.perf_counter_ns() - t0) / 1e9
    estimated_iters = budget_s / max(one_call_seconds, 1e-7)
    estimated_iters = max(min_iter, estimated_iters)
    iters_per_round = int(min(max_iter, estimated_iters))
    warm = warmup if warmup is not None else min(50, M)
    for _ in range(warm):
        fn()
    samples, rep_medians = [], []
    for _ in range(repeats):
        round_times = []
        for _ in range(M):
            a = time.perf_counter_ns()
            fn()
            rs.append((time.perf_counter_ns() - a) / 1000)
        samples += rs
        rep_medians.append(statistics.median(rs))
    samples.sort()
    return {
        "median_us": statistics.median(samples),
        "p95_us": samples[int(0.95 * (len(samples) - 1))],
        "mean_us": statistics.fmean(samples),
        "rep_median_min_us": min(rep_medians),
        "rep_median_max_us": max(rep_medians),
        "iters_per_rep": M,
        "repeats": repeats,
    }


def write_csv(name, rows):
    path = os.path.join(RESULTS, name)
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print("->", path, flush=True)


def env_info():
    info = {
        "python": platform.python_version(),
        "impl": platform.python_implementation(),
        "machine": platform.machine(),
        "system": platform.platform(),
        "cpus": os.cpu_count(),
    }
    try:
        for line in open("/proc/cpuinfo"):
            if line.startswith("model name"):
                info["cpu"] = line.split(":", 1)[1].strip()
                break
        for line in open("/proc/meminfo"):
            if line.startswith("MemTotal"):
                info["ram"] = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    with open(os.path.join(RESULTS, "env.json"), "w") as f:
        json.dump(info, f, indent=1)
    return info
