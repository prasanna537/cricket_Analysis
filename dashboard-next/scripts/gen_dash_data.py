"""Step 1 of 2: builds the full dashboard data bundle from outputs/ (the intermediate file goes to the temp dir)."""
import tempfile
from pathlib import Path
import json, sys
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import analysis as A

OUT = A.OUT
cfg = A.CONFIG
W = cfg["rating_w"]
wt = {"z_value": W["value"], "z_delta": W["delta"], "z_consistency": W["consistency"], "z_wpa": W["wpa"], "z_recovery": W["recovery"]}
LBL = {"z_value": "pressure value", "z_delta": "lift over own baseline", "z_consistency": "consistency",
       "z_wpa": "win-probability added", "z_recovery": "setback recovery"}


def clean(v):
    if isinstance(v, (np.integer,)): return int(v)
    if isinstance(v, (np.floating, float)): return None if np.isnan(v) else float(v)
    if isinstance(v, (np.bool_,)): return bool(v)
    return v


def recs(df):
    return [{k: clean(v) for k, v in r.items()} for r in df.to_dict("records")]


def why(r):
    c = {k: r[k] * v for k, v in wt.items()}
    top = sorted(c, key=c.get, reverse=True)[:2]
    low = min(c, key=c.get)
    s = f"Lifted by {LBL[top[0]]} ({c[top[0]]:+.2f}) and {LBL[top[1]]} ({c[top[1]]:+.2f})"
    if c[low] < -0.2:
        s += f"; held back by {LBL[low]} ({c[low]:+.2f})"
    return s


def lst(fn, role):
    t = pd.read_csv(OUT / fn)
    t["w_value"] = t.z_value * W["value"]; t["w_delta"] = t.z_delta * W["delta"]; t["w_consistency"] = t.z_consistency * W["consistency"]
    t["w_wpa"] = t.z_wpa * W["wpa"]; t["w_recovery"] = t.z_recovery * W["recovery"]
    t["why"] = t.apply(why, axis=1)
    t["role"] = role
    t["at_rr"] = t["availability_status"].fillna("").str.startswith("Retained by RR")
    t["consistency_pct"] = t.consistency * 100
    t["ipl_share_pct"] = t.ipl_share_hp * 100
    t["wpa_x1000"] = t.wpa_shrunk * 1000
    t["flag"] = t["flag"].fillna("")
    keep = ["final_rank", "data_rank", "player_name", "role", "n_hp", "matches", "shrunk_hp_value", "shrunk_norm_value", "delta", "consistency_pct", "wpa_x1000",
            "recovery", "rating", "ipl_share_pct", "at_rr", "w_value", "w_delta", "w_consistency", "w_wpa", "w_recovery", "why", "flag"]
    if "bowler_type" in t.columns: keep.append("bowler_type")
    return t[keep]


bat, bowl = lst("top10_batters.csv", "batter"), lst("top10_bowlers.csv", "bowler")
S = A.CONFIG["pressure"]
signals = pd.DataFrame([
    ["Chase", "Required-rate stress", S["inn2"]["rrr"], f"Required rate mapped from {S['rrr_lo']:.0f} to {S['rrr_hi']:.0f} runs/over; the harder the chase, the more every dot ball costs."],
    ["Chase", "Wickets lost", S["inn2"]["wkts"], "Fewer batters left means less licence to attack and a bigger price for a dismissal."],
    ["Chase", "How late", S["inn2"]["late"], "Share of the innings already used; less time to recover from a mistake."],
    ["Chase", "Closeness of chase", S["inn2"]["close"], "Peaks when the result is on a knife-edge; falls when the chase is easy or hopeless."],
    ["First innings", "Wickets lost", S["inn1"]["wkts"], "Same logic as in a chase."],
    ["First innings", "How late", S["inn1"]["late"], "Late overs decide the total."],
    ["First innings", "Behind par", S["inn1"]["par"], f"Runs below the average score at the same point; full pressure at {S['par_gap_scale']:.0f} runs behind."],
], columns=["innings", "signal", "weight", "why"])
weights = pd.DataFrame([
    ["Shrunk pressure value", W["value"], "Runs above (batters) or saved vs (bowlers) what similar situations give, on high-pressure balls, pulled toward the league mean."],
    ["Lift over own baseline", W["delta"], "High-pressure value minus the player's own normal-ball value."],
    ["Consistency", W["consistency"], "Share of matches (3+ high-pressure balls) with a positive pressure value."],
    ["Win probability added", W["wpa"], "Change in chase win probability from the model, weighted by leverage; chases only."],
    ["Setback recovery", W["recovery"], "Batters: the 6 balls after a wicket. Bowlers: the ball after a boundary. Versus the league in the same spot."],
], columns=["component", "weight", "meaning"])
val = pd.read_csv(OUT / "pressure_validation_table.csv")
val["innings"] = val["innings"].astype(str)
rb = pd.read_csv(OUT / "sensitivity_robustness_batters.csv"); rw = pd.read_csv(OUT / "sensitivity_robustness_bowlers.csv")
rb["role"], rw["role"] = "batter", "bowler"
rob = pd.concat([rb[(rb.share_in_top10 >= .3) | rb.in_base_top20], rw[(rw.share_in_top10 >= .3) | rw.in_base_top20]])[["role", "player_name", "in_base_top10", "in_base_top20", "base_rank", "share_in_top10", "share_in_top20", "median_rank", "best_rank", "worst_rank"]]
sb = pd.read_csv(OUT / "year_by_year_batters.csv"); sw = pd.read_csv(OUT / "year_by_year_bowlers.csv")
seas = []
for role, t in [("batter", sb), ("bowler", sw)]:
    for _, r in t.iterrows():
        for y in ["2022", "2023", "2024", "2025", "2026"]:
            if y in t.columns:
                seas.append(dict(role=role, player_name=r["player_name"], final_rank=int(r["rank"]), year=int(y), rating=clean(r[y])))
d15 = []
for role, fn in [("batter", "data_only_top15_batters.csv"), ("bowler", "data_only_top15_bowlers.csv")]:
    t = pd.read_csv(OUT / fn); t["role"] = role; t["excluded"] = t["excluded_reason"].fillna("") != ""
    d15.append(t)
d15 = pd.concat(d15)
d15["excluded_reason"] = d15["excluded_reason"].fillna(""); d15["availability_status"] = d15["availability_status"].fillna("")
d15 = d15[["role", "data_rank", "final_rank", "player_name", "rating", "excluded", "availability_status", "excluded_reason"]]
ex = pd.read_csv(OUT / "excluded_log.csv")
exr = ex[ex.source != "nationality"][["player", "availability_status", "reason", "batting_data_rank", "bowling_data_rank"]]
n_nat = int((ex.source == "nationality").sum())
stab = pd.read_csv(OUT / "stability_table.csv")
diag = pd.read_csv(OUT / "reliability_diagnostics.csv")
sens = pd.read_csv(OUT / "sensitivity_scenarios.csv")
clean_s = pd.read_csv(OUT / "clean_data_summary.csv", index_col=0)["value"]
rbf = rb[rb.in_base_top10]; rwf = rw[rw.in_base_top10]
summary = dict(
    matches=int(clean_s["matches_clean"]), balls=int(clean_s["ball_rows_clean"]), date_min=clean_s["date_min"], date_max=clean_s["date_max"],
    no_result=int(clean_s["matches_no_result_or_abandoned"]), rain_revised=int(clean_s["rain_revised_matches"]),
    hp_thr_inn1=float(clean_s["hp_threshold_inn1"]), hp_thr_inn2=float(clean_s["hp_threshold_inn2"]),
    hp_quantile=cfg["hp_quantile"], wk=cfg["wk"], shrink_k=cfg["shrink_k"], min_hp_bat=cfg["min_hp"]["bat"], min_hp_bowl=cfg["min_hp"]["bowl"],
    min_hp_matches=cfg["min_hp_matches"],
    eligible_bat=int(len(pd.read_csv(OUT / "ratings_all_eligible_batters.csv"))), eligible_bowl=int(len(pd.read_csv(OUT / "ratings_all_eligible_bowlers.csv"))),
    wpa_acc=float(clean_s["wpa_test_accuracy"]), wpa_logloss=float(clean_s["wpa_test_logloss"]), wpa_base_logloss=float(clean_s["wpa_baseline_logloss_constant"]), wpa_auc=float(clean_s["wpa_test_auc"]),
    n_scen=int(len(sens) - 1), robust_bat=int((rbf.share_in_top10 >= .75).sum()), robust_bowl=int((rwf.share_in_top10 >= .75).sum()),
    nat_excluded=n_nat, signal_close_center=float(clean_s["close_center_runs_per_over"]),
    true_signal_bat=float(diag.loc[diag.role == "bat", "share_true_signal"].iat[0]), true_signal_bowl=float(diag.loc[diag.role == "bowl", "share_true_signal"].iat[0]),
    overlap_bat=int(stab[(stab.role == "bat") & (stab.label.str.startswith("2022"))].top10_overlap.iat[0]),
    overlap_bowl=int(stab[(stab.role == "bowl") & (stab.label.str.startswith("2022"))].top10_overlap.iat[0]),
    availability_as_of=cfg["availability_as_of"],
)
summary["hp_quantile_pct"] = cfg["hp_quantile"] * 100
summary["true_signal_bat_pct"] = summary["true_signal_bat"] * 100
summary["true_signal_bowl_pct"] = summary["true_signal_bowl"] * 100
rob["share_pct"] = rob["share_in_top10"] * 100
data = dict(summary=[summary], bat=recs(bat), bowl=recs(bowl), signals=recs(signals), weights=recs(weights), validation=recs(val), robust=recs(rob),
            season=seas, data15=recs(d15), excluded=recs(exr), stability=recs(stab[["role", "label", "top10_overlap", "n_common_eligible", "spearman"]]), diag=recs(diag))
p = str(Path(tempfile.gettempdir()) / "dash_data_intermediate.json")
json.dump(data, open(p, "w"), allow_nan=False)
import os
print(os.path.getsize(p), {k: len(v) for k, v in data.items()})
