"""Matches the supplied retention lists (retention_lists_2027.csv) to player IDs in the ball data.
Rules (no memory, data evidence only):
  1. exact normalised-name match -> accept; if the name maps to several IDs, keep the one in the same franchise's IPL 2026 squad.
  2. otherwise a fuzzy candidate is accepted only if it is in the SAME franchise's IPL 2026 squad (non-traded players), shares a name token and is similar;
     traded-in players (no squad evidence) need similarity >= 0.90.
Writes retention_lists_2027_matched.csv."""
import difflib
import re
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
D = BASE / "Data Pack"
R = pd.read_csv(BASE / "retention_lists_2027.csv")
b = pd.read_csv(D / "ball_by_ball.csv", usecols=["striker_id", "striker_name", "bowler_id", "bowler_name"])
nm = pd.concat([b[["striker_id", "striker_name"]].set_axis(["id", "name"], axis=1), b[["bowler_id", "bowler_name"]].set_axis(["id", "name"], axis=1)]).drop_duplicates()
names = nm.groupby("id")["name"].first()
mp = pd.read_csv(D / "competition_team_player_mapping.csv")
sq26 = mp[mp["comp_name"] == "IPL 2026"].groupby("team_name")["player_id"].apply(set).to_dict()
ipl_any = mp[mp["comp_name"].str.startswith("IPL")].groupby("team_name")["player_id"].apply(set).to_dict()
norm = lambda s: re.sub(r"[^a-z ]", "", s.lower().replace("-", " ")).strip()
tok_sorted = lambda s: " ".join(sorted(norm(s).split()))
from collections import Counter
tok_count = Counter(t for n in names for t in set(norm(n).split()))
GENERIC = {t for t, c in tok_count.items() if c >= 25}   # very common name parts (singh, kumar, sharma, khan ...) never count as evidence
by_norm = {}
for i, n in names.items():
    by_norm.setdefault(norm(n), []).append(i)

rows = []
for _, r in R.iterrows():
    team, sup, traded = r["team"], r["player_name_supplied"], bool(r["traded_in"])
    k = norm(sup)
    rec = dict(team=team, player_name_supplied=sup, traded_in=traded, source=r.get("source", "pasted list"), player_id=None, data_name="", match_type="unmatched", evidence="")
    if k in by_norm:
        ids = by_norm[k]
        if len(ids) == 1:
            rec.update(player_id=ids[0], data_name=names[ids[0]], match_type="exact")
        else:
            inteam = [i for i in ids if i in sq26.get(team, set()) or i in ipl_any.get(team, set())]
            if len(inteam) == 1:
                rec.update(player_id=inteam[0], data_name=names[inteam[0]], match_type="exact (same name, several IDs; resolved by franchise IPL squad)",
                           evidence=f"IDs {ids}; only {inteam[0]} appears in {team} IPL squads")
            else:
                rec.update(match_type="AMBIGUOUS", evidence=f"IDs {ids}")
    else:
        pool = sq26.get(team, set()) if not traded else set()
        best = None
        for i, n in names.items():
            sim = max(difflib.SequenceMatcher(None, k, norm(n)).ratio(), difflib.SequenceMatcher(None, tok_sorted(sup), tok_sorted(n)).ratio())
            share = bool((set(k.split()) & set(norm(n).split())) - GENERIC)
            if traded:
                ok = sim >= 0.90
            else:
                ok = i in pool and share and sim >= 0.65
            if ok and (best is None or sim > best[0]):
                best = (sim, i, n)
        if best:
            sim, i, n = best
            weak = sim < 0.80
            rec.update(player_id=i, data_name=n, match_type="fuzzy + franchise squad" + (" (WEAK: confirm)" if weak else ""),
                       evidence=f"similarity {sim:.2f}; {'in ' + team + ' IPL 2026 squad' if not traded else 'traded-in, name similarity only'}")
    rows.append(rec)

M = pd.DataFrame(rows)
M.to_csv(BASE / "retention_lists_2027_matched.csv", index=False)
print(M["match_type"].value_counts().to_string())
bt = pd.read_csv(BASE / "outputs" / "ratings_all_eligible_batters.csv", index_col="player_id")
bw = pd.read_csv(BASE / "outputs" / "ratings_all_eligible_bowlers.csv", index_col="player_id")
print("\nNON-EXACT / UNRESOLVED:")
print(M[~M["match_type"].isin(["exact"])][["team", "player_name_supplied", "match_type", "data_name", "player_id", "evidence"]].to_string(index=False))
oth = M[(M["team"] != "Rajasthan Royals") & M["player_id"].notna()].copy()
oth["bat_data_rank"] = oth["player_id"].map(bt["data_rank"])
oth["bowl_data_rank"] = oth["player_id"].map(bw["data_rank"])
print("\nRetained by OTHER franchises and in the rated pool (data ranks):")
x = oth[oth["bat_data_rank"].notna() | oth["bowl_data_rank"].notna()].sort_values(["bat_data_rank", "bowl_data_rank"])
print(x[["team", "data_name", "traded_in", "bat_data_rank", "bowl_data_rank"]].to_string(index=False))
rr = M[(M["team"] == "Rajasthan Royals") & M["player_id"].notna()].copy()
rr["bat_data_rank"] = rr["player_id"].map(bt["data_rank"])
rr["bowl_data_rank"] = rr["player_id"].map(bw["data_rank"])
print("\nRR-retained (stay eligible) in rated pool:")
print(rr[rr["bat_data_rank"].notna() | rr["bowl_data_rank"].notna()][["data_name", "bat_data_rank", "bowl_data_rank"]].to_string(index=False))
