"""Case table, figures and the numeric part of results/results.md.

Every number written here is read from files produced by the pipeline; nothing is typed in.
Figures use the validated three-slot palette (dataviz reference instance, light mode, since
they go into a PDF): blue #2a78d6, orange #eb6834, aqua #1baf7a; ink and hairlines from the
same reference. Every figure has a table twin in results/.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from features import EXPLORATORY_FEATURES, FEATURES  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
LABEL_ORDER = ["C", "I", "N", "L"]
LABEL_NAMES = {"C": "coordinated", "I": "independent", "N": "no loop found", "L": "linked, no loop"}
FEATURE_NAMES = {
    "loop_share": "Loop share (K=4)",
    "loop_share_1hop": "Loop share (1 hop)",
    "shared_funder_share": "Shared first funder",
    "shared_funder_share_nonhub": "Shared funder, hubs excluded",
    "payer_hhi": "Payer concentration (HHI)",
    "outside_funding_share": "Outside funding share",
    "timing_coupling": "Timing coupling",
    "relay_share": "Relay share",
    "pair_reciprocity_timing": "Pair reciprocity timing*",
    "payer_synchrony": "Payer synchrony*",
}


def style(ax: plt.Axes) -> None:
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AXIS)
        ax.spines[s].set_linewidth(0.8)
    ax.tick_params(colors=INK2, labelsize=8, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def case_table() -> pd.DataFrame:
    reg = yaml.safe_load((ROOT / "cases" / "cases.yaml").read_text())
    src = {f["family"]: ", ".join(f["source"]) for f in reg["families"]}
    pred = pd.read_csv(RES / "predictions.csv")
    pred["source_decodes"] = pred["family"].map(src)
    cols = ["case_id", "family", "half", "chain", "window", "payee", "label", "y", "contested", "source_decodes",
            "n_payments", "n_payers", "volume"] + FEATURES + ["flag_primary", "flag_non_circular"]
    t = pred[cols].sort_values(["half", "y", "family", "window", "payee"], ascending=[True, False, True, True, True])
    t.to_csv(RES / "case_table.csv", index=False, float_format="%.4g")
    return t


def fig_features(t: pd.DataFrame, frozen: dict) -> None:
    fig, axes = plt.subplots(2, 4, figsize=(11, 5.4), dpi=200, facecolor=SURFACE)
    rng = np.random.default_rng(0)
    thresholds = {}
    for r in [frozen["rule"]] if frozen["rule"]["type"] == "single" else frozen["rule"]["terms"]:
        thresholds[r["feature"]] = r["threshold"]
    for ax, f in zip(axes.flat, FEATURES):
        style(ax)
        for half, color, mk in (("dev", BLUE, "o"), ("test", ORANGE, "o")):
            part = t[t["half"] == half]
            for i, lab in enumerate(LABEL_ORDER):
                v = part[part["label"] == lab][f].to_numpy(dtype=float)
                v = v[~np.isnan(v)]
                x = i + (-0.17 if half == "dev" else 0.17) + rng.uniform(-0.09, 0.09, size=len(v))
                ax.scatter(x, v, s=14, color=color, edgecolors=SURFACE, linewidths=0.6, zorder=3,
                           label=("development half" if half == "dev" else "test half") if i == 0 else None)
        if f in thresholds:
            ax.axhline(thresholds[f], color=INK2, linewidth=0.9, zorder=2)
            ax.text(3.45, thresholds[f], "frozen\nthreshold", fontsize=6.5, color=INK2, va="bottom", ha="right")
        ax.set_xticks(range(4), LABEL_ORDER)
        ax.set_xlim(-0.6, 3.6)
        ax.set_title(FEATURE_NAMES[f], fontsize=9, color=INK, loc="left")
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False, fontsize=8, labelcolor=INK2)
    fig.text(0.01, 0.005, "C coordinated · I independent · N no loop found · L linked, no loop (labels from the published decodes)",
             fontsize=7, color=MUTED)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(RES / "fig1_features_by_label.png", facecolor=SURFACE)
    plt.close(fig)


def fig_positive_control(summary: pd.DataFrame) -> None:
    groups = {
        "seller's money reaches the ring in 1 to 4 hops": ["direct", "relay2", "relay4"],
        "5 hops, or through an exchange-like hub": ["relay5", "via_hub"],
        "shared outside funder, no loop": ["common_funder"],
    }
    fig, ax = plt.subplots(figsize=(6.4, 3.6), dpi=200, facecolor=SURFACE)
    style(ax)
    for (name, routes), color in zip(groups.items(), (BLUE, ORANGE, AQUA)):
        s = summary[summary["route"].isin(routes)].groupby("phi")["flag_primary"].mean()
        ax.plot(s.index, s.values, color=color, linewidth=2, marker="o", markersize=4.5, markeredgecolor=SURFACE,
                markeredgewidth=1, label=name, solid_capstyle="round")
    ax.set_xscale("log")
    ax.set_xlabel("injected ring's share of the seller's payment volume", fontsize=8, color=INK2)
    ax.set_ylabel("share of runs the frozen rule flags", fontsize=8, color=INK2)
    ax.set_ylim(-0.03, 1.05)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.1%}" if v < 0.01 else f"{v:.0%}"))
    ax.legend(frameon=False, fontsize=7.5, labelcolor=INK2, loc="center right")
    fig.tight_layout()
    fig.savefig(RES / "fig2_positive_control.png", facecolor=SURFACE)
    plt.close(fig)


def fig_auc(auc: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(6.4, 3.4), dpi=200, facecolor=SURFACE)
    style(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    order = auc[auc["half"] == "dev"].set_index("feature")["auc_family_weighted"].sort_values().index.tolist()
    y = np.arange(len(order))
    for half, color, off in (("dev", BLUE, 0.13), ("test", ORANGE, -0.13)):
        a = auc[auc["half"] == half].set_index("feature").loc[order, "auc_family_weighted"]
        ax.scatter(a.values, y + off, s=26, color=color, edgecolors=SURFACE, linewidths=0.8, zorder=3,
                   label="development half" if half == "dev" else "test half")
    ax.axvline(0.5, color=AXIS, linewidth=0.9)
    ax.set_yticks(y, [FEATURE_NAMES[f] for f in order], fontsize=8)
    ax.set_xlim(0, 1.02)
    ax.set_xlabel("AUC, family-weighted (0.5 = no better than chance; * exploratory)", fontsize=8, color=INK2)
    ax.legend(frameon=False, fontsize=7.5, labelcolor=INK2, loc="lower right")
    fig.tight_layout()
    fig.savefig(RES / "fig3_feature_auc.png", facecolor=SURFACE)
    plt.close(fig)


def fig_timing_shuffle(t: pd.DataFrame, nc: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 3.2), dpi=200, facecolor=SURFACE)
    rng = np.random.default_rng(1)
    shuffled = nc.groupby("case_id")[["timing_coupling", "relay_share"]].mean()
    for ax, f in zip(axes, ("timing_coupling", "relay_share")):
        style(ax)
        for j, (y, name) in enumerate(((1, "coordinated"), (0, "not coordinated"))):
            ids = t[t["y"] == y]["case_id"]
            real = t[t["y"] == y][f].to_numpy(dtype=float)
            shuf = shuffled.loc[shuffled.index.intersection(ids), f].to_numpy(dtype=float)
            ax.scatter(j - 0.15 + rng.uniform(-0.07, 0.07, len(real)), real, s=12, color=BLUE, edgecolors=SURFACE, linewidths=0.5,
                       label="real timing" if j == 0 else None, zorder=3)
            ax.scatter(j + 0.15 + rng.uniform(-0.07, 0.07, len(shuf)), shuf, s=12, color=ORANGE, edgecolors=SURFACE, linewidths=0.5,
                       label="payment times shuffled" if j == 0 else None, zorder=3)
        ax.axhline(0, color=AXIS, linewidth=0.9)
        ax.set_xticks([0, 1], ["coordinated", "not coordinated"])
        ax.set_title(FEATURE_NAMES[f], fontsize=9, color=INK, loc="left")
    axes[0].legend(frameon=False, fontsize=7, labelcolor=INK2, loc="upper right")
    fig.tight_layout()
    fig.savefig(RES / "fig4_timing_shuffle.png", facecolor=SURFACE)
    plt.close(fig)


BASIS_TO_FEATURE = {
    "seller_to_buyer_funding_path": "loop_share",
    "seller_funds_buyers": "loop_share",
    "payment_tree": "loop_share",
    "direct_reciprocity": "loop_share_1hop",
    "closure_of_payment_set": "outside_funding_share",
    "closure_of_hiring_set": "loop_share",
    "no_outside_payments": "outside_funding_share",
    "first_funder_is_seller": "shared_funder_share",
    "shared_funder": "shared_funder_share",
    "shared_funder_without_seller_path": "shared_funder_share",
    "shared_high_throughput_funder": "shared_funder_share",
    "many_distinct_funders": "shared_funder_share",
    "no_loop_in_seller_outflow_trace": "loop_share",
    "no_seller_funding": "loop_share",
    "no_funding_link_pairwise": "loop_share",
    "money_returns_through_high_throughput_account": "loop_share",
}


def md_table(df: pd.DataFrame, floatfmt: str = "{:.3f}") -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            cells.append(floatfmt.format(v) if isinstance(v, float) and not np.isnan(v) else ("" if isinstance(v, float) else str(v)))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def circularity_table() -> pd.DataFrame:
    """Which features the decode's own evidence corresponds to, per family."""
    reg = yaml.safe_load((ROOT / "cases" / "cases.yaml").read_text())
    rows = []
    for f in reg["families"]:
        used = sorted({BASIS_TO_FEATURE.get(b, "(none)") for b in f["label_basis"]})
        rows.append({"family": f["family"], "label": f["label"], "decode_evidence": ", ".join(f["label_basis"]), "closest_feature": ", ".join(used)})
    t = pd.DataFrame(rows)
    t.to_csv(RES / "circularity.csv", index=False)
    return t


def main() -> None:
    frozen = json.loads((RES / "frozen_rule.json").read_text())
    circularity_table()
    t = case_table()
    fig_features(t, frozen)
    auc = pd.read_csv(RES / "feature_auc.csv")
    fig_auc(auc)
    if (RES / "positive_control_summary.csv").exists():
        fig_positive_control(pd.read_csv(RES / "positive_control.csv"))
    if (RES / "negative_control_timing_shuffle.csv").exists():
        fig_timing_shuffle(t, pd.read_csv(RES / "negative_control_timing_shuffle.csv"))
    print("figures and case table written")


if __name__ == "__main__":
    main()
