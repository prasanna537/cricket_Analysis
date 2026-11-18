"""Step 2 of 2: cleans the bundle (drops availability details) and adds the SHAP tables -> dashboard-next/data/dash.json."""
import tempfile
import json
import numpy as np
import pandas as pd

from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
TMP = Path(tempfile.gettempdir())
SH = str(ROOT / "outputs" / "shap")
d = json.load(open(TMP / "dash_data_intermediate.json"))
for k in ["data15", "excluded", "diag", "bat20", "bowl20"]:
    d.pop(k, None)
for k in ["nat_excluded", "availability_as_of"]:
    d["summary"][0].pop(k)
for k in ["bat", "bowl"]:
    for r in d[k]:
        r.pop("data_rank", None)


def clean(v):
    if isinstance(v, (np.integer,)): return int(v)
    if isinstance(v, (np.floating, float)): return None if np.isnan(v) else float(v)
    if isinstance(v, np.bool_): return bool(v)
    return v


def recs(df):
    return [{k: clean(v) for k, v in r.items()} for r in df.to_dict("records")]


imp = pd.read_csv(SH + "/wpa_global_importance.csv")
dep = pd.read_csv(SH + "/wpa_dependence_binned.csv")
mom = pd.read_csv(SH + "/key_moments.csv")
rs = pd.read_csv(SH + "/rating_shap.csv")
chk = pd.read_csv(SH + "/shap_checks.csv", index_col=0)["value"]
for r in d["robust"]:
    r["share20_pct"] = (r["share_in_top20"] or 0) * 100
d["wpa_importance"] = recs(imp)
d["wpa_dependence"] = recs(dep)
d["moments"] = recs(mom)
d["rating_shap"] = recs(rs.drop(columns=["player_id"]))
d["shap_meta"] = [dict(sample=int(float(chk["shap_sample"])), background=int(float(chk["background"])), balls=int(float(chk["wpa_balls_used"])),
                       wpa_err=float(chk["decomposition_max_abs_error_pp"]), rating_err=float(chk["rating_decomposition_max_abs_error"]))]
json.dump(d, open(ROOT / "dashboard-next" / "data" / "dash.json", "w"), indent=1, allow_nan=False)
txt = json.dumps(d).lower()
print("leaks:", [w for w in ["retire", "pakistan", "karthik", "russell", "bravo", "muqeem", "afridi", "abrar", "nawaz", "shadab"] if w in txt])
print({k: len(v) for k, v in d.items()})
