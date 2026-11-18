import raw from "@/data/dash.json";
import StackBar from "./StackBar";

const D: any = raw;
const S = D.summary[0];
const COLORS = ["var(--c0)", "var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)"];
const COMP: [string, string][] = [
  ["w_value", "Pressure value"],
  ["w_delta", "Lift over own baseline"],
  ["w_consistency", "Consistency"],
  ["w_wpa", "Win probability added"],
  ["w_recovery", "Setback recovery"],
];
const f = (v: number | null | undefined, d = 2) => (v == null || Number.isNaN(+v) ? "–" : (+v).toFixed(d));
const sg = (v: number | null | undefined, d = 2) => (v == null ? "–" : (+v >= 0 ? "+" : "") + (+v).toFixed(d));

const allRows: any[] = [...D.bat, ...D.bowl];
let lo = 0, hi = 0;
for (const r of allRows) {
  let p = 0, n = 0;
  for (const [k] of COMP) { const v = r[k] || 0; if (v >= 0) p += v; else n += v; }
  hi = Math.max(hi, p); lo = Math.min(lo, n);
}

function Legend() {
  return (
    <div className="legend" aria-label="Rating components">
      {COMP.map(([, l], i) => <span key={l}><i style={{ background: COLORS[i] }} />{l}</span>)}
    </div>
  );
}


const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const fdate = (iso: string) => { const [y, m, d] = iso.split("-"); return `${+d} ${MONTHS[+m - 1]} ${y}`; };
const FMT: Record<string, (v: number) => string> = {
  "Pressure value": (v) => f(v),
  "Lift over own baseline": (v) => sg(v),
  "Consistency": (v) => `${f(v * 100, 0)}%`,
  "Win probability added": (v) => sg(v * 1000, 1),
  "Setback recovery": (v) => sg(v),
};
const UNIT: Record<string, string> = {
  "Pressure value": "runs per ball",
  "Lift over own baseline": "runs per ball",
  "Consistency": "share of matches positive",
  "Win probability added": "per 1,000 chase balls",
  "Setback recovery": "runs per ball",
};

function Waterfall({ parts, rating }: { parts: any[]; rating: number }) {
  let cum = 0;
  const steps = parts.map((p) => { const a = cum; cum += p.shap_contribution; return { ...p, a, b: cum }; });
  const lo = Math.min(0, ...steps.map((s) => Math.min(s.a, s.b)));
  const hi = Math.max(rating, ...steps.map((s) => Math.max(s.a, s.b))) * 1.02;
  const x = (v: number) => ((v - lo) / (hi - lo)) * 100;
  return (
    <div className="wf" role="img" aria-label={`Rating builds from 0 to ${f(rating)}`}>
      {steps.map((s, i) => (
        <div className="wfrow" key={s.component}>
          <span className="wflab">{s.component}</span>
          <div className="wftrack">
            <i className="wfzero" style={{ left: `${x(0)}%` }} />
            <i className="wfbar" style={{ left: `${x(Math.min(s.a, s.b))}%`, width: `${Math.max(0.6, x(Math.max(s.a, s.b)) - x(Math.min(s.a, s.b)))}%`, background: s.shap_contribution >= 0 ? COLORS[i] : "var(--bad)" }} />
          </div>
          <span className="wfval">{sg(s.shap_contribution)}</span>
        </div>
      ))}
      <div className="wfrow total">
        <span className="wflab">Rating</span>
        <div className="wftrack"><i className="wfzero" style={{ left: `${x(0)}%` }} /><i className="wfbar" style={{ left: `${x(0)}%`, width: `${x(rating) - x(0)}%`, background: "var(--fg)" }} /></div>
        <span className="wfval">{f(rating)}</span>
      </div>
    </div>
  );
}

function Why({ r }: { r: any }) {
  const parts = D.rating_shap.filter((q: any) => q.role === r.role && q.player_name === r.player_name);
  const moms = D.moments.filter((q: any) => q.role === r.role && q.player_name === r.player_name);
  if (!parts.length) return null;
  return (
    <details className="more">
      <summary>Why this rank: SHAP breakdown and key moments</summary>
      <div className="morebody">
        <h4>How the rating is built</h4>
        <p className="muted small">Starts at 0 for the average rated player. Each step is that component&apos;s exact SHAP contribution: its weight times how far the player is above or below the average rated player.</p>
        <Waterfall parts={parts} rating={parts[0].rating} />
        <div className="tablewrap">
          <table className="small">
            <thead><tr><th>Component</th><th className="n">This player</th><th className="n">Average rated player</th><th className="n">Z-score</th><th className="n">Weight</th><th className="n">Adds</th></tr></thead>
            <tbody>
              {parts.map((p: any) => (
                <tr key={p.component}>
                  <td>{p.component}<div className="muted unit">{UNIT[p.component]}</div></td>
                  <td className="n">{FMT[p.component](p.player_value)}</td>
                  <td className="n">{FMT[p.component](p.rated_player_average)}</td>
                  <td className="n">{sg(p.z_score)}</td>
                  <td className="n">{f(p.weight)}</td>
                  <td className="n"><b>{sg(p.shap_contribution)}</b></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {moms.length > 0 && (
          <>
            <h4>Biggest pressure moments</h4>
            <p className="muted small">The chase balls that moved this player&apos;s side&apos;s win probability the most. The two drivers are SHAP contributions from the win-probability model: how much each change in the match state (runs needed, balls left, wickets, required rate) added.</p>
            <ul className="moments">
              {moms.map((m: any, i: number) => (
                <li key={i}>
                  <div className="mhead"><b>{fdate(m.match_date)}</b> vs {m.vs} · over {m.over} · {m.outcome}</div>
                  <div className="mbody">
                    Needed <b>{m.runs_needed}</b> off <b>{m.balls_left}</b> with <b>{m.wickets_lost}</b> down. Win probability <b>{f(m.win_prob_before_pct, 0)}%</b> to <b>{f(m.win_prob_after_pct, 0)}%</b> (<b>{sg(m.impact_pp, 1)}</b> pts).
                    <span className="muted"> Driven by {m.driver1.toLowerCase()} ({sg(m.driver1_pp, 1)}) and {m.driver2.toLowerCase()} ({sg(m.driver2_pp, 1)}).</span>
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </details>
  );
}

function DepChart({ feat }: { feat: string }) {
  const rows = D.wpa_dependence.filter((q: any) => q.feature === feat);
  const W = 220, H = 110, pad = 26;
  const xs = rows.map((q: any) => q.x), ys = rows.map((q: any) => q.shap_pp);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), ym = Math.max(...ys.map(Math.abs), 1);
  const X = (v: number) => pad + ((v - x0) / (x1 - x0 || 1)) * (W - pad - 6);
  const Y = (v: number) => H / 2 - (v / ym) * (H / 2 - 8);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="dep" role="img" aria-label={`SHAP contribution versus ${rows[0].label}`}>
      <line x1={pad} x2={W - 6} y1={Y(0)} y2={Y(0)} stroke="var(--axis)" strokeWidth={1} />
      <polyline points={rows.map((q: any) => `${X(q.x)},${Y(q.shap_pp)}`).join(" ")} fill="none" stroke={COLORS[0]} strokeWidth={2} />
      {rows.map((q: any, i: number) => <circle key={i} cx={X(q.x)} cy={Y(q.shap_pp)} r={2.5} fill={COLORS[0]} />)}
      <text x={pad - 4} y={12} textAnchor="end" fontSize={9} fill="var(--fg-muted)">+{f(ym, 0)}</text>
      <text x={pad - 4} y={H - 4} textAnchor="end" fontSize={9} fill="var(--fg-muted)">-{f(ym, 0)}</text>
      <text x={pad} y={H - 1} fontSize={9} fill="var(--fg-muted)">{f(x0, 0)}</text>
      <text x={W - 6} y={H - 1} fontSize={9} textAnchor="end" fill="var(--fg-muted)">{f(x1, 0)}</text>
    </svg>
  );
}

function ShapSection() {
  const imp = [...D.wpa_importance].sort((a: any, b: any) => b.mean_abs_shap_pp - a.mean_abs_shap_pp);
  const mx = Math.max(...imp.map((q: any) => q.mean_abs_shap_pp));
  const M = D.shap_meta[0];
  return (
    <section className="sec" id="explain">
      <h2>What drives win probability (SHAP)</h2>
      <p className="lede">
        The win-probability model scores every ball of a chase. SHAP splits each prediction into the share owed to each input, in percentage points of win probability, so a player&apos;s credit for a big hit can be traced to what actually changed in the match.
        Computed exactly on <b>{M.sample.toLocaleString("en-US")}</b> chase balls out of <b>{M.balls.toLocaleString("en-US")}</b>; per-ball breakdowns add up to the model&apos;s change with a maximum error of <b>{M.wpa_err < 1e-9 ? "0" : f(M.wpa_err, 6)}</b> points.
      </p>
      <div className="two">
        <div>
          <h3>Average size of each input&apos;s effect</h3>
          {imp.map((q: any) => (
            <div className="rob" key={q.feature}>
              <span className="hn">{q.label}</span>
              <div className="track"><i style={{ width: `${(q.mean_abs_shap_pp / mx) * 100}%`, background: COLORS[0] }} /></div>
              <span className="v">{f(q.mean_abs_shap_pp, 1)}</span>
            </div>
          ))}
          <p className="muted small" style={{ marginTop: 8 }}>Points of win probability moved, on average. Higher values of every input lower the batting side&apos;s chance. Balls left matters little once runs needed and the required rate are known.</p>
        </div>
        <div>
          <h3>How each input pushes the prediction</h3>
          <div className="depgrid">
            {["runs_needed", "rrr", "wickets_before", "balls_left"].map((k) => (
              <div key={k}><span className="muted small">{D.wpa_dependence.find((q: any) => q.feature === k).label}</span><DepChart feat={k} /></div>
            ))}
          </div>
          <p className="muted small">Each dot is a slice of chase balls. Above the line the input is helping the batting side; below it, hurting.</p>
        </div>
      </div>
      <p className="note">
        Why this matters for the rankings: the rating&apos;s win-probability-added component sums these model changes ball by ball. The per-player breakdowns above also use SHAP, on the rating itself.
        Because the rating is a weighted sum of five scores, its SHAP values are exact (maximum error <b>{M.rating_err < 1e-9 ? "0" : f(M.rating_err, 6)}</b>), not an approximation.
      </p>
    </section>
  );
}

function PlayerList({ rows }: { rows: any[] }) {
  return (
    <ol className="list">
      {rows.map((r) => {
        const rob = D.robust.find((q: any) => q.player_name === r.player_name && q.role === r.role);
        const good = rob && rob.share_pct >= 75;
        return (
          <li className="item" key={r.player_name}>
            <div className="rank">{r.final_rank}</div>
            <div>
              <div className="head">
                <span className="name">{r.player_name}</span>
                <span className="rating">rating <b>{f(r.rating)}</b></span>
              </div>
              <StackBar
                parts={COMP.map(([k, l], i) => ({ label: l, value: r[k] || 0, color: COLORS[i] }))}
                lo={lo} hi={hi}
                aria={`${r.player_name} rating components: ${COMP.map(([k, l]) => `${l} ${sg(r[k])}`).join(", ")}`}
              />
              <div className="meta">{f(r.n_hp, 0)} HP balls · {f(r.matches, 0)} matches · {f(r.ipl_share_pct, 0)}% of HP balls in the IPL</div>
              <p className="why">{r.why}</p>
              <div className="chips">
                {rob && <span className={`chip ${good ? "ok" : "warn"}`}>{good ? "Robust" : "Less robust"} · {f(rob.share_pct, 0)}% of stress tests</span>}
                {r.at_rr && <span className="chip rr">Already at RR</span>}
                {r.flag && <span className="chip warn">{r.flag}</span>}
              </div>
              <Why r={r} />
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function Vbars({ metric }: { metric: string }) {
  const pick = (inn: string, seg: string) => D.validation.find((r: any) => r.group === "all balls" && r.innings === inn && r.segment === seg);
  const max = Math.max(...["1", "2"].flatMap((i) => ["Normal", "High pressure"].map((s) => pick(i, s)[metric])));
  return (
    <div>
      {["1", "2"].map((inn) => (
        <div className="vrow" key={inn}>
          <span className="muted">Innings {inn}</span>
          <div>
            {["Normal", "High pressure"].map((seg, k) => {
              const v = pick(inn, seg)[metric];
              return (
                <div className="vb" key={seg}>
                  <i style={{ width: `${Math.max(2, (v / max) * 78)}%`, background: COLORS[k] }} />
                  <span>{f(v, 1)}</span>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

function Robust({ role }: { role: string }) {
  const rows = D.robust.filter((x: any) => x.role === role).sort((a: any, b: any) => b.share_pct - a.share_pct).slice(0, 14);
  return (
    <div>
      {rows.map((x: any) => (
        <div className="rob" key={x.player_name}>
          <span className="hn">{x.player_name}</span>
          <div className="track"><i style={{ width: `${x.share_pct}%`, background: x.in_base_top10 ? COLORS[1] : "var(--muted-bar)" }} /></div>
          <span className="v">{f(x.share_pct, 0)}%</span>
        </div>
      ))}
    </div>
  );
}

function Heat({ role }: { role: string }) {
  const rows = D.season.filter((x: any) => x.role === role);
  const years = Array.from(new Set(rows.map((x: any) => x.year))).sort() as number[];
  const names: string[] = [];
  [...rows].sort((a: any, b: any) => a.final_rank - b.final_rank).forEach((x: any) => { if (!names.includes(x.player_name)) names.push(x.player_name); });
  return (
    <div className="heat" style={{ gridTemplateColumns: `minmax(0,1fr) repeat(${years.length}, 42px)` }}>
      <span />
      {years.map((y) => <span className="hh" key={y}>{y}</span>)}
      {names.map((nm) => (
        <FragmentRow key={nm} nm={nm} years={years} rows={rows} />
      ))}
    </div>
  );
}
function FragmentRow({ nm, years, rows }: { nm: string; years: number[]; rows: any[] }) {
  return (
    <>
      <span className="hn">{nm}</span>
      {years.map((y) => {
        const r = rows.find((x) => x.player_name === nm && x.year === y);
        const has = r && r.rating != null;
        const a = has ? Math.min(70, Math.abs(r.rating) * 22) : 0;
        return (
          <span className="hc" key={y} style={has ? { background: `color-mix(in srgb, ${r.rating >= 0 ? "var(--ok)" : "var(--bad)"} ${a}%, transparent)` } : undefined}>
            {has ? f(r.rating, 1) : ""}
          </span>
        );
      })}
    </>
  );
}

export default function Page() {
  const b0 = D.bat[0], w0 = D.bowl[0];
  const v = (inn: string, seg: string) => D.validation.find((r: any) => r.group === "all balls" && r.innings === inn && r.segment === seg);
  const h1 = v("1", "High pressure"), n1 = v("1", "Normal"), h2 = v("2", "High pressure"), n2 = v("2", "Normal");
  return (
    <main className="wrap">
      <header className="top">
        <h1>Most Reliable Players Under Pressure</h1>
        <p className="muted">SuperRR Selector Season 2, Round 1 · which batters and bowlers RR should back at the IPL 2027 auction</p>
        <p className="take">
          <b>{b0.player_name}</b> leads the batters (rating <b>{f(b0.rating)}</b>) and <b>{w0.player_name}</b> leads the bowlers (<b>{f(w0.rating)}</b>).{" "}
          <b>{S.robust_bat}</b> of 10 batters and <b>{S.robust_bowl}</b> of 10 bowlers stay in the top 10 in at least 75% of <b>{S.n_scen}</b> stress tests.
          Treat the order as a shortlist: only about <b>{f(S.true_signal_bat_pct, 0)}%</b> (batters) and <b>{f(S.true_signal_bowl_pct, 0)}%</b> (bowlers) of the
          differences in pressure value look like real skill rather than noise.
        </p>
        <nav className="nav" aria-label="Sections">
          <a href="#final">The final 10</a><a href="#method">How we measured it</a><a href="#explain">What drives win probability</a><a href="#trust">How far to trust it</a>
        </nav>
      </header>

      <section className="sec" id="final">
        <h2>The final 10</h2>
        <p className="lede">Ranked by a pressure rating built only from the supplied ball-by-ball data. Each bar shows what pushed the rating up (right) or down (left); the sentence under it names the two biggest reasons.</p>
        <Legend />
        <div className="two">
          <div><h3>Batters</h3><PlayerList rows={D.bat} /></div>
          <div><h3>Bowlers</h3><PlayerList rows={D.bowl} /></div>
        </div>
        <p className="muted" style={{ fontSize: 12 }}>HP balls = balls bowled or faced in high-pressure moments. A <i>Robust</i> tag means the player stays in the top 10 in at least 75% of the stress tests described under How far to trust it.</p>
      </section>

      <section className="sec" id="method">
        <h2>How we measured it</h2>
        <p className="lede">Reputation plays no part. Every ball gets a pressure score from the match state before it. We then ask who did better than similar situations usually produce, when it mattered most.</p>
        <div className="steps">
          <div className="step"><span className="tag">Step 1</span><h3>Score the pressure on every ball</h3><p>Seven signals (table below), scaled 0 to 1 and weighted. Chases and first innings use different mixes. Rain-revised games use the revised ball count and target.</p></div>
          <div className="step"><span className="tag">Step 2</span><h3>Pick the high-pressure balls</h3><p>The top <b>{f(S.hp_quantile_pct, 0)}%</b> of balls in each innings by pressure score.</p></div>
          <div className="step"><span className="tag">Step 3</span><h3>Compare with similar situations</h3><p>Expected runs come from the same competition, innings, phase and wickets lost. A batter&apos;s value per ball is runs above that, minus <b>{f(S.wk, 0)}</b> runs for a dismissal. A bowler&apos;s is runs saved, plus the same credit per wicket.</p></div>
          <div className="step"><span className="tag">Step 4</span><h3>Add three more signals</h3><p>Win probability added in chases (gradient-boosted model, scored out-of-fold), recovery after a setback, and the share of matches with a positive pressure value.</p></div>
          <div className="step"><span className="tag">Step 5</span><h3>Shrink small samples</h3><p>Each value is pulled toward the league mean with a pseudo-count of <b>{f(S.shrink_k, 0)}</b> balls. Players need <b>{f(S.min_hp_bat, 0)}</b> (batters) or <b>{f(S.min_hp_bowl, 0)}</b> (bowlers) HP balls, from at least <b>{f(S.min_hp_matches, 0)}</b> matches.</p></div>
          <div className="step"><span className="tag">Step 6</span><h3>Combine and rank</h3><p>The five components become z-scores and are added with the weights below to give the rating.</p></div>
        </div>

        <h3 style={{ marginTop: 8 }}>The pressure score: signals and weights</h3>
        <div className="tablewrap">
          <table>
            <thead><tr><th>Innings</th><th>Signal</th><th className="n">Weight</th><th>Why it signals pressure</th></tr></thead>
            <tbody>{D.signals.map((r: any) => <tr key={r.innings + r.signal}><td>{r.innings}</td><td>{r.signal}</td><td className="n">{f(r.weight)}</td><td>{r.why}</td></tr>)}</tbody>
          </table>
        </div>

        <h3 style={{ marginTop: 8 }}>The rating: components and weights</h3>
        <div className="tablewrap">
          <table>
            <thead><tr><th>Component</th><th className="n">Weight</th><th>What it measures</th></tr></thead>
            <tbody>{D.weights.map((r: any) => <tr key={r.component}><td>{r.component}</td><td className="n">{f(r.weight)}</td><td>{r.meaning}</td></tr>)}</tbody>
          </table>
        </div>

        <h3 style={{ marginTop: 8 }}>Does the pressure score find hard moments?</h3>
        <p className="lede">High-pressure balls (orange) against normal balls (blue). Wickets fall far more often under pressure. Strike rate and dot balls do not move one way in every innings: high-pressure balls are mostly death overs, and chasing batters accelerate.</p>
        <div className="legend"><span><i style={{ background: COLORS[0] }} />Normal</span><span><i style={{ background: COLORS[1] }} />High pressure</span></div>
        <div className="vgrid">
          <div><h3>Strike rate</h3><Vbars metric="strike_rate" /></div>
          <div><h3>Dot balls (%)</h3><Vbars metric="dot_pct" /></div>
          <div><h3>Wickets per 100 balls</h3><Vbars metric="wickets_per_100" /></div>
        </div>
        <p className="note">
          Wickets per 100 balls: <b>{f(h1.wickets_per_100, 1)}</b> vs <b>{f(n1.wickets_per_100, 1)}</b> in innings 1 and <b>{f(h2.wickets_per_100, 1)}</b> vs <b>{f(n2.wickets_per_100, 1)}</b> in innings 2.
          Strike rate is <b>{f(h1.strike_rate, 1)}</b> vs <b>{f(n1.strike_rate, 1)}</b> in innings 1 but <b>{f(h2.strike_rate, 1)}</b> vs <b>{f(n2.strike_rate, 1)}</b> in innings 2, so the score is best read as how costly
          and wicket-prone a ball is, not as a pure scoring brake. Within the same phase the expected pattern holds in most segments.
        </p>
      </section>

      <ShapSection />

      <section className="sec" id="trust">
        <h2>How far to trust it</h2>
        <p className="note">
          Rated separately on 2022-23 and on 2024 onwards, the top 10 overlap in only <b>{S.overlap_bat}</b> of 10 batters and <b>{S.overlap_bowl}</b> of 10 bowlers. Pressure performance over a few hundred balls is
          mostly noise, especially for bowlers, so neighbouring ranks are not meaningfully different. Players tagged less robust, or with a high share of non-IPL balls, are lower-confidence picks.
          There is no fielding data, and the weights are judgement calls.
        </p>
        <h3>Stress tests: how often each player stays in the top 10</h3>
        <p className="lede"><b>{S.n_scen}</b> variations of the pressure weights, the high-pressure cutoff, the wicket value, minimum sample, shrinkage and win-probability weight. Orange bars are in the final top 10.</p>
        <div className="two">
          <div><h3>Batters</h3><Robust role="batter" /></div>
          <div><h3>Bowlers</h3><Robust role="bowler" /></div>
        </div>
        <h3 style={{ marginTop: 8 }}>Season by season rating of the final 10</h3>
        <p className="lede">Each season is rated on its own with lower minimums, so cells are noisy. Green is above that season&apos;s average, red below, blank means too few high-pressure balls.</p>
        <div className="two">
          <div><h3>Batters</h3><Heat role="batter" /></div>
          <div><h3>Bowlers</h3><Heat role="bowler" /></div>
        </div>
        <h3 style={{ marginTop: 8 }}>Stability across time</h3>
        <div className="tablewrap">
          <table>
            <thead><tr><th>Role</th><th>Split</th><th className="n">Top-10 overlap (of 10)</th><th className="n">Players rated in both</th><th className="n">Rank correlation</th></tr></thead>
            <tbody>{D.stability.map((r: any) => <tr key={r.role + r.label}><td>{r.role === "bat" ? "Batters" : "Bowlers"}</td><td>{r.label}</td><td className="n">{r.top10_overlap}</td><td className="n">{r.n_common_eligible}</td><td className="n">{f(r.spearman)}</td></tr>)}</tbody>
          </table>
        </div>
      </section>

      <footer className="foot">
        Data: {S.matches} completed IPL and T20I-style matches and {S.balls.toLocaleString("en-US")} balls, {S.date_min} to {S.date_max}. No-result and abandoned matches and super overs are excluded.
        Win-probability model on a time-based hold-out: accuracy {f(S.wpa_acc, 3)}, log-loss {f(S.wpa_logloss, 3)} (constant-rate baseline {f(S.wpa_base_logloss, 3)}).
        Generated by analysis.py from the supplied CSVs.
      </footer>
    </main>
  );
}
