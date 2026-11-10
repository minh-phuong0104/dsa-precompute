import csv
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
RES, OUT = os.path.join(HERE, "results"), os.path.join(HERE, "plots")
BLUE, ORANGE, GREY, GREEN = "#2a6fdb", "#e8833a", "#9aa0a6", "#2e9e6b"
plt.rcParams.update(
    {
        "font.size": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titleweight": "bold",
        "axes.titlesize": 11,
        "figure.dpi": 150,
    }
)


def rows(name):
    with open(os.path.join(RES, name)) as f:
        return list(csv.DictReader(f))


def short(v):
    return (
        v.replace(" (modexp tự cài)", "\n(tự cài)")
        .replace(" (pow C có sẵn)", "\n(pow C)")
        .replace("V2 fixed-base window (w=8)", "V2 window\n(w=8)")
        .replace("V3 comb Lim-Lee (h=8)", "V3 comb\n(h=8)")
        .replace(" (online)", "\n(online)")
        .replace("pool comb+batch inv", "pool")
    )


def e1():
    R = rows("e1_sign_latency.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for ax, lvl in zip(axes, ("2048", "3072")):
        rr = [r for r in R if r["level"] == lvl]
        names = [short(r["variant"]) for r in rr]
        med = [float(r["median_us"]) for r in rr]
        p95 = [float(r["p95_us"]) for r in rr]
        cols = [GREY, GREY, BLUE, BLUE, GREEN, GREEN]
        ax.bar(
            range(len(rr)),
            med,
            color=cols,
            yerr=[[0] * len(med), [b - a for a, b in zip(med, p95)]],
            capsize=3,
            ecolor="#555",
        )
        ax.set_yscale("log")
        ax.set_xticks(range(len(rr)), names, fontsize=7.5)
        ax.set_title(f"DSA L={lvl}: độ trễ ký online (median, vạch = p95)")
        base = med[0]
        for i, (m, top) in enumerate(zip(med, p95)):
            ax.text(
                i,
                top * 1.12,
                f"{m:,.0f} µs\n{base / m:.1f}x" if m >= 10 else f"{m:.1f} µs\n{base / m:,.0f}x",
                ha="center",
                va="bottom",
                fontsize=7.5,
            )
        ax.set_ylim(top=max(p95) * 4)
    axes[0].set_ylabel("µs / chữ ký (thang log)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "e1_sign_latency.png"))
    plt.close(fig)


def e2():
    R = [r for r in rows("e2_pool_fill.csv") if not r["filler"].startswith("chỉ")]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, lvl in zip(axes, ("2048", "3072")):
        fillers = list(dict.fromkeys(r["filler"] for r in R))
        sizes = ["100", "1000", "10000"]
        width = 0.26
        for j, (fl, c) in enumerate(zip(fillers, [GREY, BLUE, GREEN])):
            v = [
                float(
                    next(r for r in R if r["level"] == lvl and r["filler"] == fl and r["pool_size"] == s)[
                        "us_per_triple"
                    ]
                )
                / 1000
                for s in sizes
            ]
            xs = [i + (j - 1) * width for i in range(3)]
            ax.bar(xs, v, width, color=c, label=fl)
            for x, y in zip(xs, v):
                ax.text(x, y + 0.08, f"{y:.2f}", ha="center", fontsize=7)
        ax.set_xticks(range(3), [f"pool {s}" for s in sizes])
        ax.set_title(f"L={lvl}: chi phí offline mỗi bộ (k, k⁻¹, r)")
    axes[0].set_ylabel("ms / bộ")
    axes[0].legend(fontsize=7.5, frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "e2_pool_fill.png"))
    plt.close(fig)


def e3():
    R = rows("e3_fixed_base.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, lvl in zip(axes, ("2048", "3072")):
        rr = [r for r in R if r["level"] == lvl]
        ref = float(next(r for r in rr if r["method"].startswith("square"))["median_us"])
        refc = float(next(r for r in rr if r["method"].startswith("pow"))["median_us"])
        for meth, c in (("window", BLUE), ("comb", ORANGE)):
            pts = [r for r in rr if r["method"] == meth]
            xs = [float(r["table_kb"]) for r in pts]
            ys = [float(r["median_us"]) for r in pts]
            ax.plot(xs, ys, "o-", color=c, label=f"{meth} (w=2…8)")
            for r, x, y in zip(pts, xs, ys):
                ax.annotate(
                    f"w={r['w']}", (x, y), textcoords="offset points", xytext=(4, 4), fontsize=7, color=c
                )
        ax.axhline(ref, color=GREY, ls="--", lw=1)
        ax.text(
            ax.get_xlim()[1] if False else 1.2,
            ref * 1.05,
            f"square-and-multiply tự cài: {ref:,.0f} µs",
            fontsize=7.5,
            color="#555",
        )
        ax.axhline(refc, color=GREY, ls=":", lw=1)
        ax.text(1.2, refc * 0.86, f"pow C có sẵn: {refc:,.0f} µs", fontsize=7.5, color="#555")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("dung lượng bảng (KB, thang log)")
        ax.set_title(f"L={lvl}: thời gian g^k theo dung lượng bảng")
        ax.legend(fontsize=8, frameon=False, loc="lower left")
    axes[0].set_ylabel("µs / phép g^k (thang log)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "e3_fixed_base.png"))
    plt.close(fig)


def e4():
    R = rows("e4_dsa_vs_rsa.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), sharey=True)
    order = [
        ("DSA V0", "sign"),
        ("DSA V2 window w=8", "sign"),
        ("DSA V4 pool (online)", "sign"),
        ("RSA R0", "sign"),
        ("RSA R1 CRT", "sign"),
        ("DSA", "verify"),
        ("RSA", "verify"),
    ]
    labels = [
        "DSA ký\nV0",
        "DSA ký\nV2",
        "DSA ký\nV4 pool",
        "RSA ký\nR0",
        "RSA ký\nR1 CRT",
        "DSA\nxác minh",
        "RSA\nxác minh",
    ]
    cols = [GREY, BLUE, GREEN, ORANGE, ORANGE, GREY, ORANGE]
    for ax, lvl in zip(axes, ("2048", "3072")):
        v = [
            float(
                next(
                    r
                    for r in R
                    if r["level"] == lvl and r["impl"] == "tự cài" and r["scheme"] == s and r["op"] == o
                )["median_us"]
            )
            / 1000
            for s, o in order
        ]
        ax.bar(range(len(v)), v, color=cols)
        ax.set_yscale("log")
        for i, y in enumerate(v):
            ax.text(i, y * 1.15, f"{y:.3f}" if y < 0.1 else f"{y:,.1f}", ha="center", fontsize=7.5)
        ax.set_xticks(range(len(v)), labels, fontsize=7.5)
        ax.set_title(f"Mức {lvl}: DSA vs RSA (modexp tự cài, median)")
    axes[0].set_ylabel("ms / thao tác (thang log)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "e4_dsa_vs_rsa.png"))
    plt.close(fig)


def e5():
    R = rows("e5_burst.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), sharex=False)
    for ax, lvl in zip(axes, ("2048", "3072")):
        rr = [r for r in R if r["level"] == lvl]
        v = [float(r["sigs_per_sec"]) for r in rr]
        cols = [GREY, BLUE, GREEN, GREEN, GREY]
        ax.barh(range(len(v)), v, color=cols)
        ax.set_xscale("log")
        ax.set_yticks(range(len(v)), [r["case"] for r in rr], fontsize=8)
        ax.invert_yaxis()
        for i, x in enumerate(v):
            ax.text(x * 1.1, i, f"{x:,.0f}", va="center", fontsize=8)
        ax.set_title(f"L={lvl}: thông lượng đợt 2000 chữ ký")
        ax.set_xlabel("chữ ký / giây (thang log)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "e5_burst.png"))
    plt.close(fig)


if __name__ == "__main__":
    for f in (e1, e2, e3, e4, e5):
        try:
            f()
            print("ok", f.__name__)
        except FileNotFoundError as e:
            print("bỏ qua", f.__name__, e)
