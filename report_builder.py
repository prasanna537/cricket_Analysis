"""Builds the methodology report (DOCX). Every number is read from the analysis state (STATE) - nothing is hand-typed."""
import re
import numpy as np
import pandas as pd
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

COMP_LABEL = {"z_value": "pressure value", "z_delta": "lift over own baseline", "z_consistency": "consistency",
              "z_wpa": "win-probability added", "z_recovery": "setback recovery"}


def _shade(cell, hexcol):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hexcol)
    tcPr.append(shd)


def table(doc, df, widths=None, size=7.5, header_fill="1F3A5F"):
    t = doc.add_table(rows=1, cols=len(df.columns))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for j, c in enumerate(df.columns):
        cell = t.rows[0].cells[j]
        cell.text = ""
        r = cell.paragraphs[0].add_run(str(c))
        r.bold, r.font.size, r.font.color.rgb = True, Pt(size), RGBColor(255, 255, 255)
        _shade(cell, header_fill)
    for _, row in df.iterrows():
        cells = t.add_row().cells
        for j, v in enumerate(row):
            cells[j].text = ""
            p = cells[j].paragraphs[0]
            r = p.add_run("" if (isinstance(v, float) and np.isnan(v)) else str(v))
            r.font.size = Pt(size)
            if j > 0 and isinstance(v, str) and v.replace(".", "").replace("-", "").replace("%", "").replace("+", "").isdigit():
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    for row in t.rows:
        for c in row.cells:
            for p in c.paragraphs:
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.space_before = Pt(0)
    if widths:
        for row in t.rows:
            for j, w in enumerate(widths):
                row.cells[j].width = Inches(w)
    return t


def para(doc, text, size=9, bold=False, italic=False, after=4, style=None):
    p = doc.add_paragraph(style=style)
    r = p.add_run(text)
    r.font.size, r.bold, r.italic = Pt(size), bold, italic
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.space_before = Pt(0)
    return p


def h(doc, text, lvl=1):
    p = doc.add_heading(text, level=lvl)
    p.paragraph_format.space_before = Pt(8 if lvl == 1 else 4)
    p.paragraph_format.space_after = Pt(3)
    for r in p.runs:
        r.font.size = Pt(13 if lvl == 1 else 10.5)
        r.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
    return p


def caption(doc, text):
    p = para(doc, text, size=8, italic=True, after=6)
    return p


def pic(doc, path, w):
    doc.add_picture(str(path), width=Inches(w))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.paragraphs[-1].paragraph_format.space_after = Pt(2)


def f(x, d=2):
    return "" if pd.isna(x) else f"{x:.{d}f}"


def why(row, name, cfg, flag_prefix=""):
    w = cfg["rating_w"]
    wt = {"z_value": w["value"], "z_delta": w["delta"], "z_consistency": w["consistency"], "z_wpa": w["wpa"], "z_recovery": w["recovery"]}
    contrib = {k: row[k] * v for k, v in wt.items()}
    top = sorted(contrib, key=contrib.get, reverse=True)[:2]
    low = min(contrib, key=contrib.get)
    s = (f"{name} ({int(row['n_hp'])} HP balls, {int(row['matches'])} matches): lifted by {COMP_LABEL[top[0]]} "
         f"({contrib[top[0]]:+.2f}) and {COMP_LABEL[top[1]]} ({contrib[top[1]]:+.2f})")
    if contrib[low] < -0.2:
        s += f"; held back by {COMP_LABEL[low]} ({contrib[low]:+.2f})"
    if isinstance(row.get("flag"), str) and row["flag"]:
        s += f". Flag: {row['flag']}"
    return s + "."


def build(S, OUT):
    RETAIN_ASOF = "18 Nov 2026"
    cfg, names, summ = S["cfg"], S["names"], S["summ"]
    wm, vt = S["wpa_met"], S["val_tab"]
    top_b, top_w, bat_tab, bowl_tab = S["top_b"], S["top_w"], S["bat_tab"], S["bowl_tab"]
    stab, diag, sens = S["stab"], S["diag"], S["sens"]
    fb, fw, nscen = S["fb"], S["fw"], S["scen_n"]
    p = cfg["pressure"]
    doc = Document()
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Inches(0.7)
    sec.top_margin = sec.bottom_margin = Inches(0.5)
    st = doc.styles["Normal"]
    st.font.name, st.font.size = "Calibri", Pt(9)

    # ------------------------------------------------------------------ title
    t = doc.add_paragraph()
    r = t.add_run("Most Reliable Players Under Pressure")
    r.bold, r.font.size, r.font.color.rgb = True, Pt(20), RGBColor(0x1F, 0x3A, 0x5F)
    t.paragraph_format.space_after = Pt(0)
    para(doc, "SuperRR Selector Season 2 - Round 1 - methodology and evidence report", size=10, italic=True, after=6)
    para(doc, (f"Data: {summ['matches_clean']} completed matches and {summ['ball_rows_clean']:,} balls (IPL and T20I-style events, "
               f"{summ['date_min']} to {summ['date_max']}); {summ['matches_no_result_or_abandoned']} no-result/abandoned matches and "
               f"super overs removed. Every number below is generated by analysis.py from the supplied CSVs."))
    para(doc, "Final selections", bold=True, size=10, after=2)
    fin = pd.DataFrame({"Rank": range(1, 11), "Batter": list(top_b["player_name"]), "Bowler": list(top_w["player_name"])})
    table(doc, fin, widths=[0.5, 2.6, 2.6], size=8.5)
    para(doc, "", after=2)
    nrob_b = int((fb[fb["in_base_top10"]]["share_in_top10"] >= .75).sum())
    nrob_w = int((fw[fw["in_base_top10"]]["share_in_top10"] >= .75).sum())
    para(doc, (f"Headline caveat: the batter list is moderately reliable and the bowler list is not. {nrob_b} of 10 batters and "
               f"{nrob_w} of 10 bowlers stay in the top 10 in at least 75% of {nscen} sensitivity scenarios, but split-half testing shows only "
               f"{diag.loc[diag.role=='bat','share_true_signal'].iat[0]*100:.0f}% (batters) and {diag.loc[diag.role=='bowl','share_true_signal'].iat[0]*100:.0f}% "
               f"(bowlers) of the observed spread in pressure value is estimated to be true skill rather than noise (Section 5). "
               f"Use the lists as a shortlist with confidence tiers, not as a precise order."), after=2)

    # ------------------------------------------------------------------ 1 pressure
    h(doc, "1. Pressure definition")
    para(doc, ("Pressure is scored for every ball from the match state before the ball (score, wickets, legal balls bowled, balls left using "
               "rain-revised ball counts where present, target or revised target). Each signal is scaled 0-1 and weights live in one config dict."))
    w1, w2 = p["inn1"], p["inn2"]
    sig = pd.DataFrame([
        ["Chase (inn 2)", "Required-rate stress", f"{w2['rrr']:.2f}", f"Required rate mapped linearly from {p['rrr_lo']:.0f} to {p['rrr_hi']:.0f} runs/over: the more the batting side must out-hit the norm, the more every dot hurts."],
        ["Chase (inn 2)", "Wickets lost", f"{w2['wkts']:.2f}", "Fewer batters left means less licence to attack and a larger penalty for dismissal."],
        ["Chase (inn 2)", "How late", f"{w2['late']:.2f}", "Share of the innings' balls already used; less time to recover from a mistake."],
        ["Chase (inn 2)", "Closeness of chase", f"{w2['close']:.2f}", f"1 minus |required rate - {p['_center']:.1f} (league 1st-innings rate)| / {p['close_width']:.0f}: peaks when the result is on a knife-edge, falls when the chase is easy or hopeless."],
        ["1st innings", "Wickets lost", f"{w1['wkts']:.2f}", "Same logic as above."],
        ["1st innings", "How late", f"{w1['late']:.2f}", "Late overs are where the total is decided."],
        ["1st innings", "Behind par", f"{w1['par']:.2f}", f"Runs below the average score at the same point of the innings, full pressure at {p['par_gap_scale']:.0f} runs behind."]],
        columns=["Innings", "Signal", "Weight", "Why it is a pressure signal"])
    table(doc, sig, widths=[0.9, 1.3, 0.5, 4.3], size=7.5)
    para(doc, "", after=2)
    hi1, hi2 = summ["hp_threshold_inn1"], summ["hp_threshold_inn2"]
    para(doc, (f"High pressure (HP) = the top {cfg['hp_quantile']*100:.0f}% of balls by score within each innings (score above {hi1:.2f} in innings 1 and {hi2:.2f} in innings 2), "
               f"leaving {int(vt[(vt.innings=='both')&(vt.segment=='High pressure')&(vt.group=='all balls')].deliveries.iat[0]):,} HP deliveries against "
               f"{int(vt[(vt.innings=='both')&(vt.segment=='Normal')&(vt.group=='all balls')].deliveries.iat[0]):,} normal ones."))
    # validation sentences
    a = vt[vt.group == "all balls"].assign(innings=lambda d: d["innings"].astype(str)).set_index(["innings", "segment"])
    ph = vt[vt.group != "all balls"]
    def gv(inn, seg, m):
        return a.loc[(str(inn), seg), m]
    segs = []
    for inn in [1, 2]:
        for pnm in ["Powerplay", "Middle", "Death"]:
            hh = ph[(ph.innings.astype(str) == str(inn)) & (ph.group == pnm) & (ph.segment == "High pressure")]
            nn = ph[(ph.innings.astype(str) == str(inn)) & (ph.group == pnm) & (ph.segment == "Normal")]
            if len(hh) and len(nn):
                segs.append((hh.iloc[0], nn.iloc[0]))
    n_seg = len(segs)
    sr_low = sum(h_["strike_rate"] < n_["strike_rate"] for h_, n_ in segs)
    dot_hi = sum(h_["dot_pct"] > n_["dot_pct"] for h_, n_ in segs)
    wk_hi = sum(h_["wickets_per_100"] > n_["wickets_per_100"] for h_, n_ in segs)
    val_lo = sum(h_["bat_value_per_ball"] < n_["bat_value_per_ball"] for h_, n_ in segs)
    txt = (f"Validation (Figure 1). Wickets per 100 balls are higher under pressure in both innings (innings 1: {gv(1,'High pressure','wickets_per_100'):.1f} vs {gv(1,'Normal','wickets_per_100'):.1f}; "
           f"innings 2: {gv(2,'High pressure','wickets_per_100'):.1f} vs {gv(2,'Normal','wickets_per_100'):.1f}), and the context-adjusted batter value per ball is lower "
           f"({gv('both','High pressure','bat_value_per_ball'):.2f} vs {gv('both','Normal','bat_value_per_ball'):.2f}). ")
    raw_sr = [gv(i, "High pressure", "strike_rate") < gv(i, "Normal", "strike_rate") for i in [1, 2]]
    raw_dot = [gv(i, "High pressure", "dot_pct") > gv(i, "Normal", "dot_pct") for i in [1, 2]]
    if all(raw_sr) and all(raw_dot):
        txt += "Strike rate is lower and dot-ball share higher under pressure in both innings, as expected. "
    else:
        txt += (f"The raw strike-rate and dot-ball comparisons do NOT behave as hypothesised in every innings: strike rate is {gv(1,'High pressure','strike_rate'):.1f} vs {gv(1,'Normal','strike_rate'):.1f} in innings 1 "
                f"and {gv(2,'High pressure','strike_rate'):.1f} vs {gv(2,'Normal','strike_rate'):.1f} in innings 2, and dot balls are {gv(1,'High pressure','dot_pct'):.1f}% vs {gv(1,'Normal','dot_pct'):.1f}% and "
                f"{gv(2,'High pressure','dot_pct'):.1f}% vs {gv(2,'Normal','dot_pct'):.1f}%. The reason is composition: HP balls are concentrated in the death overs (fast scoring) and chasing batters accelerate rather than defend. ")
    txt += (f"Comparing within the same innings and phase (lower panels), HP balls have a lower strike rate in {sr_low} of {n_seg} segments, more dot balls in {dot_hi} of {n_seg}, "
            f"more wickets in {wk_hi} of {n_seg} and lower adjusted batter value in {val_lo} of {n_seg}. The score is therefore best read as a measure of how costly and "
            f"wicket-prone a ball is, not as a pure scoring-rate suppressor.")
    para(doc, txt)
    pic(doc, OUT / "pressure_validation.png", 5.0)
    caption(doc, "Figure 1. High-pressure vs normal balls: strike rate, dot-ball share and wicket rate (top: by innings; bottom: within the same phase).")

    # ------------------------------------------------------------------ 2 performance
    h(doc, "2. Performance measurement")
    para(doc, (f"Expected runs. For each ball we take the average outcome of similar situations (competition name x innings x phase x wickets bucket "
               f"{cfg['expected']['wkt_edges'][:-1]}+ wickets), computed leave-one-out and blended with the format-level (T20 vs T20I) average using a pseudo-count of {cfg['expected']['k']} balls, "
               f"so small series do not produce noisy baselines. Batters are compared on bat runs off balls faced (wides excluded); bowlers on total runs including extras."))
    para(doc, (f"Value per ball. Batter = (runs - expected) minus {cfg['wk']:.0f} runs if dismissed (run-outs at the other end and retirements are not charged); "
               f"bowler = (expected - total runs) plus {cfg['wk']:.0f} per wicket credited to the bowler (run-outs, retired and obstruction excluded). "
               f"Each player gets a value on HP balls and on normal balls (own baseline)."))
    para(doc, (f"Win Probability Added (chases only). A gradient-boosted classifier uses runs needed, balls left, wickets lost and required rate to predict whether the batting side wins. "
               f"On a time-based hold-out (train on the earliest {wm['train_matches']} chased matches, test on the latest {wm['test_matches']}; {wm['test_balls']:,} test balls) it reaches accuracy {wm['test_accuracy']:.3f}, "
               f"log-loss {wm['test_logloss']:.3f} (constant-rate baseline {wm['baseline_logloss_constant']:.3f}), AUC {wm['test_auc']:.3f}. "
               f"Ratings use match-grouped {cfg['wpa']['n_splits']}-fold out-of-fold probabilities (accuracy {wm['oof_accuracy']:.3f}, log-loss {wm['oof_logloss']:.3f}), so no ball is scored by a model that saw its match. "
               f"WPA per ball = win probability after - before, weighted by leverage 4p(1-p); batters receive +WPA and bowlers -WPA. First-innings balls carry no WPA, and tied or super-over matches are excluded from it."))
    para(doc, (f"Setback recovery. Batters: value in the {cfg['recovery']['window']} balls after a wicket, for batters already at the crease (not the new arrival), minus the league average in the same situation. "
               f"Bowlers: value on the next delivery after the same bowler conceded a four or six in the same over, minus the league average."))
    w = cfg["rating_w"]
    para(doc, (f"Rating. Players need at least {cfg['min_hp']['bat']} HP balls (batters) or {cfg['min_hp']['bowl']} (bowlers) from at least {cfg['min_hp_matches']} matches with 3+ HP balls. "
               f"HP value and the player's normal-ball value are shrunk toward the league mean with an empirical-Bayes pseudo-count k={cfg['shrink_k']}; delta = shrunk HP value - shrunk normal value; "
               f"consistency = share of matches with positive HP value (shrunk to the league share, pseudo-count {cfg['consistency']['k']}); WPA and recovery are shrunk toward zero (k={cfg['wpa']['k']}, {cfg['recovery']['k']}). "
               f"Rating = {w['value']:.2f} z(HP value) + {w['delta']:.2f} z(delta) + {w['consistency']:.2f} z(consistency) + {w['wpa']:.2f} z(WPA) + {w['recovery']:.2f} z(recovery), with z-scores taken across eligible players. "
               f"Eligible: {len(bat_tab)} batters and {len(bowl_tab)} bowlers."))

    # ------------------------------------------------------------------ 3 fair comparisons
    h(doc, "3. Fair comparisons")
    ipl_b = (top_b["ipl_share_hp"] >= .5).sum()
    ipl_w = (top_w["ipl_share_hp"] >= .5).sum()
    para(doc, (f"Sample sizes. Every rated player has the minimum HP balls and match count above; the shrinkage pulls small samples toward the league mean, so a player must be consistently good over a real sample to rank. "
               f"The smallest HP samples in the lists are {int(top_b['n_hp'].min())} balls (batters) and {int(top_w['n_hp'].min())} balls (bowlers); the largest are {int(top_b['n_hp'].max())} and {int(top_w['n_hp'].max())}."))
    para(doc, (f"IPL vs T20I. Expected runs are computed per competition (blended with format averages), so a player is compared with what was typical in the same series, not with IPL scoring. "
               f"It does not adjust for opposition quality inside a series. {ipl_b} of the top-10 batters and {ipl_w} of the top-10 bowlers have at least half of their HP balls in the IPL; "
               f"the rest are driven mainly by international or development-team matches and cannot be compared like-for-like with IPL players. The ipl_share_hp and a_team_share_hp columns in the output tables show this per player."))
    ex_b = [names[i] for i in S["res_b"]["exclude A-team events"][:10]]
    ex_w = [names[i] for i in S["res_w"]["exclude A-team events"][:10]]
    dropped_w = [x for x in top_w["player_name"] if x not in ex_w]
    dropped_b = [x for x in top_b["player_name"] if x not in ex_b]
    para(doc, (f"A-team events. As agreed, development-team events (Emerging Teams Asia Cup, Asia Cup Rising Stars) are included. Excluding them changes the batter list by {len(dropped_b)} name(s) "
               f"({', '.join(dropped_b) if dropped_b else 'none'}) and the bowler list by {len(dropped_w)} ({', '.join(dropped_w) if dropped_w else 'none'}); the alternative lists are in alt_top10_excluding_A_team_events.csv."))
    para(doc, (f"Rain-revised games. {summ['rain_revised_matches']} matches had revised overs or targets. Revised overs are stored as balls in this data (30-114), so balls left, the target, the required rate and "
               f"the lateness signal use the revised ball count and revised target; phases still use the actual over number."))

    h(doc, "Auction availability", 2)
    ex_all = S["excluded_log"]
    ex = ex_all[ex_all["source"] != "nationality"]
    n_nat = int((ex_all["source"] == "nationality").sum())
    n_nat_rated = int(((ex_all["source"] == "nationality") & (ex_all["batting_data_rank"].notna() | ex_all["bowling_data_rank"].notna())).sum())
    asof = cfg["availability_as_of"]
    n_ret = int((ex_all["source"] == "retained").sum())
    n_ret_rated = int(((ex_all["source"] == "retained") & (ex_all["batting_data_rank"].notna() | ex_all["bowling_data_rank"].notna())).sum())
    rr_names = sorted(set(cfg["rr_retained"].values()))
    para(doc, (f"Rule. Players retired from the IPL or from all cricket as of {asof} are excluded from the final ranking because they cannot be signed at the auction. "
               f"Retention rule: players on the IPL 2027 retention lists of the other nine franchises (lists supplied {RETAIN_ASOF}; traded-in players count for their new team) are excluded because they will not reach the auction: "
               f"{n_ret} such players appear in the ball data, {n_ret_rated} of them in the rated pool. Players retained by Rajasthan Royals stay eligible. Names were matched to player IDs by exact name, else by membership of the same franchise's IPL 2026 squad in the data (retention_lists_2027_matched.csv). The filter is applied only after ratings and data ranks are computed: retired players' balls remain in every league average, "
               f"expected-runs baseline, shrinkage mean and the win-probability training set, so no other player's rating changes (verified against the previous run in checks_availability.txt). "
               f"Nationality rule: Pakistan players are not eligible to play in the IPL, so every player who appears in a Pakistan or Pakistan A squad in competition_team_player_mapping.csv is excluded "
               f"({n_nat} players in the ball data, {n_nat_rated} of them in the rated pool; listed below). This is derived from squad data, so a player who changed nationality or never appeared in a mapped squad would not be caught. "
               f"The final top 10 is the first 10 eligible players by data rank, with no gaps."))
    def rk(v, st):
        return f"{int(v)}" if not pd.isna(v) else "not rated"
    ex = ex[ex["source"] == "retired"]
    et = pd.DataFrame({"Player": ex["player"], "Status": ex["availability_status"], "Reason and date (as supplied)": ex["reason"],
                       "Batting data rank": [rk(v, s_) for v, s_ in zip(ex["batting_data_rank"], ex["batting_pool_status"])],
                       "Bowling data rank": [rk(v, s_) for v, s_ in zip(ex["bowling_data_rank"], ex["bowling_pool_status"])]})
    table(doc, et, widths=[1.1, 1.3, 2.6, 0.9, 0.9], size=7.5)
    nr = ex[(ex["source"] != "nationality") & (ex["batting_pool_status"].str.startswith("not in") | ex["bowling_pool_status"].str.startswith("not in"))]
    if len(nr):
        para(doc, "Not rated means the player did not meet the minimum high-pressure balls/matches in that role (" + "; ".join(
            f"{r.player}: batting - {r.batting_pool_status}, bowling - {r.bowling_pool_status}" for _, r in nr.iterrows()) + "), so the exclusion changes nothing for that role.", size=8.5, italic=True)
    ret_map = pd.read_csv(cfg["retention_file"]).dropna(subset=["player_id"]).set_index("player_id")
    for lab, tab in [("batters", S["bat_tab"]), ("bowlers", S["bowl_tab"])]:
        x = tab.head(15)
        pk = x[x["excluded"] & x["availability_status"].str.startswith("Not eligible")]
        rt = x[x["excluded"] & x["availability_status"].str.startswith("Retained")]
        if len(pk):
            para(doc, f"Pakistan-squad {lab} removed from the data-only top 15: " + ", ".join(f"{r.player_name} (data rank {int(r.data_rank)})" for _, r in pk.iterrows()) + ".", size=8.5)
        if len(rt):
            para(doc, f"Retained by other franchises, removed from the data-only top 15 {lab}: " + ", ".join(
                f"{r.player_name} ({ret_map.loc[i, 'team'] if i in ret_map.index else 'retained'}, rank {int(r.data_rank)})" for i, r in rt.iterrows()) + ".", size=8.5)
    man = ex_all[ex_all["source"] == "manual"]
    if len(man):
        para(doc, "Removed at the selector's request: " + "; ".join(f"{m.player} ({m.reason})" for _, m in man.iterrows()) + ".", size=8.5)
    rr_in = [r.player_name for _, r in pd.concat([top_b, top_w]).iterrows() if r.availability_status.startswith("Retained by RR")]
    para(doc, "Already at Rajasthan Royals and kept eligible, present in the final top 10: " + (", ".join(sorted(set(rr_in))) if rr_in else "none") + ".", size=8.5)
    ent = S["entrants"]
    if len(ent):
        para(doc, "Who moved into the top 10 because of the exclusions: " + "; ".join(
            f"{r.list[:-1]} #{r.final_rank} {r.player_name} (data rank {r.data_rank}, rating {r.rating:.2f}, {r.hp_balls} HP balls, {r.matches} matches, "
            f"{r.ipl_share_hp*100:.0f}% of HP balls in the IPL, in the top 10 in {r.share_of_scenarios_in_top10*100:.0f}% of scenarios"
            f"{'; robust' if r.robust_75pct else '; not robust'}{'; flags: ' + r.flag if r.flag else '; no sample/IPL/A-team flag'})" for _, r in ent.iterrows()) + ".", size=9)
    else:
        para(doc, "No player entered the top 10 because of the exclusions.", size=9)

    # ------------------------------------------------------------------ 4 evidence
    h(doc, "4. Evidence for the top 10")
    cols = ["final_rank", "player_name", "n_hp", "matches", "shrunk_hp_value", "delta", "consistency", "wpa_shrunk", "recovery", "rating"]
    def prep(tt):
        o = tt[cols].copy()
        o["n_hp"] = o["n_hp"].astype(int)
        o["matches"] = o["matches"].astype(int)
        o["wpa_shrunk"] = (o["wpa_shrunk"] * 1000)
        for c in ["shrunk_hp_value", "delta", "recovery", "rating"]:
            o[c] = o[c].map(lambda x: f"{x:.2f}")
        o["consistency"] = o["consistency"].map(lambda x: f"{x*100:.0f}%")
        o["wpa_shrunk"] = o["wpa_shrunk"].map(lambda x: f"{x:.1f}")
        o.columns = ["#", "Player", "HP balls", "Matches", "HP value/ball", "Delta", "Consist.", "WPA x1000", "Recovery", "Rating"]
        return o
    para(doc, "Top 10 batters", bold=True, size=9.5, after=2)
    table(doc, prep(top_b), widths=[0.3, 1.5, 0.6, 0.6, 0.8, 0.55, 0.6, 0.7, 0.65, 0.55], size=7.5)
    para(doc, "", after=2)
    para(doc, "Top 10 bowlers", bold=True, size=9.5, after=2)
    table(doc, prep(top_w), widths=[0.3, 1.5, 0.6, 0.6, 0.8, 0.55, 0.6, 0.7, 0.65, 0.55], size=7.5)
    caption(doc, "Table 1. HP value/ball and delta are in runs per ball (shrunk); consistency is the share of matches with positive HP value; WPA is per chase ball, shrunk.")
    tc = doc.add_table(rows=1, cols=2)
    tc.alignment = WD_TABLE_ALIGNMENT.CENTER
    for j_, fn_ in enumerate(["top10_batters.png", "top10_bowlers.png"]):
        tc.rows[0].cells[j_].paragraphs[0].add_run().add_picture(str(OUT / fn_), width=Inches(3.2))
    caption(doc, "Figure 2. Weighted z-score contributions to each rating (n = HP balls).")
    para(doc, "Why this order (batters)", bold=True, size=9.5, after=2)
    for _, r in S["bat_final"].head(10).iterrows():
        para(doc, f"{int(r['final_rank'])}. " + why(r, r["player_name"], cfg), size=8, after=0)
    para(doc, "Why this order (bowlers)", bold=True, size=9.5, after=2)
    for _, r in S["bowl_final"].head(10).iterrows():
        para(doc, f"{int(r['final_rank'])}. " + why(r, r["player_name"], cfg), size=8, after=0)

    # ---- explainability (SHAP)
    SHP = S["shap"]
    imp, mom, rsh, met = SHP["importance"], SHP["moments"], SHP["rating_shap"], SHP["metrics"]
    h(doc, "Explainability with SHAP", 2)
    top_f = imp.iloc[0]
    para(doc, (f"SHAP is used in two places. (1) The win-probability model: exact Shapley values (4 inputs, probability scale) on {met['shap_sample']:,} of the {met['wpa_balls_used']:,} chase balls show what the model relies on. "
               f"Mean absolute effect in win-probability points: " + "; ".join(f"{r.label} {r.mean_abs_shap_pp:.1f}" for _, r in imp.iterrows()) +
               f". Higher values of every input lower the batting side's chance (largest driver: {top_f.label.lower()}). "
               f"(2) The rating itself: it is a weighted sum of five z-scores, so shap.LinearExplainer gives its exact Shapley decomposition against the average rated player (maximum reconstruction error {met['rating_decomposition_max_abs_error']:.1e}). "
               f"Figure 3 shows the rank-1 batter and bowler; every player's waterfall is in outputs/shap/."), size=9)
    def wf(role, rank):
        nm = (S["top_b"] if role == "batter" else S["top_w"]).iloc[rank - 1]["player_name"]
        return OUT / "shap" / f"waterfall_{role}_{rank:02d}_{re.sub('[^A-Za-z0-9]+', '_', nm)}.png"
    t3 = doc.add_table(rows=1, cols=2)
    t3.alignment = WD_TABLE_ALIGNMENT.CENTER
    for j, role in enumerate(["batter", "bowler"]):
        t3.rows[0].cells[j].paragraphs[0].add_run().add_picture(str(wf(role, 1)), width=Inches(3.0))
    caption(doc, "Figure 3. SHAP waterfall of the rating for the rank-1 batter (left) and bowler (right): starts at 0 for the average rated player and adds each component's exact contribution.")
    ex_rows = []
    for role in ["batter", "bowler"]:
        m_ = mom[(mom.role == role) & (mom.final_rank == 1)].sort_values("impact_pp", ascending=False).iloc[0]
        ex_rows.append(f"{m_.player_name} ({m_.match_date}, vs {m_.vs}, over {m_.over}, {m_.outcome}): needed {m_.runs_needed} off {m_.balls_left} with {m_.wickets_lost} down; his side's win probability "
                       f"{m_.win_prob_before_pct:.0f}% to {m_.win_prob_after_pct:.0f}% ({m_.impact_pp:+.1f} points), driven by {m_.driver1.lower()} ({m_.driver1_pp:+.1f}) and {m_.driver2.lower()} ({m_.driver2_pp:+.1f}).")
    para(doc, ("Key moments. For every top-10 player the three chase balls with the largest win-probability swing are decomposed with SHAP (the change in each input's contribution adds up to the model's change; maximum error "
               f"{met['decomposition_max_abs_error_pp']:.1e} points). Examples - " + " ".join(ex_rows) + " The full list of 60 moments is in outputs/shap/key_moments.csv and in the dashboard."), size=9)

    # year by year
    para(doc, "", after=2)
    h(doc, "Year-by-year, big-game and winning-contribution views", 2)
    sbs, sws = S["batters_seasonstats"], S["bowlers_seasonstats"]
    def sy(tt, lab):
        n3 = int((tt["seasons_rated"] >= 3).sum())
        pos = tt["share_seasons_above_avg"].mean()
        return (f"{lab}: {n3} of 10 have 3+ rated seasons (needed for a trend slope); on average they are above the season average in {pos*100:.0f}% of the seasons in which they are rated, "
                f"and the median season-to-season standard deviation of their rating is {tt['rating_variability_sd'].median():.2f}.")
    para(doc, sy(sbs, "Batters") + " " + sy(sws, "Bowlers") + " Season ratings are recomputed with lower minimums (30 / 25 HP balls) and z-scored within each season, so they are noisy; see the heatmaps and year_by_year_*.csv.")
    t2 = doc.add_table(rows=1, cols=2)
    t2.alignment = WD_TABLE_ALIGNMENT.CENTER
    for j, fn in enumerate(["heatmap_batters.png", "heatmap_bowlers.png"]):
        c = t2.rows[0].cells[j]
        c.paragraphs[0].add_run().add_picture(str(OUT / fn), width=Inches(3.0))
    caption(doc, "Figure 4. Season ratings of the top 10 (blank = below the season minimum).")
    bgb, bgw = S["bgb"], S["bgw"]
    have_b, have_w = int((bgb["ko_innings"] > 0).sum()), int((bgw["ko_innings"] > 0).sum())
    para(doc, (f"Knockouts and finals are rare ({int(S['df'].loc[S['df'].is_ko,'match_id'].nunique())} matches). {have_b} of the 10 batters and {have_w} of the 10 bowlers have any knockout/final appearance in the data, "
               f"with at most {int(bgb['ko_innings'].max())} (batters) and {int(bgw['ko_innings'].max())} (bowlers) such innings; knockout value is shrunk toward the player's own normal value with a pseudo-count of {cfg['knockout_k']} balls "
               f"and is shown for context only - it is not in the rating (bigame_*.csv)."))
    wcb, wcw = S["wcb"], S["wcw"]
    para(doc, (f"Winning contribution (HP value in matches the team won vs lost): {int((wcb['win_minus_loss']>0).sum())} of 10 batters and {int((wcw['win_minus_loss']>0).sum())} of 10 bowlers have a higher HP value in wins, "
               f"which is expected because wins are partly caused by good HP performance; the gap is informational (winning_contribution_*.csv). Role views (finishers, rebuilders, death defenders, pace vs spin) and "
               f"series/tournament totals for every top-10 player are saved as roleview_*.csv and series_totals_*.csv; player_profile(name) in analysis.py returns all of this for any selected player."))

    # ------------------------------------------------------------------ 5 reliability
    h(doc, "5. Reliability and limitations")
    sd = stab.copy()
    sd["Role"] = sd["role"].map({"bat": "Batters", "bowl": "Bowlers"})
    out = pd.DataFrame({"Role": sd["Role"], "Split": sd["label"], "Top-10 overlap": sd["top10_overlap"].astype(int),
                        "Common eligible": sd["n_common_eligible"].astype(int), "Rank corr.": sd["spearman"].map(lambda x: f"{x:.2f}"),
                        "Half A in full top 10": sd["a_vs_full"].astype(int), "Half B in full top 10": sd["b_vs_full"].astype(int)})
    table(doc, out, widths=[0.8, 1.6, 0.9, 0.9, 0.8, 1.0, 1.0], size=7.5)
    caption(doc, f"Table 2. Stability. Each half is rated separately with minimums of {cfg['half_min_hp']['bat']} (batters) / {cfg['half_min_hp']['bowl']} (bowlers) HP balls.")
    db, dw = diag[diag.role == "bat"].iloc[0], diag[diag.role == "bowl"].iloc[0]
    para(doc, (f"Stability is weak. Rating players on 2022-23 and on 2024-onwards separately gives a top-10 overlap of {int(stab.iloc[0].top10_overlap)} (batters) and {int(stab.iloc[2].top10_overlap)} (bowlers); odd vs even matches give "
               f"{int(stab.iloc[1].top10_overlap)} and {int(stab.iloc[3].top10_overlap)}. The split-half correlation of raw HP value per ball is {db.split_half_r:.2f} for batters (Spearman-Brown corrected {db.spearman_brown_r:.2f}) "
               f"and {dw.split_half_r:.2f} for bowlers ({dw.spearman_brown_r:.2f}). A method-of-moments estimate puts the true-skill share of the spread in HP value at {db.share_true_signal*100:.0f}% for batters "
               f"and {dw.share_true_signal*100:.0f}% for bowlers, implying an empirical-Bayes k of about {db.eb_k_estimate:.0f} (batters) and {dw.eb_k_estimate:.0f} (bowlers) versus the k={cfg['shrink_k']} used. "
               f"Pressure performance over a few hundred balls is dominated by noise, especially for bowlers, so differences between neighbouring ranks are not meaningful."))
    pic(doc, OUT / "sensitivity_robustness.png", 4.8)
    caption(doc, f"Figure 5. Share of {nscen} sensitivity scenarios in which each player is in the top 10.")
    sm = sens[sens.scenario != "base"]
    rb = fb[fb.in_base_top10 & (fb.share_in_top10 >= .75)]["player_name"].tolist()
    rw = fw[fw.in_base_top10 & (fw.share_in_top10 >= .75)]["player_name"].tolist()
    weak_b = fb[fb.in_base_top10 & (fb.share_in_top10 < .6)]["player_name"].tolist()
    weak_w = fw[fw.in_base_top10 & (fw.share_in_top10 < .6)]["player_name"].tolist()
    out_b = fb[~fb.in_base_top10 & (fb.share_in_top10 >= .5)]["player_name"].tolist()
    out_w = fw[~fw.in_base_top10 & (fw.share_in_top10 >= .5)]["player_name"].tolist()
    para(doc, (f"Sensitivity. Scenarios vary the pressure weights, the HP cutoff (20/25/30%), the wicket value (6/10), minimum balls (+/-33%), the WPA weight (0 / 1.0), the shrinkage k (50/200/400), the minimum-match rule and A-team exclusion. "
               f"The average overlap with the base top 10 is {sm.batter_overlap_with_base.mean():.1f} (batters, minimum {int(sm.batter_overlap_with_base.min())}) and {sm.bowler_overlap_with_base.mean():.1f} (bowlers, minimum {int(sm.bowler_overlap_with_base.min())}). "
               f"Robust batters (>=75% of scenarios): {', '.join(rb) if rb else 'none'}. Robust bowlers: {', '.join(rw) if rw else 'none'}. "
               f"Less robust members (<60%): {', '.join(weak_b + weak_w) if (weak_b or weak_w) else 'none'}. Players outside the list who appear in at least half of scenarios: "
               f"{', '.join(out_b + out_w) if (out_b or out_w) else 'none'}. Full tables: sensitivity_scenarios.csv and sensitivity_robustness_*.csv."))
    flagged = pd.concat([top_b.assign(role="batter"), top_w.assign(role="bowler")])
    flagged = flagged[flagged["flag"].fillna("") != ""]
    if len(flagged):
        para(doc, "Surprises flagged. " + "; ".join(f"{r.player_name} ({r.role}, rank {int(r['final_rank'])}, {int(r.n_hp)} HP balls): {r.flag}" for _, r in flagged.iterrows()) +
             ". These are kept because they meet the stated minimums, but their position should be treated as lower-confidence than players with large IPL samples.")
    para(doc, ("Limitations. (1) No fielding or catching data, so fielding value is ignored and run-outs are excluded from both batter penalty at the other end and bowler credit. "
               "(2) Weights in the pressure score, the rating and the wicket value are judgement calls; the sensitivity table shows what they move. "
               "(3) IPL and T20I (and development-team) conditions differ and opposition quality is not modelled inside a series; baselines are per competition only. "
               "(4) The win-probability model uses only chase state (no team strength, venue or dew), covers chases only, and its ball-level WPA is noisy. "
               "(5) Pressure performance is a small-sample quantity; the estimated true-signal share above is the honest ceiling on how well any ranking can do from this data. "
               "(6) Byes and leg-byes are charged to bowlers' total runs as specified. (7) Rain-revised phases use the actual over number."), size=9)
    para(doc, ("Reproduce: python analysis.py (fixed seed " + str(cfg["seed"]) + "; config at the top of the file) regenerates every CSV, PNG, the two plain-text final lists and this report."), size=8.5, italic=True)
    doc.add_page_break() if False else None
    h(doc, "Appendix: data-only top 15 and final top 10", 1)
    para(doc, "Left: the data-only ranking before any availability filter (excluded players marked). Right: the final top 10 after exclusion (same order as final_top10_*.txt).", size=8.5)
    def appx(tab, fin):
        rows = []
        for i in range(20):
            r = tab.iloc[i]
            st_ = str(r["availability_status"]).replace("Not eligible for IPL (Pakistan)", "Pakistan").replace("Retained (official)", "Retained elsewhere")
            rows.append([int(r["data_rank"]), r["player_name"] + (" (excluded)" if r["excluded"] else ""), f"{r['rating']:.2f}",
                         st_ if (r["excluded"] or st_.startswith("Retained by RR")) else "", i + 1 if i < 20 else "", fin.iloc[i]["player_name"] if i < 20 else ""])
        return pd.DataFrame(rows, columns=["Data #", "Player", "Rating", "Status", "Final #", "Final top 20"])
    def appx2(tab, fin):
        rows = []
        for i in range(15):
            r = tab.iloc[i]
            rows.append([int(r["data_rank"]), r["player_name"] + (" (excl.)" if r["excluded"] else (" (RR)" if str(r["availability_status"]).startswith("Retained by RR") else "")),
                         f"{r['rating']:.2f}", i + 1 if i < 10 else "", fin.iloc[i]["player_name"] if i < 10 else ""])
        return rows
    rb_, rw_ = appx2(S["bat_tab"], S["bat_final"]), appx2(S["bowl_tab"], S["bowl_final"])
    comb = pd.DataFrame([a_ + b_ for a_, b_ in zip(rb_, rw_)], columns=["Data #", "Batter (data order)", "Rating", "Final #", "Final player", "Data #", "Bowler (data order)", "Rating", "Final #", "Final player"])
    para(doc, "(excl.) = removed from the final ranking: retired, Pakistan squad, or retained by another franchise. (RR) = already a Rajasthan Royals player, kept eligible. Left block batters, right block bowlers.", size=8, after=2)
    table(doc, comb, widths=[0.3, 1.35, 0.4, 0.3, 1.2, 0.3, 1.35, 0.4, 0.3, 1.2], size=6.5)
    doc.save(OUT / "Methodology_Report.docx")
