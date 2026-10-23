"""Figure: the reach walk, with three worked examples from the committed case tables.

Added Oct 23 to 24, 2026, after the freeze (cases/market_plan.md, section 6). Every count and share
is read from data/cases (payer_reach, payments, meta.json) and results/sensitivity_features.csv;
the address prefixes are the ones the decodes print. Writes results/fig_reach_walk.png.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import FancyArrowPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
EXAMPLES = [
    ("X Pay, W4", "F06-xpay|0x589a2314a2e05f45e40c4823da3ba58d421db3d8|W4", ["payTo\n0x589a2314"], []),
    ("ClusterProtocol, W1", "F01-clusterprotocol|0x68396bd35874695ad86cd29410bd80a550991a2b|W1",
     ["payTo\n0x68396bd3", "wallet\n0x0a4135f9", "{n2} distributors"], []),
    ("BotPay, W2", "F04-botpay|0x159be9e316bc5fac8ce05aec4eaae46e8f8a4908|W2",
     ["payTo\n0x159be9e3", "contract\n0xcc1984e7", "root\n0x8736ae11", "{n3} funders", "{n4} buyers"], []),
]


def case_facts(cid: str) -> dict:
    d = ROOT / "data" / "cases" / cid.replace("|", "__")
    meta = json.loads((d / "meta.json").read_text())
    reach = pd.read_csv(d / "payer_reach.csv.gz")
    pay = pd.read_csv(d / "payments.csv.gz")
    v = pay.groupby("payer")["value"].sum()
    reach["value"] = reach["payer"].map(v)
    hop = int(reach.groupby(reach["hops"].fillna(-1).astype(int))["value"].sum().drop(-1, errors="ignore").idxmax())
    at = reach[reach["hops"] == hop]
    sens = pd.read_csv(ROOT / "results" / "sensitivity_features.csv")
    ls = sens[sens["case_id"] == cid].set_index("k")["loop_share"]
    return {"hop": hop, "payers_at_hop": int(len(at)), "share_at_hop": float(at["value"].sum() / v.sum()), "n_payers": int(meta["n_payers"]),
            "reach_by_hop": {int(h): int(n) for h, n in meta["reach_by_hop"]}, "ls4": float(ls.loc[4]), "ls5": float(ls.loc[5])}


def node(ax, x: float, y: float, text: str, color: str, fill: str) -> None:
    ax.text(x, y, text, ha="center", va="center", fontsize=6.6, color=INK, zorder=4, linespacing=1.15,
            bbox={"boxstyle": "round,pad=0.32", "fc": fill, "ec": color, "lw": 1.0})


def arrow(ax, x0: float, x1: float, y: float, color: str) -> None:
    ax.add_patch(FancyArrowPatch((x0 + 0.33, y), (x1 - 0.33, y), arrowstyle="-|>", mutation_scale=8, color=color, lw=1.0, zorder=3))


def back(ax, x0: float, y: float, color: str, label: str) -> None:
    """Dashed return path under the lane: from the payers' node back to the payee."""
    yb = y - 0.47
    ax.plot([x0, x0, 0, 0], [y - 0.2, yb, yb, y - 0.24], color=color, lw=1.0, ls=(0, (3, 2)), zorder=2, solid_capstyle="round")
    ax.add_patch(FancyArrowPatch((0, yb + 0.02), (0, y - 0.21), arrowstyle="-|>", mutation_scale=8, color=color, lw=1.0, zorder=3))
    ax.text(x0 / 2, yb - 0.12, label, ha="center", va="center", fontsize=6.2, color=color)


def pct(x: float) -> str:
    return f"{x:.2%}" if 0.999 <= x < 1 else f"{x:.1%}"


def main() -> None:
    fig, ax = plt.subplots(figsize=(7.6, 4.9), dpi=200, facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    ax.axvspan(0.55, 4.5, color=BLUE, alpha=0.06, lw=0)
    ax.axvline(4.5, color=INK2, lw=0.9, ls=(0, (4, 3)))
    ax.text(0.62, 4.82, "reach set, K = 4: wallets the payee's money reached in at most 4 transfers", ha="left", fontsize=6.6, color=BLUE)
    ax.text(0.62, 4.65, "through non-hub wallets, in lookback + window", ha="left", fontsize=6.6, color=BLUE)
    ax.text(4.56, 4.82, "beyond the", ha="left", fontsize=6.6, color=INK2)
    ax.text(4.56, 4.65, "reach limit", ha="left", fontsize=6.6, color=INK2)
    lanes = [3.95, 2.75, 1.55]
    for (title, cid, labels, _), y in zip(EXAMPLES, lanes):
        f = case_facts(cid)
        rb = f["reach_by_hop"]
        flagged = f["ls4"] >= 0.4235
        color = ORANGE if flagged else INK2
        fill = "#fdf0ea" if flagged else "#f1f0ec"
        texts = [t.format(n2=rb.get(2, 0), n3=rb.get(3, 0), n4=rb.get(4, 0)) for t in labels]
        for h, t in enumerate(texts):
            node(ax, h, y, t, INK2 if h else INK, "#ffffff")
        node(ax, f["hop"], y, f"{f['payers_at_hop']} of {f['n_payers']} payers\n{pct(f['share_at_hop'])} of value", color, fill)
        for h in range(f["hop"]):
            arrow(ax, h, h + 1, y, INK2)
        back(ax, f["hop"], y, color, "their x402 payments to the payTo")
        verdict = (f"loop share {f['ls4']:.2f}, flagged" if flagged else f"loop share {f['ls4']:.2f} at K = 4, missed ({f['ls5']:.2f} at K = 5)")
        ax.text(-0.45, y + 0.36, title, ha="left", fontsize=7.4, color=INK, weight="bold")
        ax.text(0.95, y + 0.36, verdict, ha="left", fontsize=6.8, color=color)
    y = 0.2
    node(ax, 0, y, "seller", INK, "#ffffff")
    node(ax, 1.05, y, "exchange-like hub\n(1,000+ counterparties)", INK2, "#f1f0ec")
    node(ax, 2.25, y, "ring payer", INK2, "#ffffff")
    arrow(ax, 0, 0.88, y, INK2)
    ax.add_patch(FancyArrowPatch((1.62, y), (1.92, y), arrowstyle="-|>", mutation_scale=8, color=MUTED, lw=1.0, ls=(0, (2, 2)), zorder=3))
    ax.text(-0.45, y + 0.36, "Hub blind spot", ha="left", fontsize=7.4, color=INK, weight="bold")
    ax.text(0.95, y + 0.36, "the walk stops at hubs: a ring funded this way is never reached (positive control)", ha="left", fontsize=6.8, color=INK2)
    ax.text(-0.45, -0.45, "A transfer that a contract forwards in the same transaction (a facilitator proxy) is passed through, not counted as a hop.",
            ha="left", fontsize=6.0, color=MUTED)
    ax.set_xlim(-0.55, 5.6)
    ax.set_ylim(-0.6, 5.0)
    ax.set_xticks(range(6), ["payee\n(hop 0)", "hop 1", "hop 2", "hop 3", "hop 4", "hop 5"], fontsize=7, color=INK2)
    ax.tick_params(length=0)
    ax.set_yticks([])
    for s_ in ("top", "right", "left"):
        ax.spines[s_].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    fig.tight_layout()
    fig.savefig(ROOT / "results" / "fig_reach_walk.png", facecolor=SURFACE)
    plt.close(fig)
    print("wrote results/fig_reach_walk.png")


if __name__ == "__main__":
    main()
