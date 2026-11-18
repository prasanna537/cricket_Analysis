#!/usr/bin/env python
"""
SuperRR Selector Season 2 - Round 1
Most Reliable Players Under Pressure  (IPL + T20I, 2022 onwards)

Runs end to end from the raw CSVs:   python analysis.py
Everything that appears in the report is produced here (no hand-typed numbers).
All tunable choices live in CONFIG below.
"""
import copy
import json
import re
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import spearmanr
import shap
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import GroupKFold

warnings.filterwarnings("ignore")

# =====================================================================================
# CONFIG  (every weight / threshold lives here)
# =====================================================================================
BASE = Path(__file__).resolve().parent

# ---- AUCTION AVAILABILITY (applied ONLY to the final ranking; raw data, baselines and ratings are untouched) ----
RETIRED_EXCLUDE = {
    "Dinesh Karthik": "Retired from all cricket, 1 Jun 2024",
    "Andre Russell":  "Retired from IPL, 30 Nov 2025 (now KKR power coach; still plays other leagues)",
    "Dwayne Bravo":   "Retired from playing; KKR support staff",
    "Mahendra Singh Dhoni": "Retired, as stated by the user on 18 Nov 2026 (type of retirement not specified)",
}
RETAINED_EXCLUDE = {}   # to be filled from the OFFICIAL IPL 2027 retention lists (deadline 17 Nov 2026).
                        # Format: {"Player Name": "Retained by TEAM, official list dd Mon 2026"}. Never add predicted retentions.
# Nationality rule: Pakistan players are not eligible to play in the IPL. Derived from the DATA (competition_team_player_mapping.csv):
# any player listed in a team whose name matches team_regex is excluded from the FINAL ranking only. Add more rules here if needed.
NATIONALITY_EXCLUDE = {
    "Pakistan": dict(team_regex=r"^Pakistan( A)?$",
                     reason="Appears in Pakistan / Pakistan A squads in the data; Pakistan players are not eligible to play in the IPL",
                     status="Not eligible for IPL (Pakistan)"),
}
# Exact player IDs, confirmed against ball_by_ball.csv by name lookup. Names are re-checked against the data at run time.
EXCLUDE_IDS = {"Dinesh Karthik": 143, "Andre Russell": 1318, "Dwayne Bravo": 161, "Mahendra Singh Dhoni": 8}

# ---- IPL 2027 retention lists (supplied 18 Nov 2026), matched to player IDs by build_retention_map.py (exact name, else same-franchise IPL 2026 squad).
# Players retained by OTHER franchises are removed from the final ranking only. Players retained by Rajasthan Royals stay eligible.
RETENTION_FILE = BASE / "retention_lists_2027_matched.csv"
RETENTION_ASOF = "18 Nov 2026"


def _load_retention():
    ret, ids, rr = {}, {}, {}
    if RETENTION_FILE.exists():
        m = pd.read_csv(RETENTION_FILE)
        m = m[m["player_id"].notna()]
        for _, r in m.iterrows():
            if r["team"] == "Rajasthan Royals":
                rr[int(r["player_id"])] = r["data_name"]
                continue
            src = str(r["source"]) if "source" in m.columns and pd.notna(r["source"]) else "pasted list"
            how = f"retention list supplied {RETENTION_ASOF}" if src == "pasted list" else src
            ret[r["data_name"]] = f"Retained by {r['team']}{' (traded in)' if r['traded_in'] else ''}, {how}"
            ids[r["data_name"]] = int(r["player_id"])
    return ret, ids, rr


RETAINED_EXCLUDE, _RET_IDS, RR_RETAINED = _load_retention()
# ---- Selector's own exclusions (a choice, not an availability fact). Applied to the final ranking only.
MANUAL_EXCLUDE = {
    "Tim Southee": "Removed at the selector's request, 18 Nov 2026",
    "Mohit Sharma": "Joining the Chennai Super Kings support staff, as stated by the user on 18 Nov 2026",
    "Jaker Ali Anik": "Removed at the selector's request, 18 Nov 2026",
    "Taskin Ahmed": "Removed at the selector's request, 18 Nov 2026",
}
EXCLUDE_IDS["Tim Southee"] = 278
EXCLUDE_IDS["Mohit Sharma"] = 2878
EXCLUDE_IDS["Jaker Ali Anik"] = 4773
EXCLUDE_IDS["Taskin Ahmed"] = 2681
EXCLUDE_IDS.update(_RET_IDS)
# availability_status for each excluded player (anyone not listed here is "Unverified")
EXCLUDE_STATUS = {"Dinesh Karthik": "Retired from all cricket", "Andre Russell": "Retired from IPL",
                  "Dwayne Bravo": "Retired from all cricket",   # Bravo: source text says "Retired from playing" -> mapped to this status; please confirm
                  "Mahendra Singh Dhoni": "Retired from IPL"}   # Dhoni: user said "retired" without specifying; "Retired from IPL" is the status that matters for the auction
CONFIG = dict(
    seed=42,
    data_dir=BASE / "Data Pack",
    out_dir=BASE / "outputs",
    full_innings_balls=120,                      # used when no rain-revised value exists
    revised_overs_are_balls=True,                # *_revised_overs holds BALLS in this data (30..114)
    wide_types=["wide"],
    noball_types=["Overstep", "other"],          # 'other' behaves like a no-ball (bat runs + 1 extra)
    non_bowler_dismissals=["RunOut", "Retire Out", "Obstracting the field", "Obstructing the field"],
    not_charged_to_batter=["Retire Out"],
    phases={"Powerplay": (1, 6), "Middle": (7, 15), "Death": (16, 20)},
    # ---- pressure score ---------------------------------------------------------
    pressure=dict(
        inn2=dict(rrr=0.40, wkts=0.25, late=0.20, close=0.15),
        inn1=dict(wkts=0.35, late=0.35, par=0.30),
        rrr_lo=6.0, rrr_hi=16.0,                 # required rate mapped linearly 0..1 between these
        close_width=4.0,                         # runs/over either side of the "typical" rate
        close_center=None,                       # None -> league mean 1st-innings run rate (from data)
        par_gap_scale=30.0,                      # runs behind par that count as full pressure
    ),
    hp_quantile=0.25,                            # top 25% of balls per innings = high pressure
    wk=8.0,                                      # wicket value (runs)
    expected=dict(k=200, wkt_edges=[0, 2, 4, 6, 11]),   # blend cell mean with format-level fallback
    min_hp=dict(bat=120, bowl=100),
    min_hp_matches=15,                           # matches contributing >=3 high-pressure balls (guards against one-tournament streaks)
    shrink_k=100,
    consistency=dict(min_hp_balls_match=3, k=5),
    wpa=dict(k=100, leverage=True, n_splits=5, test_frac=0.25),
    recovery=dict(k=100, window=6),
    rating_w=dict(value=1.0, delta=0.5, consistency=0.5, wpa=0.5, recovery=0.25),
    season_min_hp=dict(bat=30, bowl=25),
    half_min_hp=dict(bat=60, bowl=50),
    knockout_k=300,
    role_min_balls=60,
    top_n=10,                                    # players analysed in depth (heatmaps, SHAP moments, report tables)
    list_n=10,                                   # length of the final selection lists
    rr_retained=RR_RETAINED, retention_file=RETENTION_FILE,
    shap=dict(background=150, sample=3000, moments_per_player=3, dep_bins=12),
    availability_as_of="13 Nov 2026",
    nationality_exclude=NATIONALITY_EXCLUDE,
    retired_exclude=RETIRED_EXCLUDE, retained_exclude=RETAINED_EXCLUDE, exclude_ids=EXCLUDE_IDS, exclude_status=EXCLUDE_STATUS, manual_exclude=MANUAL_EXCLUDE,
    a_team_regex="Emerging Teams|Rising Stars",   # A-team / development events (flagged; excluded in one sensitivity scenario)
)

OUT = CONFIG["out_dir"]
OUT.mkdir(exist_ok=True, parents=True)
np.random.seed(CONFIG["seed"])
STATE = {}   # filled by main(); used by player_profile()

HP_COL, NM_COL = "#D55E00", "#0072B2"
plt.rcParams.update({"figure.dpi": 130, "font.size": 9, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.titlesize": 10, "axes.titleweight": "bold"})


def log(*a):
    print(*a, flush=True)


def to_bool(s):
    if s.dtype == bool:
        return s
    return s.astype(str).str.strip().str.lower().isin(["true", "1", "t", "yes"])


# =====================================================================================
# STEP 0/1  LOAD + CLEAN
# =====================================================================================
def load_and_clean(cfg):
    D = cfg["data_dir"]
    b = pd.read_csv(D / "ball_by_ball.csv", low_memory=False)
    m = pd.read_csv(D / "matches.csv")
    c = pd.read_csv(D / "competitions.csv")
    for col in ["is_four", "is_six", "is_wicket"]:
        b[col] = to_bool(b[col])
    summ = {"ball_rows_raw": len(b), "matches_raw": len(m)}

    m["match_date"] = pd.to_datetime(m["match_date"], errors="coerce")
    m["year"] = m["match_date"].dt.year
    m = m.merge(c[["comp_id", "comp_name", "match_format", "season"]], on="comp_id", how="left")
    no_res = m["result"].str.contains("No Result|Abandoned", case=False, na=False)
    summ["matches_no_result_or_abandoned"] = int(no_res.sum())
    m_ok = m[~no_res].copy()

    b = b[b["innings"].isin([1, 2])]
    summ["rows_after_superover_removed"] = len(b)
    b = b[b["match_id"].isin(m_ok["match_id"])]
    summ["rows_after_dropping_noresult"] = len(b)
    key = ["match_id", "innings", "innings_ball_num", "striker_id", "bowler_id", "batting_team_id", "runs"]
    n0 = len(b)
    b = b.dropna(subset=key).drop_duplicates(["match_id", "innings", "innings_ball_num"])
    summ["broken_or_duplicate_rows_dropped"] = n0 - len(b)

    df = b.merge(m_ok[["match_id", "comp_id", "comp_name", "match_format", "season", "year", "match_date", "stage",
                       "knock_out", "win_team_id", "result", "first_inn_revised_overs",
                       "second_inn_revised_overs", "revised_target"]], on="match_id", how="left")
    df = df.sort_values(["match_id", "innings", "innings_ball_num"]).reset_index(drop=True)

    df["total_runs"] = df["runs"] + df["extras1_runs"] + df["extras_2_runs"]
    et = df["extras_type"].fillna("")
    df["is_wide"] = et.isin(cfg["wide_types"])
    df["is_noball"] = et.isin(cfg["noball_types"])
    df["legal"] = ~(df["is_wide"] | df["is_noball"])
    df["dismissed_striker"] = df["is_wicket"] & (df["dismissed_player_id"] == df["striker_id"])
    df["bat_faced"] = ~df["is_wide"] | df["dismissed_striker"]
    df["batter_out"] = df["dismissed_striker"] & ~df["dismissal_type"].isin(cfg["not_charged_to_batter"])
    df["bowler_wkt"] = df["is_wicket"] & ~df["dismissal_type"].isin(cfg["non_bowler_dismissals"])
    df["is_boundary"] = df["is_four"] | df["is_six"]
    df["is_ko"] = df["knock_out"].eq(1)

    # rain-revised overs are balls here; default full innings
    rv = np.where(df["innings"] == 1, df["first_inn_revised_overs"], df["second_inn_revised_overs"])
    df["max_balls"] = np.where(np.isnan(rv), cfg["full_innings_balls"],
                               rv if cfg["revised_overs_are_balls"] else rv * 6).astype(float)
    df["rain_revised"] = df["first_inn_revised_overs"].notna() | df["revised_target"].notna()

    # names (exactly as in data, keyed by ID)
    nm = {}
    for idc, nc in [("striker_id", "striker_name"), ("bowler_id", "bowler_name")]:
        for pid, name in df.groupby(idc)[nc].agg(lambda s: s.mode().iat[0]).items():
            nm.setdefault(pid, name)
    names = pd.Series(nm)
    summ.update({"ball_rows_clean": len(df), "matches_clean": int(df["match_id"].nunique()),
                 "players_batting": int(df["striker_id"].nunique()), "players_bowling": int(df["bowler_id"].nunique()),
                 "rain_revised_matches": int(df.loc[df["rain_revised"], "match_id"].nunique()),
                 "date_min": str(df["match_date"].min().date()), "date_max": str(df["match_date"].max().date())})
    return df, m, c, names, summ


# =====================================================================================
# STEP 2  MATCH STATE BEFORE EACH BALL
# =====================================================================================
def add_state(df, cfg):
    g = df.groupby(["match_id", "innings"], sort=False)
    df["score_before"] = g["total_runs"].cumsum() - df["total_runs"]
    df["wickets_before"] = g["is_wicket"].cumsum() - df["is_wicket"].astype(int)
    df["legal_before"] = g["legal"].cumsum() - df["legal"].astype(int)
    df["balls_left"] = (df["max_balls"] - df["legal_before"]).clip(lower=0)
    df["phase"] = np.select([df["overid"].between(*cfg["phases"]["Powerplay"]),
                             df["overid"].between(*cfg["phases"]["Middle"])], ["Powerplay", "Middle"], "Death")
    inn1_tot = df[df["innings"] == 1].groupby("match_id")["total_runs"].sum()
    df["inn1_total"] = df["match_id"].map(inn1_tot)
    df["target"] = np.where(df["revised_target"].notna(), df["revised_target"], df["inn1_total"] + 1)
    i2 = df["innings"] == 2
    df["runs_needed"] = np.where(i2, df["target"] - df["score_before"], np.nan)
    df["crr"] = np.where(df["legal_before"] > 0, df["score_before"] / df["legal_before"].replace(0, np.nan) * 6, 0.0)
    df["rrr"] = np.where(i2, np.where(df["balls_left"] > 0, df["runs_needed"] / df["balls_left"].replace(0, np.nan) * 6, 36.0), np.nan)
    df["rrr"] = df["rrr"].clip(lower=0, upper=36)
    # par curve for the first innings (average score before the ball at the same point of the innings)
    i1 = df[df["innings"] == 1]
    idx1 = np.clip(i1["legal_before"].values, 0, 119).astype(int)
    par = pd.Series(i1["score_before"].values).groupby(idx1).mean().reindex(range(120)).interpolate().values
    prog = np.clip(np.round(df["legal_before"] / df["max_balls"] * 120), 0, 119).astype(int)
    df["par_score"] = np.where(df["innings"] == 1, par[prog], np.nan)
    df["gap_to_par"] = df["par_score"] - df["score_before"]       # +ve = behind par
    STATE["par_curve"] = par
    # league 1st-innings run rate (centre of "close chase")
    cfg["pressure"]["_center"] = (cfg["pressure"]["close_center"] if cfg["pressure"]["close_center"]
                                  else float(i1["total_runs"].sum() / i1["legal"].sum() * 6))
    # is the match a tie on runs (excluded from win-probability work)?
    inn2_tot = df[df["innings"] == 2].groupby("match_id")["total_runs"].sum()
    tied = (inn2_tot == inn1_tot.reindex(inn2_tot.index))
    df["tied"] = df["match_id"].map(tied).fillna(False).astype(bool) | df["result"].str.contains("tied|super over", case=False, na=False)
    return df


# =====================================================================================
# STEP 3  PRESSURE SCORE
# =====================================================================================
def pressure_score(df, cfg):
    p = cfg["pressure"]
    w1, w2 = p["inn1"], p["inn2"]
    wk = df["wickets_before"].values / 10.0
    late = np.clip(df["legal_before"].values / df["max_balls"].values, 0, 1)
    rrr = df["rrr"].values
    stress = np.clip((rrr - p["rrr_lo"]) / (p["rrr_hi"] - p["rrr_lo"]), 0, 1)
    close = 1 - np.clip(np.abs(rrr - p["_center"]) / p["close_width"], 0, 1)
    behind = np.clip(df["gap_to_par"].values / p["par_gap_scale"], 0, 1)
    s2 = w2["rrr"] * stress + w2["wkts"] * wk + w2["late"] * late + w2["close"] * close
    s1 = w1["wkts"] * wk + w1["late"] * late + w1["par"] * behind
    return np.where(df["innings"].values == 2, s2, s1)


def hp_flag(ps, innings, q):
    s = pd.Series(ps)
    thr = s.groupby(innings.values).transform(lambda x: x.quantile(1 - q))
    return (s >= thr).values


# =====================================================================================
# STEP 4  EXPECTED RUNS + VALUE
# =====================================================================================
def expected_runs(df, cfg):
    k = cfg["expected"]["k"]
    df["wkt_bucket"] = pd.cut(df["wickets_before"], cfg["expected"]["wkt_edges"], right=False,
                              labels=False).astype(int)
    kc = ["comp_name", "innings", "phase", "wkt_bucket"]
    kf = ["match_format", "innings", "phase", "wkt_bucket"]
    for out, col, mask in [("exp_bat", "runs", df["bat_faced"]), ("exp_bowl", "total_runs", pd.Series(True, index=df.index))]:
        sub = df[mask]
        cell = sub.groupby(kc)[col].agg(s="sum", n="count")
        fb = sub.groupby(kf)[col].agg(fs="sum", fn="count")
        j = df[kc + ["match_format"]].join(cell, on=kc).join(fb, on=kf)
        own = df[col].where(mask, 0.0)
        n = j["n"].fillna(0) - mask.astype(int)
        s = j["s"].fillna(0) - own                                  # leave-one-out
        fmean = (j["fs"] / j["fn"]).fillna(df.loc[mask, col].mean())
        cm = (s / n.replace(0, np.nan)).fillna(fmean)
        df[out] = ((n * cm + k * fmean) / (n + k)).values
    return df


def add_values(df, wk):
    """returns (bat_val, bowl_val) arrays"""
    bat = (df["runs"] - df["exp_bat"] - wk * df["batter_out"].astype(float)).where(df["bat_faced"])
    bowl = df["exp_bowl"] - df["total_runs"] + wk * df["bowler_wkt"].astype(float)
    return bat.values, bowl.values


# =====================================================================================
# STEP 5  EXTRA SIGNALS
# =====================================================================================
def add_setback_flags(df, cfg):
    W = cfg["recovery"]["window"]
    g = df.groupby(["match_id", "innings"], sort=False)
    rec = np.zeros(len(df), bool)
    for k in range(1, W + 1):
        wk = g["is_wicket"].shift(k).fillna(False).astype(bool)
        s1, s2, dis = g["striker_id"].shift(k), g["non_striker_id"].shift(k), g["dismissed_player_id"].shift(k)
        surv = ((df["striker_id"] == s1) | (df["striker_id"] == s2)) & (df["striker_id"] != dis)
        rec |= (wk & surv).values
    df["rec_bat"] = rec & df["bat_faced"].values
    gb = df.groupby(["match_id", "innings", "overid", "bowler_id"], sort=False)
    df["rec_bowl"] = gb["is_boundary"].shift(1).fillna(False).astype(bool).values
    return df


def add_wpa(df, cfg):
    wc = cfg["wpa"]
    c = df[df["innings"] == 2].copy()
    c["ok"] = c["win_team_id"].notna() & ~c["tied"]
    c["y"] = (c["batting_team_id"] == c["win_team_id"]).astype(int)
    c["rn_a"] = c["runs_needed"] - c["total_runs"]
    c["bl_a"] = (c["balls_left"] - c["legal"].astype(int)).clip(lower=0)
    c["wk_a"] = (c["wickets_before"] + c["is_wicket"].astype(int)).clip(upper=10)
    c["rrr_a"] = np.where(c["bl_a"] > 0, c["rn_a"] / c["bl_a"].replace(0, np.nan) * 6, 36.0).clip(0, 36)
    c["rrr_b"] = c["rrr"]
    F_b = c[["runs_needed", "balls_left", "wickets_before", "rrr_b"]].values
    F_a = c[["rn_a", "bl_a", "wk_a", "rrr_a"]].values
    ok = c["ok"].values
    y = c["y"].values
    mk = lambda: HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08, max_depth=4, min_samples_leaf=60,
                                                early_stopping=False, random_state=cfg["seed"])
    # --- time-based hold-out: earliest 75% of matches train, latest 25% test
    mt = c[ok].groupby("match_id")["match_date"].first().sort_values(kind="stable")
    cut = int(len(mt) * (1 - wc["test_frac"]))
    train_m, test_m = set(mt.index[:cut]), set(mt.index[cut:])
    tr = ok & c["match_id"].isin(train_m).values
    te = ok & c["match_id"].isin(test_m).values
    mdl = mk().fit(F_b[tr], y[tr])
    pt = np.clip(mdl.predict_proba(F_b[te])[:, 1], 1e-4, 1 - 1e-4)
    base = np.full(te.sum(), y[tr].mean())
    met = {"split": "time-based (train earliest %d%% of chased matches, test latest %d%%)" % (round(100 * (1 - wc["test_frac"])), round(100 * wc["test_frac"])),
           "train_matches": len(train_m), "test_matches": len(test_m), "train_balls": int(tr.sum()), "test_balls": int(te.sum()),
           "test_accuracy": accuracy_score(y[te], pt > 0.5), "test_logloss": log_loss(y[te], pt),
           "test_brier": brier_score_loss(y[te], pt), "test_auc": roc_auc_score(y[te], pt),
           "baseline_logloss_constant": log_loss(y[te], base)}
    # --- out-of-fold (match-grouped) probabilities for every ball, so no ball is scored by a model that saw its match
    pb = np.full(len(c), np.nan)
    pa = np.full(len(c), np.nan)
    gkf = GroupKFold(n_splits=wc["n_splits"])
    idx_ok = np.where(ok)[0]
    for trn, tst in gkf.split(idx_ok, groups=c["match_id"].values[idx_ok]):
        m_ = mk().fit(F_b[idx_ok[trn]], y[idx_ok[trn]])
        pb[idx_ok[tst]] = m_.predict_proba(F_b[idx_ok[tst]])[:, 1]
        pa[idx_ok[tst]] = m_.predict_proba(F_a[idx_ok[tst]])[:, 1]
    won = c["rn_a"].values <= 0
    lost_end = (c["wk_a"].values >= 10) | (c["bl_a"].values <= 0)
    pa = np.where(won, 1.0, np.where(lost_end, y.astype(float), pa))
    pb = np.clip(pb, 1e-4, 1 - 1e-4)
    pa = np.clip(pa, 0, 1)
    met["oof_accuracy"] = accuracy_score(y[ok], pb[ok] > 0.5)
    met["oof_logloss"] = log_loss(y[ok], pb[ok])
    met["oof_auc"] = roc_auc_score(y[ok], pb[ok])
    delta = pa - pb
    lev = 4 * pb * (1 - pb)
    w = delta * (lev if wc["leverage"] else 1.0)
    w = np.where(ok, w, np.nan)
    df["wpa_p_before"] = np.nan
    df["wpa_delta"] = np.nan
    df["wpa_w"] = np.nan
    df.loc[c.index, "wpa_p_before"] = np.where(ok, pb, np.nan)
    df.loc[c.index, "wpa_delta"] = np.where(ok, delta, np.nan)
    df.loc[c.index, "wpa_w"] = w
    STATE["wpa_calib"] = pd.DataFrame({"p": pb[ok], "y": y[ok]})
    return df, met


# =====================================================================================
# STEP 6  RATING
# =====================================================================================
def make_core(df, hp, bat_val, bowl_val, cfg):
    core = df[["match_id", "match_order", "year", "innings", "striker_id", "bowler_id", "bat_faced", "wpa_w",
               "rec_bat", "rec_bowl", "comp_name", "is_ko"]].copy()
    core["hp"] = hp
    core["bat_val"] = bat_val
    core["bowl_val"] = bowl_val
    return core


def _z(s):
    sd = s.std(ddof=0)
    return (s - s.mean()) / sd if sd and np.isfinite(sd) and len(s) > 1 else s * 0.0


def rate(core, cfg, role, min_hp, wts=None, min_matches=None):
    wts = wts or cfg["rating_w"]
    min_matches = cfg["min_hp_matches"] if min_matches is None else min_matches
    k, kc, kw, kr = cfg["shrink_k"], cfg["consistency"]["k"], cfg["wpa"]["k"], cfg["recovery"]["k"]
    if role == "bat":
        d, pid, val, wcol, rcol, sign = core[core["bat_faced"]], "striker_id", "bat_val", "wpa_w", "rec_bat", 1.0
    else:
        d, pid, val, wcol, rcol, sign = core, "bowler_id", "bowl_val", "wpa_w", "rec_bowl", -1.0
    hp, nm = d[d["hp"]], d[~d["hp"]]
    if len(hp) == 0:
        return pd.DataFrame()
    t = hp.groupby(pid)[val].agg(n_hp="size", sum_hp="sum").join(
        nm.groupby(pid)[val].agg(n_norm="size", sum_norm="sum"), how="outer").fillna(0)
    lg_hp, lg_nm = hp[val].mean(), nm[val].mean()
    t["raw_hp_value"] = t["sum_hp"] / t["n_hp"].replace(0, np.nan)
    t["raw_norm_value"] = t["sum_norm"] / t["n_norm"].replace(0, np.nan)
    t["shrunk_hp_value"] = (t["sum_hp"] + k * lg_hp) / (t["n_hp"] + k)
    t["shrunk_norm_value"] = (t["sum_norm"] + k * lg_nm) / (t["n_norm"] + k)
    t["delta"] = t["shrunk_hp_value"] - t["shrunk_norm_value"]
    # consistency: share of matches (>= min HP balls) with positive pressure value, shrunk to league share
    mh = hp.groupby([pid, "match_id"])[val].agg(s="sum", n="size")
    mh = mh[mh["n"] >= cfg["consistency"]["min_hp_balls_match"]]
    pos = (mh["s"] > 0)
    lg_share = pos.mean() if len(pos) else 0.5
    cs = pos.groupby(level=0).agg(psum="sum", pn="count")
    t = t.join(cs)
    t["psum"], t["pn"] = t["psum"].fillna(0), t["pn"].fillna(0)
    t["consistency"] = (t["psum"] + kc * lg_share) / (t["pn"] + kc)
    t = t.rename(columns={"pn": "hp_matches"})
    # WPA (chases only; batter +, bowler -)
    ch = d[d["innings"] == 2].dropna(subset=[wcol])
    ws = (sign * ch[wcol]).groupby(ch[pid]).agg(wsum="sum", chase_balls="count")
    t = t.join(ws)
    t["wsum"], t["chase_balls"] = t["wsum"].fillna(0), t["chase_balls"].fillna(0)
    t["wpa_shrunk"] = t["wsum"] / (t["chase_balls"] + kw)
    # setback recovery vs league average in same situation
    r = d[d[rcol]].dropna(subset=[val])
    lg_r = r[val].mean()
    rs = (r[val] - lg_r).groupby(r[pid]).agg(rsum="sum", rec_balls="count")
    t = t.join(rs)
    t["rsum"], t["rec_balls"] = t["rsum"].fillna(0), t["rec_balls"].fillna(0)
    t["recovery"] = t["rsum"] / (t["rec_balls"] + kr)
    t["matches"] = d.groupby(pid)["match_id"].nunique()
    t["ipl_share_hp"] = hp.assign(ipl=hp["comp_name"].str.startswith("IPL")).groupby(pid)["ipl"].mean()
    t["a_team_share_hp"] = hp["comp_name"].str.contains(cfg["a_team_regex"]).groupby(hp[pid]).mean()
    e = t[(t["n_hp"] >= min_hp) & (t["hp_matches"] >= min_matches)].copy()
    if len(e) < 3:
        return e.assign(rating=np.nan)
    for c_, zc in [("shrunk_hp_value", "z_value"), ("delta", "z_delta"), ("consistency", "z_consistency"),
                   ("wpa_shrunk", "z_wpa"), ("recovery", "z_recovery")]:
        e[zc] = _z(e[c_])
    e["rating"] = (wts["value"] * e["z_value"] + wts["delta"] * e["z_delta"] + wts["consistency"] * e["z_consistency"]
                   + wts["wpa"] * e["z_wpa"] + wts["recovery"] * e["z_recovery"])
    e = e.sort_values("rating", ascending=False)
    e["rank"] = np.arange(1, len(e) + 1)
    e.index.name = "player_id"
    return e


def pipeline_core(df, cfg):
    """pressure -> HP flag -> values -> slim core table (used for base and every scenario)"""
    ps = pressure_score(df, cfg)
    hp = hp_flag(ps, df["innings"], cfg["hp_quantile"])
    bv, wv = add_values(df, cfg["wk"])
    return make_core(df, hp, bv, wv, cfg), ps


def resolve_exclusions(names, cfg):
    """name -> exact id; stops loudly if a configured name/ID does not match the data."""
    out = {}
    for src, dct in [("retired", cfg["retired_exclude"]), ("retained", cfg["retained_exclude"]), ("manual", cfg["manual_exclude"])]:
        for nm, reason in dct.items():
            if nm not in cfg["exclude_ids"]:
                raise SystemExit(f"Excluded player '{nm}' has no ID in EXCLUDE_IDS - confirm the ID first.")
            pid = cfg["exclude_ids"][nm]
            if names.get(pid) != nm:
                raise SystemExit(f"Excluded player '{nm}' (id {pid}) does not match the data name '{names.get(pid)}'.")
            status = cfg["exclude_status"].get(nm, {"retained": "Retained (official)", "manual": "Excluded by selector"}.get(src, "Unverified"))
            out[pid] = dict(player_name=nm, reason=reason, availability_status=status, source=src)
    mp = pd.read_csv(cfg["data_dir"] / "competition_team_player_mapping.csv")
    for key, rule in cfg["nationality_exclude"].items():
        ids = set(mp.loc[mp["team_name"].str.contains(rule["team_regex"], regex=True), "player_id"])
        for pid in sorted(ids):
            if pid in names.index and pid not in out:
                out[pid] = dict(player_name=names[pid], reason=rule["reason"], availability_status=rule["status"], source="nationality")
    return out


def top_ids(core, cfg, role, min_hp, n=10, wts=None, min_matches=None, exclude=None):
    """Rate the full pool (so z-scores and baselines are unaffected), THEN drop unavailable players and re-rank."""
    t = rate(core, cfg, role, min_hp, wts, min_matches)
    if len(t) and exclude:
        t = t[~t.index.isin(list(exclude))].copy()
        t["rank"] = np.arange(1, len(t) + 1)
    return (list(t.index[:n]) if len(t) else []), t


# =====================================================================================
# STEP 7  YEAR BY YEAR, BIG GAME, SERIES
# =====================================================================================
def season_ratings(core, cfg, role, ids):
    mins = cfg["season_min_hp"]["bat" if role == "bat" else "bowl"]
    rows = {}
    for y in sorted(core["year"].unique()):
        t = rate(core[core["year"] == y], cfg, role, mins, min_matches=0)
        if len(t) >= 5:
            rows[int(y)] = t["rating"]
    piv = pd.DataFrame(rows).reindex(ids)
    return piv


def season_stats(piv):
    out = pd.DataFrame(index=piv.index)
    out["seasons_rated"] = piv.notna().sum(axis=1)
    out["share_seasons_above_avg"] = (piv > 0).sum(axis=1) / out["seasons_rated"].replace(0, np.nan)
    out["rating_variability_sd"] = piv.std(axis=1, ddof=0).where(out["seasons_rated"] >= 2)
    def slope(r):
        r = r.dropna()
        return np.polyfit(r.index.astype(float), r.values, 1)[0] if len(r) >= 3 else np.nan
    out["trend_slope_per_year"] = piv.apply(slope, axis=1)
    return out


def big_game(df, cfg, role, ids):
    pid, val = ("striker_id", "bat_val") if role == "bat" else ("bowler_id", "bowl_val")
    d = df[df["bat_faced"]] if role == "bat" else df
    d = d[d[pid].isin(ids)]
    k = cfg["knockout_k"]
    rows = []
    for p in ids:
        x = d[d[pid] == p]
        ko, nk = x[x["is_ko"]], x[~x["is_ko"]]
        nmean = nk[val].mean() if len(nk) else 0.0
        shr = (ko[val].sum() + k * nmean) / (len(ko) + k) if len(ko) else nmean
        rows.append(dict(player_id=p, ko_innings=ko["match_id"].nunique() if len(ko) else 0,
                         ko_balls=len(ko), normal_balls=len(nk),
                         ko_value_per_ball_raw=ko[val].mean() if len(ko) else np.nan,
                         normal_value_per_ball=nmean,
                         ko_value_shrunk_to_own_baseline=shr, ko_minus_normal_shrunk=shr - nmean))
    return pd.DataFrame(rows).set_index("player_id")


def series_totals(df, role, ids, hpcol):
    pid = "striker_id" if role == "bat" else "bowler_id"
    d = df[df[pid].isin(ids)]
    d = d[d["bat_faced"]] if role == "bat" else d
    val = "bat_val" if role == "bat" else "bowl_val"
    g = d.groupby([pid, "comp_name", "year"])
    if role == "bat":
        o = g.agg(matches=("match_id", "nunique"), balls=("bat_faced", "sum"), runs=("runs", "sum"),
                  dismissals=("batter_out", "sum"), hp_balls=(hpcol, "sum"), total_value=(val, "sum"))
        o["strike_rate"] = o["runs"] / o["balls"] * 100
    else:
        o = g.agg(matches=("match_id", "nunique"), deliveries=("legal", "size"), legal_balls=("legal", "sum"),
                  runs_conceded=("total_runs", "sum"), wickets=("bowler_wkt", "sum"), hp_balls=(hpcol, "sum"),
                  total_value=(val, "sum"))
        o["economy"] = o["runs_conceded"] / o["legal_balls"].replace(0, np.nan) * 6
    return o.reset_index()


def winning_contribution(df, role, ids):
    pid, tid = ("striker_id", "batting_team_id") if role == "bat" else ("bowler_id", "bowling_team_id")
    val = "bat_val" if role == "bat" else "bowl_val"
    d = df[df[pid].isin(ids) & df["hp"] & df["win_team_id"].notna()]
    if role == "bat":
        d = d[d["bat_faced"]]
    d = d.assign(team_won=(d[tid] == d["win_team_id"]))
    g = d.groupby([pid, "team_won"])[val].agg(["mean", "size"]).unstack("team_won")
    out = pd.DataFrame(index=g.index)
    out["hp_value_in_wins"] = g[("mean", True)]
    out["hp_balls_in_wins"] = g[("size", True)]
    out["hp_value_in_losses"] = g[("mean", False)]
    out["hp_balls_in_losses"] = g[("size", False)]
    out["win_minus_loss"] = out["hp_value_in_wins"] - out["hp_value_in_losses"]
    return out.reindex(ids)


def role_views(df, cfg, names, bat_tab, bowl_tab):
    mb = cfg["role_min_balls"]
    k = cfg["shrink_k"]
    def shrunk(mask, pid, val, label, minb):
        d = df[mask].dropna(subset=[val])
        lg = d[val].mean()
        g = d.groupby(pid)[val].agg(n="size", s="sum")
        g = g[g["n"] >= minb]
        g[label] = (g["s"] + k * lg) / (g["n"] + k)
        g["raw"] = g["s"] / g["n"]
        g["player_name"] = g.index.map(names)
        return g.sort_values(label, ascending=False).head(10)[["player_name", "n", "raw", label]]
    out = {}
    out["finishers_bat"] = shrunk(df["bat_faced"] & (df["innings"] == 2) & (df["overid"] >= 16) & (df["rrr"] > 10),
                                  "striker_id", "bat_val", "shrunk_value", mb)
    out["rebuilders_bat"] = shrunk(df["bat_faced"] & (df["phase"] == "Powerplay") & (df["wickets_before"] >= 2),
                                   "striker_id", "bat_val", "shrunk_value", mb)
    out["death_defenders_bowl"] = shrunk((df["innings"] == 2) & (df["phase"] == "Death"),
                                         "bowler_id", "bowl_val", "shrunk_value", mb)
    for typ in ["Pace", "Spin"]:
        out[f"bat_hp_vs_{typ.lower()}"] = shrunk(df["bat_faced"] & df["hp"] & (df["pace_or_spin"] == typ),
                                                  "striker_id", "bat_val", "shrunk_value", mb // 2)
        out[f"bowl_hp_{typ.lower()}_bowlers"] = shrunk(df["hp"] & (df["pace_or_spin"] == typ),
                                                       "bowler_id", "bowl_val", "shrunk_value", mb // 2)
    return out


# =====================================================================================
# STEP 8  RELIABILITY
# =====================================================================================
def overlap_stats(a, b, ta, tb):
    common = ta.index.intersection(tb.index)
    rho = spearmanr(ta.loc[common, "rating"], tb.loc[common, "rating"])[0] if len(common) >= 5 else np.nan
    return dict(top10_overlap=len(set(a) & set(b)), n_common_eligible=len(common), spearman=rho)


def scenarios(cfg):
    S = {"base": {}}
    def ov(name, **kw):
        S[name] = kw
    p = lambda **k: {"pressure": k}
    ov("inn2 weights: rate-heavy (.55/.15/.15/.15)", pressure={"inn2": dict(rrr=.55, wkts=.15, late=.15, close=.15)})
    ov("inn2 weights: wickets-heavy (.25/.40/.20/.15)", pressure={"inn2": dict(rrr=.25, wkts=.40, late=.20, close=.15)})
    ov("inn2 weights: late+close (.30/.20/.25/.25)", pressure={"inn2": dict(rrr=.30, wkts=.20, late=.25, close=.25)})
    ov("inn1 weights: par-heavy (.20/.30/.50)", pressure={"inn1": dict(wkts=.20, late=.30, par=.50)})
    ov("inn1 weights: wickets-heavy (.50/.30/.20)", pressure={"inn1": dict(wkts=.50, late=.30, par=.20)})
    ov("HP cutoff 20%", hp_quantile=0.20)
    ov("HP cutoff 30%", hp_quantile=0.30)
    ov("WK = 6", wk=6.0)
    ov("WK = 10", wk=10.0)
    ov("min balls -33% (bat 80 / bowl 67)", min_hp=dict(bat=80, bowl=67))
    ov("min balls +33% (bat 160 / bowl 133)", min_hp=dict(bat=160, bowl=133))
    ov("WPA weight 0", rating_w=dict(value=1.0, delta=.5, consistency=.5, wpa=0.0, recovery=.25))
    ov("WPA weight 1.0", rating_w=dict(value=1.0, delta=.5, consistency=.5, wpa=1.0, recovery=.25))
    ov("shrinkage k = 50", shrink_k=50)
    ov("shrinkage k = 200", shrink_k=200)
    ov("shrinkage k = 400", shrink_k=400)
    ov("min HP matches 25", min_hp_matches=25)
    ov("exclude A-team events", exclude_regex=True)
    return S


def merge_cfg(base, over):
    c = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(c.get(k), dict):
            for kk, vv in v.items():
                c[k][kk] = vv
        else:
            c[k] = v
    return c


def reliability_diag(core, cfg, role, min_hp):
    d = core[core["bat_faced"]] if role == "bat" else core
    pid, val = ("striker_id", "bat_val") if role == "bat" else ("bowler_id", "bowl_val")
    hp = d[d["hp"]]
    a = hp[hp["match_order"] % 2 == 1].groupby(pid)[val].agg(m="mean", n="size")
    b = hp[hp["match_order"] % 2 == 0].groupby(pid)[val].agg(m="mean", n="size")
    j = a.join(b, lsuffix="_o", rsuffix="_e", how="inner")
    j = j[(j["n_o"] >= 30) & (j["n_e"] >= 30)]
    r = np.corrcoef(j["m_o"], j["m_e"])[0, 1]
    n = hp.groupby(pid).size()
    means = hp.groupby(pid)[val].mean()
    el = n[n >= min_hp].index
    sigma2 = hp[val].var()
    var_obs = means[el].var()
    noise = (sigma2 / n[el]).mean()
    var_true = max(var_obs - noise, 1e-6)
    return dict(role=role, ball_sd=float(np.sqrt(sigma2)), players_split_half=len(j), split_half_r=float(r),
                spearman_brown_r=float(2 * r / (1 + r)), var_observed=float(var_obs), var_noise=float(noise),
                share_true_signal=float(var_true / var_obs), eb_k_estimate=float(sigma2 / var_true))


# =====================================================================================
# CHARTS / TABLES
# =====================================================================================
def pressure_validation(df, hp):
    d = df.assign(hp=hp)
    rows = []
    def stat(x, label, inn, grp):
        f = x[x["bat_faced"]]
        rows.append(dict(innings=inn, group=grp, segment=label, deliveries=len(x),
                         strike_rate=f["runs"].sum() / max(len(f), 1) * 100,
                         dot_pct=(x["total_runs"] == 0).mean() * 100,
                         wickets_per_100=x["is_wicket"].sum() / len(x) * 100,
                         runs_per_ball=x["total_runs"].mean(),
                         bat_value_per_ball=x["bat_val"].mean(), bowl_value_per_ball=x["bowl_val"].mean()))
    for inn in [1, 2, "both"]:
        x0 = d if inn == "both" else d[d["innings"] == inn]
        for g, lab in [(True, "High pressure"), (False, "Normal")]:
            stat(x0[x0["hp"] == g], lab, inn, "all balls")
    for inn in [1, 2]:
        for ph in ["Powerplay", "Middle", "Death"]:
            for g, lab in [(True, "High pressure"), (False, "Normal")]:
                x = d[(d["innings"] == inn) & (d["phase"] == ph) & (d["hp"] == g)]
                if len(x) > 200:
                    stat(x, lab, inn, ph)
    return pd.DataFrame(rows)


def chart_validation(tab):
    fig, axes = plt.subplots(2, 3, figsize=(10, 5.6))
    mets = [("strike_rate", "Strike rate (runs/100 balls faced)"), ("dot_pct", "Dot balls (%)"),
            ("wickets_per_100", "Wickets per 100 balls")]
    a = tab[tab["group"] == "all balls"]
    for j, (m_, ttl) in enumerate(mets):
        ax = axes[0, j]
        xs = np.arange(3)
        for i, (lab, col) in enumerate([("Normal", NM_COL), ("High pressure", HP_COL)]):
            v = [a[(a["innings"] == inn) & (a["segment"] == lab)][m_].iat[0] for inn in [1, 2, "both"]]
            ax.bar(xs + (i - .5) * .36, v, .36, color=col, label=lab)
            for x_, v_ in zip(xs + (i - .5) * .36, v):
                ax.text(x_, v_, f"{v_:.1f}", ha="center", va="bottom", fontsize=7)
        ax.set_xticks(xs, ["Innings 1", "Innings 2", "Both"])
        ax.set_title(ttl)
        if j == 0:
            ax.legend(frameon=False, fontsize=8)
    ph = tab[tab["group"] != "all balls"]
    for j, (m_, ttl) in enumerate(mets):
        ax = axes[1, j]
        labs = [(inn, p) for inn in [1, 2] for p in ["Powerplay", "Middle", "Death"]]
        xs = np.arange(len(labs))
        for i, (lab, col) in enumerate([("Normal", NM_COL), ("High pressure", HP_COL)]):
            v = []
            for inn, p_ in labs:
                r = ph[(ph["innings"] == inn) & (ph["group"] == p_) & (ph["segment"] == lab)]
                v.append(r[m_].iat[0] if len(r) else np.nan)
            ax.bar(xs + (i - .5) * .36, v, .36, color=col)
        ax.set_xticks(xs, [f"I{i} {p[:2] if p != 'Middle' else 'Mid'}" for i, p in labs], fontsize=7)
        ax.set_title(ttl + "\nwithin the same phase", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "pressure_validation.png")
    plt.close(fig)


def chart_calibration(met):
    cal = STATE["wpa_calib"]
    cal["bin"] = pd.cut(cal["p"], np.linspace(0, 1, 11))
    g = cal.groupby("bin", observed=True).agg(p=("p", "mean"), y=("y", "mean"), n=("y", "size"))
    fig, ax = plt.subplots(figsize=(4.2, 3.6))
    ax.plot([0, 1], [0, 1], color="#999", ls="--", lw=1)
    ax.plot(g["p"], g["y"], "o-", color=NM_COL)
    ax.set_xlabel("Predicted chase win probability (out-of-fold)")
    ax.set_ylabel("Observed win rate")
    ax.set_title("Win-probability model calibration")
    fig.tight_layout()
    fig.savefig(OUT / "wpa_calibration.png")
    plt.close(fig)


def chart_top10(tab, role, names, title, fname):
    t = tab.head(10).iloc[::-1]
    w = CONFIG["rating_w"]
    comps = [("z_value", w["value"], "Shrunk pressure value", "#0072B2"), ("z_delta", w["delta"], "Delta vs own baseline", "#E69F00"),
             ("z_consistency", w["consistency"], "Consistency", "#009E73"), ("z_wpa", w["wpa"], "Shrunk WPA (chases)", "#CC79A7"),
             ("z_recovery", w["recovery"], "Setback recovery", "#56B4E9")]
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    pos = np.zeros(len(t))
    neg = np.zeros(len(t))
    y = np.arange(len(t))
    for c, wt, lab, col in comps:
        v = (t[c] * wt).values
        left = np.where(v >= 0, pos, neg)
        ax.barh(y, v, left=left, color=col, label=lab, height=.7)
        pos += np.where(v >= 0, v, 0)
        neg += np.where(v < 0, v, 0)
    ax.set_yticks(y, [f"{names[i]}  (n={int(n)})" for i, n in zip(t.index, t["n_hp"])])
    ax.axvline(0, color="#444", lw=.8)
    ax.set_xlabel("Weighted z-score contribution to rating   (n = high-pressure balls)")
    ax.set_title(title)
    ax.legend(frameon=False, fontsize=7, loc="lower right")
    fig.tight_layout()
    fig.savefig(OUT / fname)
    plt.close(fig)


def chart_heatmap(piv, names, title, fname):
    d = piv.copy()
    d.index = [names[i] for i in d.index]
    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    sns.heatmap(d, annot=True, fmt=".1f", cmap="RdBu_r", center=0, ax=ax, linewidths=.5, linecolor="white",
                cbar_kws={"label": "Season rating (z-composite)"}, annot_kws={"size": 8})
    ax.set_xlabel("Season (calendar year)")
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(OUT / fname)
    plt.close(fig)


def chart_sensitivity(freq_b, freq_w, nscen, names):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, f, ttl in [(axes[0], freq_b, "Batters"), (axes[1], freq_w, "Bowlers")]:
        f = f.head(15).iloc[::-1]
        ax.barh([names[i] for i in f.index], f["share_in_top10"] * 100,
                color=[HP_COL if b else "#999" for b in f["in_base_top10"]])
        ax.set_xlabel(f"% of {nscen} scenarios in top 10")
        ax.set_title(f"{ttl}: robustness (orange = in base top 10)")
    fig.tight_layout()
    fig.savefig(OUT / "sensitivity_robustness.png")
    plt.close(fig)


def chart_stability(rows):
    fig, ax = plt.subplots(figsize=(6, 3.2))
    labs = [r["label"] for r in rows]
    ax.bar(labs, [r["top10_overlap"] for r in rows], color=NM_COL)
    for i, r in enumerate(rows):
        ax.text(i, r["top10_overlap"] + .15, f"rho={r['spearman']:.2f}", ha="center", fontsize=7)
    ax.set_ylabel("Top-10 overlap (of 10)")
    ax.set_ylim(0, 11)
    plt.setp(ax.get_xticklabels(), rotation=15, ha="right", fontsize=7)
    ax.set_title("Stability of the top 10")
    fig.tight_layout()
    fig.savefig(OUT / "stability.png")
    plt.close(fig)


def chart_delta(tab, names, role, fname):
    t = tab.head(10)
    fig, ax = plt.subplots(figsize=(5.2, 3.6))
    ax.scatter(t["shrunk_norm_value"], t["shrunk_hp_value"], s=t["n_hp"] / 3, color=HP_COL, alpha=.75)
    lim = [min(t["shrunk_norm_value"].min(), t["shrunk_hp_value"].min()) - .02, max(t["shrunk_norm_value"].max(), t["shrunk_hp_value"].max()) + .02]
    ax.plot(lim, lim, "--", color="#888", lw=1)
    for i, r in t.iterrows():
        ax.annotate(names[i].split()[-1], (r["shrunk_norm_value"], r["shrunk_hp_value"]), fontsize=7, xytext=(3, 3), textcoords="offset points")
    ax.set_xlabel("Normal-ball value per ball (own baseline)")
    ax.set_ylabel("High-pressure value per ball")
    ax.set_title(f"Top-10 {role}: pressure vs baseline (bubble = HP balls)")
    fig.tight_layout()
    fig.savefig(OUT / fname)
    plt.close(fig)


# =====================================================================================
# PLAYER PROFILE
# =====================================================================================
def player_profile(name):
    """Return everything we know about a player (case-insensitive substring of the data name)."""
    S = STATE
    names = S["names"]
    hits = [i for i, n in names.items() if name.lower() in n.lower()]
    if not hits:
        return f"No player matching '{name}'"
    exact = [i for i in hits if names[i].lower() == name.lower()]
    pid = (exact or hits)[0]
    out = {"player_id": int(pid), "name": names[pid], "other_matches": [names[i] for i in hits if i != pid][:5]}
    for role, tab_key in [("bat", "bat_all"), ("bowl", "bowl_all")]:
        tab = S[tab_key]
        if pid in tab.index:
            row = tab.loc[pid]
            out[f"{role}_rating"] = {k: (float(v) if isinstance(v, (int, float, np.floating, np.integer)) else v) for k, v in row.items()}
        sr = S[f"{role}_season_all"]
        if pid in sr.index:
            out[f"{role}_season_ratings"] = sr.loc[pid].dropna().to_dict()
        ts = S[f"{role}_series_all"]
        s = ts[ts[("striker_id" if role == "bat" else "bowler_id")] == pid]
        if len(s):
            out[f"{role}_series_totals"] = s.drop(columns=["striker_id" if role == "bat" else "bowler_id"]).to_dict("records")
        bg = S[f"{role}_bigame_all"]
        if pid in bg.index:
            out[f"{role}_knockout_vs_normal"] = bg.loc[pid].to_dict()
        wc = S[f"{role}_win_all"]
        if pid in wc.index:
            out[f"{role}_winning_contribution"] = wc.loc[pid].to_dict()
    return out




# =====================================================================================
# SHAP EXPLAINABILITY
# =====================================================================================
WPA_FEATS = ["runs_needed", "balls_left", "wickets_before", "rrr"]
WPA_LABEL = {"runs_needed": "Runs needed", "balls_left": "Balls left", "wickets_before": "Wickets lost", "rrr": "Required rate"}
RATING_COMPONENTS = [("z_value", "shrunk_hp_value", "Pressure value", "value"), ("z_delta", "delta", "Lift over own baseline", "delta"),
                     ("z_consistency", "consistency", "Consistency", "consistency"), ("z_wpa", "wpa_shrunk", "Win probability added", "wpa"),
                     ("z_recovery", "recovery", "Setback recovery", "recovery")]


def shap_outputs(df, bat_tab, bowl_tab, top_b_ids, top_w_ids, names, cfg):
    """(1) SHAP of the win-probability model (probability points, exact Shapley, 4 features);
       (2) per-ball SHAP decomposition of each top player's biggest pressure moments;
       (3) exact Shapley decomposition of the rating via shap.LinearExplainer (+ waterfall charts)."""
    SH = OUT / "shap"
    SH.mkdir(exist_ok=True)
    sc = cfg["shap"]
    rng = np.random.RandomState(cfg["seed"])
    teams = pd.read_csv(cfg["data_dir"] / "teams.csv").drop_duplicates("team_id").set_index("team_id")["team_name"]
    c = df[(df["innings"] == 2) & df["win_team_id"].notna() & ~df["tied"]].copy()
    y = (c["batting_team_id"] == c["win_team_id"]).astype(int).values
    X = c[WPA_FEATS].values
    mdl = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08, max_depth=4, min_samples_leaf=60,
                                         early_stopping=False, random_state=cfg["seed"]).fit(X, y)
    f = lambda a: mdl.predict_proba(a)[:, 1]
    bg = X[rng.choice(len(X), sc["background"], replace=False)]
    expl = shap.Explainer(f, bg, algorithm="exact")
    # ---- global
    samp = rng.choice(len(X), sc["sample"], replace=False)
    ex = expl(X[samp])
    vals = ex.values * 100.0
    labels = [WPA_LABEL[k] for k in WPA_FEATS]
    imp = pd.DataFrame({"feature": WPA_FEATS, "label": labels, "mean_abs_shap_pp": np.abs(vals).mean(axis=0)})
    imp["direction_spearman"] = [spearmanr(X[samp][:, j], vals[:, j])[0] for j in range(len(WPA_FEATS))]
    imp["higher_value_effect"] = np.where(imp["direction_spearman"] > 0, "raises win probability", "lowers win probability")
    imp = imp.sort_values("mean_abs_shap_pp", ascending=False)
    imp.to_csv(SH / "wpa_global_importance.csv", index=False)
    dep = []
    for j, k in enumerate(WPA_FEATS):
        b = pd.qcut(X[samp][:, j], sc["dep_bins"], duplicates="drop")
        g = pd.DataFrame({"x": X[samp][:, j], "s": vals[:, j], "b": b}).groupby("b", observed=True).agg(x=("x", "mean"), shap_pp=("s", "mean"), n=("s", "size"))
        for _, r in g.iterrows():
            dep.append(dict(feature=k, label=WPA_LABEL[k], x=float(r["x"]), shap_pp=float(r["shap_pp"]), n=int(r["n"])))
    dep = pd.DataFrame(dep)
    dep.to_csv(SH / "wpa_dependence_binned.csv", index=False)
    plt.figure(figsize=(7, 3.4))
    shap.plots.beeswarm(shap.Explanation(values=vals, base_values=ex.base_values * 100, data=X[samp], feature_names=labels), show=False, plot_size=None)
    plt.xlabel("SHAP value: change in chase win probability (percentage points)")
    plt.tight_layout()
    plt.savefig(SH / "wpa_beeswarm.png", dpi=130)
    plt.close("all")
    fig, axes = plt.subplots(1, 4, figsize=(11, 2.6), sharey=True)
    for ax, k in zip(axes, WPA_FEATS):
        d_ = dep[dep["feature"] == k]
        ax.plot(d_["x"], d_["shap_pp"], "o-", color=NM_COL, ms=3)
        ax.axhline(0, color="#999", lw=.8)
        ax.set_title(WPA_LABEL[k], fontsize=9)
    axes[0].set_ylabel("SHAP (pp win prob.)")
    fig.tight_layout()
    fig.savefig(SH / "wpa_dependence.png", dpi=130)
    plt.close(fig)
    # ---- per-ball moments for each top player
    rn_a = c["runs_needed"] - c["total_runs"]
    bl_a = (c["balls_left"] - c["legal"].astype(int)).clip(lower=0)
    wk_a = (c["wickets_before"] + c["is_wicket"].astype(int)).clip(upper=10)
    rrr_a = np.where(bl_a > 0, rn_a / bl_a.replace(0, np.nan) * 6, 36.0)
    rrr_a = np.clip(np.nan_to_num(rrr_a, nan=36.0), 0, 36)
    Xa = np.column_stack([rn_a, bl_a, wk_a, rrr_a])
    c["p_b"], c["p_a"] = f(X), f(Xa)
    c["nonterminal"] = ((rn_a > 0) & (wk_a < 10) & (bl_a > 0)).values
    c["d"] = c["p_a"] - c["p_b"]
    mrows, max_err = [], 0.0
    for role, ids, idc, sign in [("batter", top_b_ids, "striker_id", 1.0), ("bowler", top_w_ids, "bowler_id", -1.0)]:
        for rk, pid in enumerate(ids, 1):
            x_ = c[(c[idc] == pid) & c["nonterminal"]]
            x_ = x_.assign(imp=sign * x_["d"]).sort_values("imp", ascending=False).head(sc["moments_per_player"])
            for ix, r in x_.iterrows():
                pos = c.index.get_loc(ix)
                sb, sa = expl(X[pos:pos + 1]).values[0] * 100, expl(Xa[pos:pos + 1]).values[0] * 100
                dr = sign * (sa - sb)
                tot = sign * (r["p_a"] - r["p_b"]) * 100
                max_err = max(max_err, abs(dr.sum() - tot))
                out = ("wicket (" + str(r["dismissal_type"]) + ")") if r["is_wicket"] else ("six" if r["is_six"] else "four" if r["is_four"] else
                       ("wide" if r["is_wide"] else f"{int(r['total_runs'])} run" + ("" if r["total_runs"] == 1 else "s")))
                order = np.argsort(-np.abs(dr))
                mrows.append(dict(role=role, final_rank=rk, player_id=pid, player_name=names[pid],
                                  match_date=str(r["match_date"])[:10], competition=r["comp_name"],
                                  vs=teams.get(r["bowling_team_id"] if role == "batter" else r["batting_team_id"], ""),
                                  over=int(r["overid"]), outcome=out, runs_needed=int(r["runs_needed"]), balls_left=int(r["balls_left"]),
                                  wickets_lost=int(r["wickets_before"]),
                                  win_prob_before_pct=float(r["p_b"] * 100 if role == "batter" else (1 - r["p_b"]) * 100),
                                  win_prob_after_pct=float(r["p_a"] * 100 if role == "batter" else (1 - r["p_a"]) * 100),
                                  impact_pp=float(tot),
                                  driver1=WPA_LABEL[WPA_FEATS[order[0]]], driver1_pp=float(dr[order[0]]),
                                  driver2=WPA_LABEL[WPA_FEATS[order[1]]], driver2_pp=float(dr[order[1]]),
                                  shap_runs_needed_pp=float(dr[0]), shap_balls_left_pp=float(dr[1]), shap_wickets_pp=float(dr[2]), shap_rrr_pp=float(dr[3])))
    mom = pd.DataFrame(mrows)
    mom.to_csv(SH / "key_moments.csv", index=False)
    # ---- rating decomposition (exact Shapley for the additive rating) with shap.LinearExplainer
    w = cfg["rating_w"]
    coef = np.array([w[k] for _, _, _, k in RATING_COMPONENTS])
    rrows, rating_err = [], 0.0
    for role, tab, ids in [("batter", bat_tab, top_b_ids), ("bowler", bowl_tab, top_w_ids)]:
        zc = [a for a, _, _, _ in RATING_COMPONENTS]
        rc = [b for _, b, _, _ in RATING_COMPONENTS]
        lin = shap.LinearExplainer((coef, 0.0), tab[zc].values)
        sv = lin.shap_values(tab.loc[ids, zc].values)
        base = float(np.ravel(lin.expected_value)[0])
        rating_err = max(rating_err, float(np.abs(sv.sum(axis=1) + base - tab.loc[ids, "rating"].values).max()))
        pool_mean = tab[rc].mean()
        for i_, pid in enumerate(ids):
            for j, (a, b, lab, k) in enumerate(RATING_COMPONENTS):
                rrows.append(dict(role=role, final_rank=i_ + 1, player_id=pid, player_name=names[pid], component=lab, weight=coef[j],
                                  player_value=float(tab.loc[pid, b]), rated_player_average=float(pool_mean[b]), z_score=float(tab.loc[pid, a]),
                                  shap_contribution=float(sv[i_, j]), base_value=base, rating=float(tab.loc[pid, "rating"])))
            vals_ = sv[i_]
            plt.figure(figsize=(6.2, 3.2))
            shap.plots.waterfall(shap.Explanation(values=vals_, base_values=base, data=tab.loc[pid, rc].values.astype(float),
                                                  feature_names=[lab for _, _, lab, _ in RATING_COMPONENTS]), show=False, max_display=6)
            plt.title(f"{names[pid]} ({role}, final #{i_ + 1})", fontsize=10)
            plt.tight_layout()
            plt.savefig(SH / f"waterfall_{role}_{i_ + 1:02d}_{re.sub('[^A-Za-z0-9]+', '_', names[pid])}.png", dpi=120)
            plt.close("all")
    rr = pd.DataFrame(rrows)
    rr.to_csv(SH / "rating_shap.csv", index=False)
    met = dict(wpa_balls_used=len(c), shap_sample=sc["sample"], background=sc["background"], decomposition_max_abs_error_pp=max_err,
               rating_decomposition_max_abs_error=rating_err, n_moments=len(mom))
    pd.Series(met).to_csv(SH / "shap_checks.csv", header=["value"])
    log("   SHAP checks:", {k: (round(v, 8) if isinstance(v, float) else v) for k, v in met.items()})
    return dict(importance=imp, dependence=dep, moments=mom, rating_shap=rr, metrics=met)

# =====================================================================================
# AVAILABILITY LOG + CHECKS
# =====================================================================================
def availability_outputs(bat_tab, bowl_tab, bat_all, bowl_all, excl, top_b_ids, top_w_ids, fb, fw, names, cfg, top20_b_ids=None, top20_w_ids=None):
    """excluded_log.csv + new_entrants.csv (all derived from the final-ranking stage only)."""
    d10b = list(bat_tab.index[:10])
    d10w = list(bowl_tab.index[:10])
    ent_b = [i for i in top_b_ids if i not in d10b]
    ent_w = [i for i in top_w_ids if i not in d10w]
    rows = []
    for pid, e in excl.items():
        def info(tab, allt):
            if pid in tab.index:
                return int(tab.loc[pid, "data_rank"]), "rated (eligible pool)"
            if pid in allt.index:
                r = allt.loc[pid]
                return np.nan, f"not in eligible pool ({int(r['n_hp'])} HP balls, {int(r['hp_matches'])} HP matches; below minimums)"
            return np.nan, "no ball data in this role"
        br, bs = info(bat_tab, bat_all)
        wr, ws = info(bowl_tab, bowl_all)
        rows.append(dict(player=e["player_name"], player_id=pid, source=e["source"], availability_status=e["availability_status"], reason=e["reason"],
                         batting_data_rank=br, batting_pool_status=bs, bowling_data_rank=wr, bowling_pool_status=ws,
                         in_data_top10_batters=pid in d10b, in_data_top10_bowlers=pid in d10w,
                         entered_batters_top10=", ".join(names[i] for i in ent_b) if pid in d10b else "",
                         entered_bowlers_top10=", ".join(names[i] for i in ent_w) if pid in d10w else ""))
    log_df = pd.DataFrame(rows)
    log_df.to_csv(OUT / "excluded_log.csv", index=False)
    ne = []
    for lst, ids, tab, fr in [("batters", ent_b, bat_tab, fb), ("bowlers", ent_w, bowl_tab, fw)]:
        for i in ids:
            r = tab.loc[i]
            share = float(fr.loc[i, "share_in_top10"]) if i in fr.index else np.nan
            ne.append(dict(list=lst, final_rank=int(r["final_rank"]), data_rank=int(r["data_rank"]), player_id=i, player_name=names[i],
                           rating=r["rating"], hp_balls=int(r["n_hp"]), matches=int(r["matches"]), ipl_share_hp=r["ipl_share_hp"],
                           a_team_share_hp=r["a_team_share_hp"], flag=r["flag"], share_of_scenarios_in_top10=share,
                           robust_75pct=bool(share >= 0.75) if not np.isnan(share) else False))
    ne_df = pd.DataFrame(ne)
    ne_df.to_csv(OUT / "new_entrants.csv", index=False)
    if top20_b_ids is not None:
        ne20 = []
        for lst, ids, tab, fr in [("batters", top20_b_ids, bat_tab, fb), ("bowlers", top20_w_ids, bowl_tab, fw)]:
            data20 = set(tab.index[:20])
            for i in ids:
                if i in data20:
                    continue
                r = tab.loc[i]
                share = float(fr.loc[i, "share_in_top20"]) if i in fr.index else np.nan
                ne20.append(dict(list=lst, final_rank=int(r["final_rank"]), data_rank=int(r["data_rank"]), player_name=names[i], rating=r["rating"],
                                 hp_balls=int(r["n_hp"]), matches=int(r["matches"]), ipl_share_hp=r["ipl_share_hp"], a_team_share_hp=r["a_team_share_hp"],
                                 availability_status=r["availability_status"], flag=r["flag"], share_of_scenarios_in_top20=share))
        pd.DataFrame(ne20).to_csv(OUT / "new_entrants_top20.csv", index=False)
    return log_df, ne_df


def run_checks(S, OUT):
    """Task-4 checks. Prints and saves checks_availability.txt. Returns True if all pass."""
    from docx import Document as _Doc
    lines, ok_all = [], True
    def chk(name, ok, detail=""):
        nonlocal ok_all
        ok_all &= bool(ok)
        lines.append(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
    names, excl = S["names"], S["excl"]
    txt_b = (OUT / "final_top10_batters.txt").read_text(encoding="utf-8").split("\n")
    txt_b = [x for x in txt_b if x]
    txt_w = [x for x in (OUT / "final_top10_bowlers.txt").read_text(encoding="utf-8").split("\n") if x]
    exn = {e["player_name"] for e in excl.values()}
    chk("no excluded player in final batters list", not (set(txt_b) & exn), f"({len(exn)} excluded names)")
    chk("no excluded player in final bowlers list", not (set(txt_w) & exn))
    mp = pd.read_csv(S["cfg"]["data_dir"] / "competition_team_player_mapping.csv")
    pk_names = {names[i] for i in set(mp.loc[mp["team_name"].str.contains(r"^Pakistan( A)?$", regex=True), "player_id"]) if i in names.index}
    chk("no Pakistan-squad player in either final list", not ((set(txt_b) | set(txt_w)) & pk_names), f"({len(pk_names)} Pakistan-squad players in the data)")
    rr_in = sorted(set(txt_b + txt_w) & set(S["cfg"]["rr_retained"].values()))
    lines.append(f"       RR-retained players present in the final lists (allowed): {rr_in}")
    chk("no name repeats in batters list", len(txt_b) == len(set(txt_b)) == 10)
    chk("no name repeats in bowlers list", len(txt_w) == len(set(txt_w)) == 10)
    # ratings identical to previous run
    prev = OUT / "prev_run"
    for role, fn in [("batters", "ratings_all_eligible_batters.csv"), ("bowlers", "ratings_all_eligible_bowlers.csv")]:
        old = pd.read_csv(prev / fn, index_col="player_id")
        new = pd.read_csv(OUT / fn, index_col="player_id")
        common = old.index.intersection(new.index)
        cols = ["rating", "z_value", "z_delta", "z_consistency", "z_wpa", "z_recovery", "shrunk_hp_value", "n_hp"]
        md = max(float((old.loc[common, c] - new.loc[common, c]).abs().max()) for c in cols)
        chk(f"{role}: ratings identical to previous run for the {len(common)} players present in both", md == 0.0 or md < 1e-12,
            f"(max abs difference across rating, 5 z-scores, shrunk value, HP balls = {md:.3g}; pools equal: {set(old.index) == set(new.index)}; data_rank == old rank: {bool((old.loc[common,'rank'] == new.loc[common,'data_rank']).all())})")
    # same order in csv / txt / report
    for role, fn, tx in [("batters", "top10_batters.csv", txt_b), ("bowlers", "top10_bowlers.csv", txt_w)]:
        c = pd.read_csv(OUT / fn)
        chk(f"{role}: top10 csv order == txt order", list(c["player_name"]) == tx and list(c["final_rank"]) == list(range(1, 11)))
    doc = _Doc(OUT / "Methodology_Report.docx")
    rep_final, rep_tab, rep_app = {}, [], []
    for t in doc.tables:
        hdr = [c.text for c in t.rows[0].cells]
        body = [[c.text for c in r.cells] for r in t.rows[1:]]
        if hdr == ["Rank", "Batter", "Bowler"]:
            rep_final = {"batters": [r[1] for r in body], "bowlers": [r[2] for r in body]}
        elif hdr[:2] == ["#", "Player"]:
            rep_tab.append([r[1] for r in body])
        elif hdr[0] == "Data #":
            for j_, h_ in enumerate(hdr):
                if h_ == "Final player":
                    rep_app.append([r[j_] for r in body if r[j_]])
    chk("report: final-selection table order == txt order", rep_final.get("batters") == txt_b and rep_final.get("bowlers") == txt_w)
    chk("report: section-4 evidence tables order == txt order", len(rep_tab) == 2 and rep_tab[0] == txt_b and rep_tab[1] == txt_w)
    chk("report: appendix final-top-10 columns order == txt order", len(rep_app) == 2 and rep_app[0] == txt_b and rep_app[1] == txt_w)
    # summaries
    lines.append("")
    lines.append("Players who entered the top 10 because of the exclusions:")
    for _, r in S["entrants"].iterrows():
        lines.append(f"  {r['list']}: final #{r['final_rank']} {r['player_name']} (id {r['player_id']}) rating {r['rating']:.2f}, {r['hp_balls']} HP balls, {r['matches']} matches, "
                     f"IPL share of HP balls {r['ipl_share_hp']*100:.0f}%, A-team share {r['a_team_share_hp']*100:.0f}%, in top 10 in {r['share_of_scenarios_in_top10']*100:.0f}% of scenarios"
                     f"{' [robust]' if r['robust_75pct'] else ''}; flags: {r['flag'] or 'none'}")
    lines.append("")
    lines.append("ALL CHECKS PASSED" if ok_all else "SOME CHECKS FAILED")
    (OUT / "checks_availability.txt").write_text("\n".join(lines), encoding="utf-8")
    log("\n".join(lines))
    return ok_all


# =====================================================================================
# MAIN
# =====================================================================================
def main(cfg=CONFIG):
    log("== loading & cleaning")
    df, m, c, names, summ = load_and_clean(cfg)
    df["match_order"] = df["match_id"].map(
        df.groupby("match_id")["match_date"].first().reset_index().sort_values(["match_date", "match_id"]).reset_index(drop=True)
        .reset_index().set_index("match_id")["index"])
    df = add_state(df, cfg)
    df = expected_runs(df, cfg)
    log("== setback flags + win probability")
    df = add_setback_flags(df, cfg)
    df, wpa_met = add_wpa(df, cfg)
    log("   WPA test:", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in wpa_met.items()})

    log("== base pressure / values / rating")
    core, ps = pipeline_core(df, cfg)
    df["pressure"], df["hp"] = ps, core["hp"].values
    df["bat_val"], df["bowl_val"] = core["bat_val"].values, core["bowl_val"].values
    STATE["names"] = names

    # ---- validation
    val_tab = pressure_validation(df, df["hp"].values)
    val_tab.to_csv(OUT / "pressure_validation_table.csv", index=False)
    chart_validation(val_tab)
    chart_calibration(wpa_met)
    fig, ax = plt.subplots(figsize=(5, 3))
    for inn, col in [(1, NM_COL), (2, HP_COL)]:
        ax.hist(df.loc[df["innings"] == inn, "pressure"], bins=50, alpha=.6, color=col, label=f"Innings {inn}")
    ax.set_xlabel("Pressure score")
    ax.set_ylabel("Balls")
    ax.legend(frameon=False)
    ax.set_title("Distribution of ball pressure scores")
    fig.tight_layout()
    fig.savefig(OUT / "pressure_distribution.png")
    plt.close(fig)

    mb, mw = cfg["min_hp"]["bat"], cfg["min_hp"]["bowl"]
    bat_all = rate(core, cfg, "bat", 1)
    bowl_all = rate(core, cfg, "bowl", 1)
    excl = resolve_exclusions(names, cfg)
    EXCL = set(excl)
    log("   availability exclusions:", len(excl), "players (",
        sum(v["source"] == "nationality" for v in excl.values()), "by nationality rule)")
    _, bat_tab = top_ids(core, cfg, "bat", mb, cfg["top_n"])          # full pool, data order (no exclusion)
    _, bowl_tab = top_ids(core, cfg, "bowl", mw, cfg["top_n"])
    log("   eligible batters", len(bat_tab), "bowlers", len(bowl_tab))
    for tab in (bat_tab, bowl_tab):
        tab.insert(0, "player_name", tab.index.map(names))
    btype = df.groupby("bowler_id")["pace_or_spin"].agg(lambda s_: s_.mode().iat[0])
    bowl_tab["bowler_type"] = bowl_tab.index.map(btype)

    def flags(t, minn):
        f = []
        for i, r in t.iterrows():
            x = []
            if r["n_hp"] < 1.5 * minn:
                x.append("low HP volume")
            if r["ipl_share_hp"] < 0.5:
                x.append("mostly non-IPL balls")
            if r["matches"] < 15:
                x.append("<15 matches")
            if r["a_team_share_hp"] > 0.3:
                x.append("A-team events >30% of HP balls")
            f.append("; ".join(x))
        return f
    bat_tab["flag"] = flags(bat_tab, mb)
    bowl_tab["flag"] = flags(bowl_tab, mw)
    for tab in (bat_tab, bowl_tab):
        tab.rename(columns={"rank": "data_rank"}, inplace=True)
        tab["excluded_reason"] = [excl[i]["reason"] if i in excl else "" for i in tab.index]
        tab["availability_status"] = [excl[i]["availability_status"] if i in excl else ("Retained by RR (own player)" if i in cfg["rr_retained"] else "Unverified") for i in tab.index]
        tab["excluded"] = tab.index.isin(EXCL)
        tab["final_rank"] = np.nan
        tab.loc[~tab["excluded"], "final_rank"] = np.arange(1, int((~tab["excluded"]).sum()) + 1)
    bat_final = bat_tab[~bat_tab["excluded"]].copy()
    bowl_final = bowl_tab[~bowl_tab["excluded"]].copy()
    for t_ in (bat_final, bowl_final):
        t_["final_rank"] = t_["final_rank"].astype(int)
    top_b_ids = list(bat_final.index[:cfg["top_n"]])
    top_w_ids = list(bowl_final.index[:cfg["top_n"]])
    lead = ["data_rank", "final_rank", "player_name", "availability_status", "excluded_reason"]
    full_order = lambda t_: lead + [c_ for c_ in t_.columns if c_ not in lead + ["excluded"]]
    bat_tab[full_order(bat_tab)].to_csv(OUT / "ratings_all_eligible_batters.csv")
    bowl_tab[full_order(bowl_tab)].to_csv(OUT / "ratings_all_eligible_bowlers.csv")
    bat_tab[full_order(bat_tab)].head(25).to_csv(OUT / "ranked_top25_batters_with_availability.csv")
    bowl_tab[full_order(bowl_tab)].head(25).to_csv(OUT / "ranked_top25_bowlers_with_availability.csv")
    cols_b = ["final_rank", "data_rank", "player_name", "n_hp", "n_norm", "matches", "hp_matches", "chase_balls", "rec_balls", "raw_hp_value", "shrunk_hp_value",
              "raw_norm_value", "shrunk_norm_value", "delta", "consistency", "wpa_shrunk", "recovery", "z_value", "z_delta",
              "z_consistency", "z_wpa", "z_recovery", "rating", "ipl_share_hp", "a_team_share_hp", "availability_status", "excluded_reason", "flag"]
    top_b = bat_final.head(10)[cols_b]
    top_w = bowl_final.head(10)[cols_b]
    top_w.insert(3, "bowler_type", bowl_final.head(10)["bowler_type"])
    dcols = ["data_rank", "final_rank", "player_name", "availability_status", "excluded_reason", "rating", "n_hp", "matches", "ipl_share_hp", "a_team_share_hp", "flag"]
    bat_tab.head(15)[dcols].to_csv(OUT / "data_only_top15_batters.csv")
    bowl_tab.head(15)[dcols].to_csv(OUT / "data_only_top15_bowlers.csv")
    top20_b = bat_final.head(cfg["list_n"])[cols_b]
    top20_w = bowl_final.head(cfg["list_n"])[cols_b]
    top20_w.insert(3, "bowler_type", bowl_final.head(cfg["list_n"])["bowler_type"])
    top20_b_ids, top20_w_ids = list(top20_b.index), list(top20_w.index)
    for tt in (top_b, top_w, top20_b, top20_w):
        assert tt["player_name"].is_unique and tt.index.is_unique, "duplicate player in a list"
    top_b.to_csv(OUT / "top10_batters.csv")
    top_w.to_csv(OUT / "top10_bowlers.csv")
    (OUT / "final_top10_batters.txt").write_text("\n".join(top_b["player_name"]) + "\n", encoding="utf-8")
    (OUT / "final_top10_bowlers.txt").write_text("\n".join(top_w["player_name"]) + "\n", encoding="utf-8")
    chart_top10(bat_final, "bat", names, "Top 10 batters under pressure: what drives the rating", "top10_batters.png")
    chart_top10(bowl_final, "bowl", names, "Top 10 bowlers under pressure: what drives the rating", "top10_bowlers.png")
    chart_delta(bat_final, names, "batters", "delta_batters.png")
    chart_delta(bowl_final, names, "bowlers", "delta_bowlers.png")

    # ---- Step 7
    log("== year by year / big game / series")
    sb_all = season_ratings(core, cfg, "bat", list(bat_all.index))
    sw_all = season_ratings(core, cfg, "bowl", list(bowl_all.index))
    sb, sw = sb_all.loc[top_b_ids], sw_all.loc[top_w_ids]
    for piv, role, ids, nm_ in [(sb, "batters", top_b_ids, "year_by_year_batters.csv"), (sw, "bowlers", top_w_ids, "year_by_year_bowlers.csv")]:
        st = season_stats(piv)
        o = pd.concat([piv, st], axis=1)
        o.insert(0, "player_name", o.index.map(names))
        o.insert(0, "rank", np.arange(1, len(o) + 1))
        o.to_csv(OUT / nm_)
        STATE[f"{role}_seasonstats"] = o
    chart_heatmap(sb, names, "Batters: season rating (min 30 HP balls per season)", "heatmap_batters.png")
    chart_heatmap(sw, names, "Bowlers: season rating (min 25 HP balls per season)", "heatmap_bowlers.png")
    df["hp_"] = df["hp"]
    bgb = big_game(df, cfg, "bat", top_b_ids)
    bgw = big_game(df, cfg, "bowl", top_w_ids)
    for t_, nm_ in [(bgb, "bigame_batters.csv"), (bgw, "bigame_bowlers.csv")]:
        t_.insert(0, "player_name", t_.index.map(names))
        t_.to_csv(OUT / nm_)
    serb = series_totals(df, "bat", top_b_ids, "hp_")
    serw = series_totals(df, "bowl", top_w_ids, "hp_")
    for t_, nm_ in [(serb, "series_totals_batters.csv"), (serw, "series_totals_bowlers.csv")]:
        t_.insert(1, "player_name", t_.iloc[:, 0].map(names))
        t_.to_csv(OUT / nm_, index=False)
    wcb = winning_contribution(df, "bat", top_b_ids)
    wcw = winning_contribution(df, "bowl", top_w_ids)
    for t_, nm_ in [(wcb, "winning_contribution_batters.csv"), (wcw, "winning_contribution_bowlers.csv")]:
        t_.insert(0, "player_name", t_.index.map(names))
        t_.to_csv(OUT / nm_)
    rv = role_views(df, cfg, names, bat_final, bowl_final)
    for k_, v_ in rv.items():
        v_.to_csv(OUT / f"roleview_{k_}.csv")
    STATE.update(bat_all=bat_all, bowl_all=bowl_all, bat_season_all=sb_all, bowl_season_all=sw_all,
                 bat_series_all=serb,
                 bowl_series_all=serw,
                 bat_bigame_all=bgb, bowl_bigame_all=bgw, bat_win_all=wcb, bowl_win_all=wcw)

    # ---- Step 8
    log("== reliability")
    rel_rows, stab_rows = [], []
    for role, tab, ids, minb, half_min in [("bat", bat_final, top_b_ids, mb, cfg["half_min_hp"]["bat"]),
                                          ("bowl", bowl_final, top_w_ids, mw, cfg["half_min_hp"]["bowl"])]:
        splits = {
            "2022-23 vs 2024+": (core["year"] <= 2023, core["year"] >= 2024),
            "odd vs even matches": (core["match_order"] % 2 == 1, core["match_order"] % 2 == 0)}
        for lab, (ma, mb_) in splits.items():
            ia, ta = top_ids(core[ma], cfg, role, half_min, min_matches=8, exclude=EXCL)
            ib, tb = top_ids(core[mb_], cfg, role, half_min, min_matches=8, exclude=EXCL)
            st = overlap_stats(ia, ib, ta, tb)
            st.update(role=role, label=lab, half_min=half_min, n_a=len(ta), n_b=len(tb),
                      a_vs_full=len(set(ia) & set(ids)), b_vs_full=len(set(ib) & set(ids)))
            stab_rows.append(st)
    stab = pd.DataFrame(stab_rows)
    stab.to_csv(OUT / "stability_table.csv", index=False)
    diag = pd.DataFrame([reliability_diag(core, cfg, "bat", mb), reliability_diag(core, cfg, "bowl", mw)])
    diag.to_csv(OUT / "reliability_diagnostics.csv", index=False)
    chart_stability([dict(label=f"{r['role']}: {r['label']}", top10_overlap=r["top10_overlap"], spearman=r["spearman"]) for r in stab_rows])

    S = scenarios(cfg)
    res_b, res_w, rk_b, rk_w = {}, {}, {}, {}
    for nm_, ov_ in S.items():
        cs = merge_cfg(cfg, ov_)
        cs["pressure"]["_center"] = cfg["pressure"]["_center"]
        core_s, _ = pipeline_core(df, cs)
        if cs.get("exclude_regex"):
            core_s = core_s[~core_s["comp_name"].str.contains(cs["a_team_regex"])]
        ib, tb = top_ids(core_s, cs, "bat", cs["min_hp"]["bat"], n=cfg["list_n"], exclude=EXCL)
        iw, tw = top_ids(core_s, cs, "bowl", cs["min_hp"]["bowl"], n=cfg["list_n"], exclude=EXCL)
        res_b[nm_], res_w[nm_] = ib, iw
        rk_b[nm_], rk_w[nm_] = tb["rank"], tw["rank"]
        log(f"   scenario {nm_}: bat overlap {len(set(ib[:10]) & set(top_b_ids))}/10, bowl overlap {len(set(iw[:10]) & set(top_w_ids))}/10")
    def rcorr(rb, rs):
        common = rb.index.intersection(rs.index)
        return spearmanr(rb[common], rs[common])[0] if len(common) > 4 else np.nan
    sens_rows = []
    for nm_ in S:
        sens_rows.append(dict(scenario=nm_, batter_overlap_with_base=len(set(res_b[nm_][:10]) & set(top_b_ids)),
                              bowler_overlap_with_base=len(set(res_w[nm_][:10]) & set(top_w_ids)),
                              batter_rank_spearman=rcorr(rk_b["base"], rk_b[nm_]),
                              bowler_rank_spearman=rcorr(rk_w["base"], rk_w[nm_])))
    sens = pd.DataFrame(sens_rows)
    sens.to_csv(OUT / "sensitivity_scenarios.csv", index=False)

    def freq(res, rk, base_ids, base20):
        scen = [s for s in S if s != "base"]
        allp = set(i for s in S for i in res[s])
        rows = []
        for p in allp:
            ranks = [rk[s].get(p, np.nan) for s in scen]
            inn = [p in res[s][:10] for s in scen]
            inn20 = [p in res[s] for s in scen]
            rows.append(dict(player_id=p, player_name=names[p], in_base_top10=p in base_ids,
                             base_rank=rk["base"].get(p, np.nan), scenarios_in_top10=int(sum(inn)),
                             share_in_top10=sum(inn) / len(scen), median_rank=np.nanmedian(ranks) if not np.all(np.isnan(ranks)) else np.nan,
                             in_base_top20=p in base20, scenarios_in_top20=int(sum(inn20)), share_in_top20=sum(inn20) / len(scen),
                             best_rank=np.nanmin(ranks) if not np.all(np.isnan(ranks)) else np.nan,
                             worst_rank=np.nanmax(ranks) if not np.all(np.isnan(ranks)) else np.nan))
        return pd.DataFrame(rows).sort_values(["share_in_top10", "median_rank"], ascending=[False, True]).set_index("player_id")
    alt = pd.DataFrame({"rank": range(1, 11), "batters_excl_A_team": [names[i] for i in res_b["exclude A-team events"][:10]],
                        "bowlers_excl_A_team": [names[i] for i in res_w["exclude A-team events"][:10]]})
    alt.to_csv(OUT / "alt_top10_excluding_A_team_events.csv", index=False)
    fb, fw = freq(res_b, rk_b, top_b_ids, top20_b_ids), freq(res_w, rk_w, top_w_ids, top20_w_ids)
    fb.to_csv(OUT / "sensitivity_robustness_batters.csv")
    fw.to_csv(OUT / "sensitivity_robustness_bowlers.csv")
    chart_sensitivity(fb, fw, len(S) - 1, names)

    # ---- clean-data summary
    summ.update({f"wpa_{k}": v for k, v in wpa_met.items()})
    summ["close_center_runs_per_over"] = cfg["pressure"]["_center"]
    summ["hp_threshold_inn1"] = float(df.loc[df["innings"] == 1, "pressure"].quantile(1 - cfg["hp_quantile"]))
    summ["hp_threshold_inn2"] = float(df.loc[df["innings"] == 2, "pressure"].quantile(1 - cfg["hp_quantile"]))
    pd.Series(summ).to_csv(OUT / "clean_data_summary.csv", header=["value"])
    mc = df.groupby(["comp_name", "year"]).match_id.nunique().reset_index(name="matches")
    mc.to_csv(OUT / "matches_per_competition_year.csv", index=False)
    df.groupby(["match_format", "year"]).match_id.nunique().unstack().to_csv(OUT / "matches_per_format_year.csv")

    bat_ctx = rate(core, cfg, "bat", 1, min_matches=0)      # context lookup only (no match minimum) for the exclusion log
    bowl_ctx = rate(core, cfg, "bowl", 1, min_matches=0)
    log_df, ne_df = availability_outputs(bat_tab, bowl_tab, bat_ctx, bowl_ctx, excl, top_b_ids, top_w_ids, fb, fw, names, cfg)
    STATE.update(dict(excl=excl, excluded_log=log_df, entrants=ne_df, bat_final=bat_final, bowl_final=bowl_final))
    log("== SHAP")
    STATE["shap"] = shap_outputs(df, bat_tab, bowl_tab, top_b_ids, top_w_ids, names, cfg)
    STATE.update(dict(df=df, summ=summ, wpa_met=wpa_met, val_tab=val_tab, top_b=top_b, top_w=top_w, bat_tab=bat_tab, bowl_tab=bowl_tab,
                      sb=sb, sw=sw, bgb=bgb, bgw=bgw, serb=serb, serw=serw, wcb=wcb, wcw=wcw, rv=rv, stab=stab, diag=diag, sens=sens,
                      fb=fb, fw=fw, res_b=res_b, res_w=res_w, scen_n=len(S) - 1, cfg=cfg, names=names, top_b_ids=top_b_ids, top_w_ids=top_w_ids, top20_b=top20_b, top20_w=top20_w, top20_b_ids=top20_b_ids, top20_w_ids=top20_w_ids))
    # profiles of the 20 selected players
    prof = {names[i]: player_profile(names[i]) for i in top_b_ids + top_w_ids}
    (OUT / "player_profiles_top20.json").write_text(json.dumps(prof, indent=1, default=str), encoding="utf-8")
    log("== done analysis; building report")
    import report_builder
    report_builder.build(STATE, OUT)
    log("== checks")
    STATE["checks_ok"] = run_checks(STATE, OUT)
    log("== finished")
    return STATE


if __name__ == "__main__":
    main()
