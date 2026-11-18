"""Builds dashboard-next/data/strategy.json: data checks of the selector's three weaknesses (RR vs the other IPL teams) and
data evidence for the three recommended players. Everything is computed from the supplied CSVs and the pipeline outputs."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
D = BASE / "Data Pack"
OUT = BASE / "outputs"

b = pd.read_csv(D / "ball_by_ball.csv", low_memory=False)
m = pd.read_csv(D / "matches.csv")
c = pd.read_csv(D / "competitions.csv")
t = pd.read_csv(D / "teams.csv").drop_duplicates("team_id").set_index("team_id")["team_name"]
m = m.merge(c[["comp_id", "comp_name", "match_format"]], on="comp_id")
b = b[b["innings"].isin([1, 2])].merge(m[["match_id", "comp_name", "match_format", "result"]], on="match_id")
b = b[~b["result"].str.contains("No Result|Abandoned", case=False, na=False)].copy()
b["legal"] = ~b["extras_type"].isin(["wide", "Overstep", "other"])
b["bat_faced"] = ~(b["extras_type"] == "wide")
b["bowler_wkt"] = b["is_wicket"] & ~b["dismissal_type"].isin(["RunOut", "Retire Out", "Obstracting the field", "Obstructing the field"])
b["out"] = b["is_wicket"] & (b["dismissed_player_id"] == b["striker_id"]) & (b["dismissal_type"] != "Retire Out")
b["tot"] = b["runs"] + b["extras1_runs"] + b["extras_2_runs"]

RR = "Rajasthan Royals"
checks = []
for season in ["IPL 2026", "IPL 2025"]:
    s = b[b["comp_name"] == season]
    mo = s[s["batting_order"].between(4, 6) & s["bat_faced"]].groupby("batting_team_id").agg(balls=("runs", "size"), runs=("runs", "sum"), outs=("out", "sum"))
    mo["sr"] = mo["runs"] / mo["balls"] * 100
    mo["avg"] = mo["runs"] / mo["outs"].replace(0, np.nan)
    de = s[s["overid"] >= 16].groupby("bowling_team_id").agg(legal=("legal", "sum"), runs=("tot", "sum"), w=("bowler_wkt", "sum"))
    de["econ"] = de["runs"] / de["legal"] * 6
    de["wpo"] = de["w"] / de["legal"] * 6
    sp = s[s["pace_or_spin"] == "Spin"].groupby("bowling_team_id").agg(legal=("legal", "sum"), runs=("tot", "sum"), w=("bowler_wkt", "sum"))
    sp["econ"] = sp["runs"] / sp["legal"] * 6
    sp["bpw"] = sp["legal"] / sp["w"]
    spm = s[(s["pace_or_spin"] == "Spin") & s["overid"].between(7, 15)].groupby("bowling_team_id").agg(legal=("legal", "sum"), runs=("tot", "sum"))
    spm["econ"] = spm["runs"] / spm["legal"] * 6
    rr = [i for i in mo.index if t.get(i) == RR][0]

    def add(area, metric, df, col, higher_better, unit):
        v = df[col]
        rank = int(v.rank(ascending=not higher_better, method="min")[rr])
        checks.append(dict(area=area, metric=metric, season=season.replace("IPL ", ""), rr=float(v[rr]), league_avg=float(v.mean()), rank=rank, teams=int(len(v)),
                           higher_is_better=higher_better, unit=unit))
    add("Middle-order batting", "Strike rate, batting positions 4-6", mo, "sr", True, "runs per 100 balls")
    add("Middle-order batting", "Batting average, positions 4-6", mo, "avg", True, "runs per dismissal")
    add("Death-over bowling", "Economy, overs 16-20", de, "econ", False, "runs per over")
    add("Death-over bowling", "Wickets per over, overs 16-20", de, "wpo", True, "wickets per over")
    add("Spin bowling", "Spin economy, all overs", sp, "econ", False, "runs per over")
    add("Spin bowling", "Balls per spin wicket", sp, "bpw", False, "balls")
    add("Spin bowling", "Spin economy, overs 7-15", spm, "econ", False, "runs per over")

# ---- player evidence
bt = pd.read_csv(OUT / "ratings_all_eligible_batters.csv")
bw = pd.read_csv(OUT / "ratings_all_eligible_bowlers.csv")
fb = pd.read_csv(OUT / "sensitivity_robustness_batters.csv")
fw = pd.read_csv(OUT / "sensitivity_robustness_bowlers.csv")
all_death = b[b["overid"] >= 16]
bench_death = dict(econ=float(all_death["tot"].sum() / all_death["legal"].sum() * 6), wpo=float(all_death["bowler_wkt"].sum() / all_death["legal"].sum() * 6))
all_spm = b[(b["pace_or_spin"] == "Spin") & b["overid"].between(7, 15)]
bench_spm = float(all_spm["tot"].sum() / all_spm["legal"].sum() * 6)


def one(df, name):
    r = df[df["player_name"] == name]
    return None if r.empty else r.iloc[0]


def death(name):
    x = all_death[all_death["bowler_name"] == name]
    return dict(balls=int(x["legal"].sum()), econ=float(x["tot"].sum() / max(x["legal"].sum(), 1) * 6), wpo=float(x["bowler_wkt"].sum() / max(x["legal"].sum(), 1) * 6))


players = []
for name, role in [("Sikandar Raza", "Spin all-rounder"), ("Mark Chapman", "Middle-order batter"), ("Matheesha Pathirana", "Death-over specialist"), ("Mustafizur Rahman", "Death-over alternative")]:
    rb_, rt_ = one(bw, name), one(bt, name)
    rec = dict(name=name, role=role)
    if rb_ is not None:
        sh = fw[fw["player_name"] == name]
        rec["bowling"] = dict(final_rank=None if pd.isna(rb_["final_rank"]) else int(rb_["final_rank"]), data_rank=int(rb_["data_rank"]), rating=float(rb_["rating"]),
                              hp_balls=int(rb_["n_hp"]), matches=int(rb_["matches"]), ipl_share_pct=float(rb_["ipl_share_hp"] * 100),
                              robust_pct=None if sh.empty else float(sh["share_in_top10"].iloc[0] * 100))
    if rt_ is not None:
        sh = fb[fb["player_name"] == name]
        rec["batting"] = dict(final_rank=None if pd.isna(rt_["final_rank"]) else int(rt_["final_rank"]), data_rank=int(rt_["data_rank"]), rating=float(rt_["rating"]),
                              hp_balls=int(rt_["n_hp"]), matches=int(rt_["matches"]), ipl_share_pct=float(rt_["ipl_share_hp"] * 100),
                              robust_pct=None if sh.empty else float(sh["share_in_top10"].iloc[0] * 100))
    rec["death_overs"] = death(name)
    x = all_spm[all_spm["bowler_name"] == name]
    rec["spin_middle_overs"] = dict(balls=int(x["legal"].sum()), econ=float(x["tot"].sum() / x["legal"].sum() * 6) if len(x) else None)
    players.append(rec)

# ---- Mark Chapman: what the supplied data (T20I, 2022 onward) shows next to the career figures quoted by the selector
x = b[(b["striker_name"] == "Mark Chapman")]
f_ = x[x["bat_faced"]]
inn = f_.groupby(["match_id", "innings"])["runs"].sum()
mid = f_[f_["overid"].between(7, 15)]
t20i_mid = b[(b["match_format"] == "T20I") & b["bat_faced"] & b["overid"].between(7, 15)]
pos46 = t20i_mid[t20i_mid["batting_order"].between(4, 6)]
yb = b[b["bowler_name"] == "Mark Chapman"]
chapman = dict(
    stated=dict(runs=2074, average=25.92, strike_rate=135.73, fifties=10, hundreds=1, note="Career T20I figures as given by the selector; not computed from the supplied data"),
    dataset=dict(innings=int(len(inn)), runs=int(f_["runs"].sum()), average=float(f_["runs"].sum() / max(x["out"].sum(), 1)), strike_rate=float(f_["runs"].sum() / len(f_) * 100),
                 fifties=int(((inn >= 50) & (inn < 100)).sum()), hundreds=int((inn >= 100).sum()), hand=str(x["batting_type"].iloc[0]),
                 formats=sorted(x["match_format"].unique().tolist()), ipl_balls=int(x[x["comp_name"].str.startswith("IPL")]["bat_faced"].sum())),
    middle_overs=dict(balls=int(len(mid)), strike_rate=float(mid["runs"].sum() / len(mid) * 100), t20i_all_batters=float(t20i_mid["runs"].sum() / len(t20i_mid) * 100),
                      t20i_positions_4_6=float(pos46["runs"].sum() / len(pos46) * 100)),
    bowling=dict(balls=int(len(yb)), types=sorted(yb["bowling_type"].dropna().unique().tolist())),
)
out = dict(rr_checks=checks, players=players, chapman=chapman, benchmarks=dict(death_econ=bench_death["econ"], death_wpo=bench_death["wpo"], spin_middle_econ=bench_spm))
p = BASE / "dashboard-next" / "data" / "strategy.json"
json.dump(out, open(p, "w"), indent=1, allow_nan=False)
for r in checks:
    print(r["season"], r["metric"], round(r["rr"], 2), "avg", round(r["league_avg"], 2), "rank", r["rank"], "/", r["teams"])
for r in players:
    print(r["name"], r.get("bowling"), r.get("batting"), r["death_overs"], r["spin_middle_overs"])
print(out["benchmarks"])
