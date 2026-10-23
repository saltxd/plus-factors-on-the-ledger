"""Evidence features for one case: a payee (seller or hired agent) in one window.

Every feature is computed from the same five tables, whatever the chain or market:

  payments        payer, value, ts                  payments into the payee during the window
  payer_inflows   payer, src, value, ts, order,     every USDC (or stablecoin) transfer into a payer
                  src_hops, src_is_payer,           during lookback + window; src is the economic
                  src_is_hub, src_is_seller         sender after same-transaction pass-through
  seller_outflows dst, value, ts                    every transfer out of the payee in lookback + window
  payer_reach     payer, hops                       shortest path payee -> payer through non-hub
                                                    wallets (None if not reachable within K hops)
  window          t0, t1 (unix seconds, end exclusive)

Definitions (fixed before any case was scored):

loop_share
    Share of payment value whose payer is reachable from the payee by a path of at most K
    USDC transfers through non-hub wallets, inside lookback + window. "The payee's own money
    reached the payer before or while the payer paid it."
loop_share_1hop
    Same with K = 1: payers the payee paid directly.
shared_funder_share
    Each payer's first funder is the sender of its first non-zero inflow in lookback + window.
    The share of payment value from the payers behind the most common first funder, counting
    only funders that first-funded at least two of the payee's payers (0 if none did).
    Hubs (exchanges, routers, custodial accounts) are included as funders.
shared_funder_share_nonhub
    Same, but a hub never counts as a shared funder (each such payer counts alone).
payer_hhi
    Herfindahl index of payment value across payers (1 = one payer).
outside_funding_share
    Share of the value flowing into payers (lookback + window) that comes from wallets that are
    not the payee, not another payer and not reachable from the payee. 1.0 when payers received
    nothing (they spent money held before the lookback).
timing_coupling
    Fraction of payments made within LAG_COUPLING seconds after any transfer out of the payee,
    minus the same fraction when each payer's payment times are circularly shifted by a random
    offset inside the window (mean of N_NULL shifts). About 0 when payment timing is unrelated
    to the payee's own outflows.
relay_share
    Fraction of payments made within LAG_RELAY seconds after the payer received money from
    anyone, minus the circular-shift null. High when payers spend money the moment it arrives.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

K_HOPS = 4
LAG_COUPLING = 3600
LAG_RELAY = 600
N_NULL = 200

FEATURES = [
    "loop_share",
    "loop_share_1hop",
    "shared_funder_share",
    "shared_funder_share_nonhub",
    "payer_hhi",
    "outside_funding_share",
    "timing_coupling",
    "relay_share",
]

# Direction in which a feature is expected to point to coordination.
DIRECTION = {
    "loop_share": +1,
    "loop_share_1hop": +1,
    "shared_funder_share": +1,
    "shared_funder_share_nonhub": +1,
    "payer_hhi": +1,
    "outside_funding_share": -1,
    "timing_coupling": +1,
    "relay_share": +1,
}


@dataclass
class CaseData:
    case_id: str
    payments: pd.DataFrame
    payer_inflows: pd.DataFrame
    seller_outflows: pd.DataFrame
    payer_reach: dict[str, int | None]
    t0: int
    t1: int
    meta: dict = field(default_factory=dict)


def _payer_values(p: pd.DataFrame) -> pd.Series:
    return p.groupby("payer")["value"].sum()


def loop_share(cd: CaseData, k: int = K_HOPS) -> float:
    v = _payer_values(cd.payments)
    if v.sum() <= 0:
        return float("nan")
    reach = np.array([(cd.payer_reach.get(b) is not None and cd.payer_reach[b] <= k) for b in v.index])
    return float(v[reach].sum() / v.sum())


def first_funders(cd: CaseData) -> pd.Series:
    inf = cd.payer_inflows
    inf = inf[inf["value"] > 0]
    if inf.empty:
        return pd.Series(dtype=object)
    first = inf.sort_values(["payer", "order"]).groupby("payer").head(1).set_index("payer")
    return first[["src", "src_is_hub"]]


def shared_funder_share(cd: CaseData, nonhub: bool = False) -> float:
    """Value share of the payers behind the most common first funder, counting only funders
    that first-funded at least two of this payee's payers (0 when none did)."""
    v = _payer_values(cd.payments)
    if v.sum() <= 0:
        return float("nan")
    ff = first_funders(cd)
    groups: dict[str, list[str]] = {}
    for b in v.index:
        if b not in ff.index:
            continue
        src, hub = ff.loc[b, "src"], bool(ff.loc[b, "src_is_hub"])
        if nonhub and hub:
            continue
        groups.setdefault(src, []).append(b)
    best = 0.0
    for members in groups.values():
        if len(members) >= 2:
            best = max(best, float(v[members].sum()))
    return best / float(v.sum())


def payer_hhi(cd: CaseData) -> float:
    v = _payer_values(cd.payments)
    if v.sum() <= 0:
        return float("nan")
    w = v / v.sum()
    return float((w**2).sum())


def outside_funding_share(cd: CaseData, k: int = K_HOPS) -> float:
    inf = cd.payer_inflows
    inf = inf[inf["value"] > 0]
    if inf.empty:
        return 1.0
    inside = (
        (inf["src_is_seller"] == 1)
        | (inf["src_is_payer"] == 1)
        | ((inf["src_hops"] >= 0) & (inf["src_hops"] <= k))
    )
    tot = inf["value"].sum()
    return float(inf.loc[~inside, "value"].sum() / tot) if tot > 0 else 1.0


def _follows(event_ts: np.ndarray, ref_ts: np.ndarray, lag: int, strict: bool) -> np.ndarray:
    """For each event, is there a reference time r with 0 < e - r <= lag (strict) or 0 <= e - r <= lag."""
    if len(ref_ts) == 0 or len(event_ts) == 0:
        return np.zeros(len(event_ts), dtype=bool)
    ref = np.sort(ref_ts)
    side = "left" if strict else "right"
    idx = np.searchsorted(ref, event_ts, side=side) - 1  # last ref strictly before (or at) e
    ok = idx >= 0
    out = np.zeros(len(event_ts), dtype=bool)
    out[ok] = (event_ts[ok] - ref[idx[ok]]) <= lag
    return out


def _shifted(times: np.ndarray, payers: np.ndarray, t0: int, t1: int, rng: np.random.Generator) -> np.ndarray:
    span = t1 - t0
    uniq, inv = np.unique(payers, return_inverse=True)
    off = rng.integers(0, span, size=len(uniq))
    return t0 + ((times - t0 + off[inv]) % span)


def timing_coupling(cd: CaseData, lag: int = LAG_COUPLING, n_null: int = N_NULL, seed: int = 0) -> float:
    p = cd.payments
    if p.empty:
        return float("nan")
    out_ts = cd.seller_outflows["ts"].to_numpy(dtype=np.int64)
    ts = p["ts"].to_numpy(dtype=np.int64)
    obs = _follows(ts, out_ts, lag, strict=True).mean()
    rng = np.random.default_rng(seed)
    payers = p["payer"].to_numpy()
    null = [_follows(_shifted(ts, payers, cd.t0, cd.t1, rng), out_ts, lag, strict=True).mean() for _ in range(n_null)]
    return float(obs - np.mean(null))


def relay_share(cd: CaseData, lag: int = LAG_RELAY, n_null: int = N_NULL, seed: int = 0) -> float:
    p = cd.payments
    if p.empty:
        return float("nan")
    inf = cd.payer_inflows[cd.payer_inflows["value"] > 0]
    by_payer = {b: g["ts"].to_numpy(dtype=np.int64) for b, g in inf.groupby("payer")}
    rng = np.random.default_rng(seed)

    def frac(ts_all: np.ndarray) -> float:
        hits = 0
        for b, idx in groups.items():
            ref = by_payer.get(b)
            if ref is not None:
                hits += int(_follows(ts_all[idx], ref, lag, strict=False).sum())
        return hits / len(ts_all)

    groups = {b: np.flatnonzero(p["payer"].to_numpy() == b) for b in p["payer"].unique()}
    ts = p["ts"].to_numpy(dtype=np.int64)
    obs = frac(ts)
    payers = p["payer"].to_numpy()
    null = [frac(_shifted(ts, payers, cd.t0, cd.t1, rng)) for _ in range(n_null)]
    return float(obs - np.mean(null))


def compute_features(cd: CaseData, k: int = K_HOPS, n_null: int = N_NULL) -> dict[str, float]:
    v = _payer_values(cd.payments)
    return {
        "n_payments": int(len(cd.payments)),
        "n_payers": int(len(v)),
        "volume": float(v.sum()),
        "loop_share": loop_share(cd, k),
        "loop_share_1hop": loop_share(cd, 1),
        "shared_funder_share": shared_funder_share(cd, nonhub=False),
        "shared_funder_share_nonhub": shared_funder_share(cd, nonhub=True),
        "payer_hhi": payer_hhi(cd),
        "outside_funding_share": outside_funding_share(cd, k),
        "timing_coupling": timing_coupling(cd, n_null=n_null),
        "relay_share": relay_share(cd, n_null=n_null),
    }
