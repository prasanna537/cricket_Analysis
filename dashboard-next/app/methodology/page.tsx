import raw from "@/data/dash.json";

const D: any = raw;
const S = D.summary[0];
const f = (v: number | null | undefined, d = 2) => (v == null || Number.isNaN(+v) ? "–" : (+v).toFixed(d));
const val = (inn: string, seg: string) => D.validation.find((r: any) => r.group === "all balls" && r.innings === inn && r.segment === seg);
const h1 = val("1", "High pressure"), n1 = val("1", "Normal"), h2 = val("2", "High pressure"), n2 = val("2", "Normal");
const W: Record<string, number> = Object.fromEntries(D.weights.map((w: any) => [w.component, w.weight]));
const tsb = D.wpa_importance.slice().sort((a: any, b: any) => b.mean_abs_shap_pp - a.mean_abs_shap_pp);

export const metadata = { title: "Methodology · Most Reliable Players Under Pressure" };

export default function Methodology() {
  return (
    <main className="wrap">
      <header className="top">
        <h1>Methodology</h1>
        <p className="take">
          How the rankings were built, step by step. Everything comes from the supplied ball-by-ball data: <b>{S.matches}</b> completed matches and <b>{S.balls.toLocaleString("en-US")}</b> balls,{" "}
          {S.date_min} to {S.date_max}. The same code run from the raw files reproduces every number on this page.
        </p>
        <nav className="nav" aria-label="Steps">
          <a href="#q">The question</a><a href="#s1">1 Clean</a><a href="#s2">2 Pressure</a><a href="#s3">3 Performance</a><a href="#s4">4 Extra signals</a>
          <a href="#s5">5 Rating</a><a href="#s6">6 Final ranking</a><a href="#s7">7 SHAP</a><a href="#s8">8 Trust</a>
        </nav>
      </header>

      <section className="sec" id="q">
        <h2>The question</h2>
        <p className="lede">Which batters and bowlers do best in high-pressure moments compared with their own usual level? Reputation plays no part. The method has to be transparent and reproducible, so every weight and threshold sits in one configuration block.</p>
      </section>

      <section className="sec" id="s1">
        <h2>1. Clean the data</h2>
        <div className="two">
          <ul className="plain">
            <li>Ball-by-ball, match, competition and squad files are joined on match and competition IDs. Players are identified by ID, never by name.</li>
            <li><b>{S.no_result}</b> no-result or abandoned matches are dropped, and so are all super overs.</li>
            <li>Total runs per ball = bat runs + extras. Wides and no-balls are not legal balls; wides are not faced by the batter.</li>
          </ul>
          <ul className="plain">
            <li>Rain-revised games (<b>{S.rain_revised}</b> matches) use the revised ball count and revised target for balls left, the required rate and lateness.</li>
            <li>Before each ball we record score, wickets lost, balls bowled, balls left, phase (powerplay, middle, death), and in a chase the target, runs needed and required rate.</li>
          </ul>
        </div>
      </section>

      <section className="sec" id="s2">
        <h2>2. Score the pressure on every ball</h2>
        <p className="lede">Seven signals, each scaled 0 to 1, are weighted into a pressure score. Chases and first innings use different mixes.</p>
        <div className="tablewrap">
          <table>
            <thead><tr><th>Innings</th><th>Signal</th><th className="n">Weight</th><th>Why it signals pressure</th></tr></thead>
            <tbody>{D.signals.map((r: any) => <tr key={r.innings + r.signal}><td>{r.innings}</td><td>{r.signal}</td><td className="n">{f(r.weight)}</td><td>{r.why}</td></tr>)}</tbody>
          </table>
        </div>
        <p>High pressure = the top <b>{f(S.hp_quantile_pct, 0)}%</b> of balls in each innings by this score (score above <b>{f(S.hp_thr_inn1)}</b> in innings 1 and <b>{f(S.hp_thr_inn2)}</b> in innings 2).</p>
        <h3>Does the score find hard moments?</h3>
        <p className="note">
          Wickets per 100 balls are higher under pressure in both innings: <b>{f(h1.wickets_per_100, 1)}</b> vs <b>{f(n1.wickets_per_100, 1)}</b> in innings 1 and <b>{f(h2.wickets_per_100, 1)}</b> vs <b>{f(n2.wickets_per_100, 1)}</b> in innings 2.
          Strike rate and dot balls do not move one way in every innings (strike rate <b>{f(h1.strike_rate, 1)}</b> vs <b>{f(n1.strike_rate, 1)}</b> in innings 1 but <b>{f(h2.strike_rate, 1)}</b> vs <b>{f(n2.strike_rate, 1)}</b> in innings 2),
          because high-pressure balls are mostly death overs and chasing batters accelerate. Within the same innings and phase the expected pattern holds in most segments. The score is best read as how costly and wicket-prone a ball is.
        </p>
      </section>

      <section className="sec" id="s3">
        <h2>3. Measure performance against context</h2>
        <ul className="plain">
          <li><b>Expected runs</b> come from the average of similar situations: same competition, innings, phase and wickets lost. Small series are blended with the format-wide average so they do not give noisy baselines.</li>
          <li><b>Batter value per ball</b> = runs above expected, minus <b>{f(S.wk, 0)}</b> runs if dismissed.</li>
          <li><b>Bowler value per ball</b> = runs saved against expected, plus <b>{f(S.wk, 0)}</b> for each wicket credited to the bowler.</li>
          <li>Every player gets a value on high-pressure balls and on normal balls. The normal-ball value is their own baseline, so the method rewards rising to the moment, not just being good.</li>
        </ul>
      </section>

      <section className="sec" id="s4">
        <h2>4. Add three more signals</h2>
        <div className="steps">
          <div className="step"><span className="tag">Chases only</span><h3>Win probability added</h3>
            <p>A gradient-boosted model predicts whether the batting side wins from runs needed, balls left, wickets lost and required rate. On a time-based hold-out it reaches accuracy <b>{f(S.wpa_acc, 3)}</b> and log-loss <b>{f(S.wpa_logloss, 3)}</b>, against <b>{f(S.wpa_base_logloss, 3)}</b> for a constant guess. Each ball&apos;s win-probability change, weighted by leverage, is credited to the batter and charged to the bowler.</p></div>
          <div className="step"><span className="tag">Resilience</span><h3>Setback recovery</h3>
            <p>Batters: value in the 6 balls after a wicket, for batters already at the crease. Bowlers: value on the next ball after conceding a four or six. Both are compared with the league in the same situation.</p></div>
          <div className="step"><span className="tag">Reliability</span><h3>Consistency</h3>
            <p>The share of matches (with at least 3 high-pressure balls) in which the player&apos;s pressure value was positive. It separates steady performers from one big innings.</p></div>
        </div>
      </section>

      <section className="sec" id="s5">
        <h2>5. Build the rating</h2>
        <p className="lede">Small samples are pulled toward the league mean with a pseudo-count of <b>{f(S.shrink_k, 0)}</b> balls, so a hot streak over few balls cannot rank. Players need at least <b>{f(S.min_hp_bat, 0)}</b> high-pressure balls (batters) or <b>{f(S.min_hp_bowl, 0)}</b> (bowlers), from at least <b>{f(S.min_hp_matches, 0)}</b> matches. The five components become z-scores and are combined:</p>
        <div className="formula">
          rating = <b>{f(W["Shrunk pressure value"])}</b> × pressure value + <b>{f(W["Lift over own baseline"])}</b> × lift over own baseline + <b>{f(W["Consistency"])}</b> × consistency + <b>{f(W["Win probability added"])}</b> × win probability added + <b>{f(W["Setback recovery"])}</b> × setback recovery
        </div>
        <div className="tablewrap">
          <table>
            <thead><tr><th>Component</th><th className="n">Weight</th><th>What it measures</th></tr></thead>
            <tbody>{D.weights.map((r: any) => <tr key={r.component}><td>{r.component}</td><td className="n">{f(r.weight)}</td><td>{r.meaning}</td></tr>)}</tbody>
          </table>
        </div>
      </section>

      <section className="sec" id="s6">
        <h2>6. Final ranking</h2>
        <p className="lede">Players are ranked by rating within batters and within bowlers, and the top 10 of each are shown. Each rank comes with its reasons: the two biggest contributors, the sample size and the robustness tag. See <a href="/#final" className="inl">the final 10</a>.</p>
      </section>

      <section className="sec" id="s7">
        <h2>7. Explain it with SHAP</h2>
        <ul className="plain">
          <li><b>The rating:</b> it is a weighted sum of five z-scores, so its SHAP breakdown is exact. Each player&apos;s panel shows how the rating builds from 0 (the average rated player) to the final number.</li>
          <li><b>The win-probability model:</b> exact Shapley values on <b>{D.shap_meta[0].sample.toLocaleString("en-US")}</b> chase balls. Average effect in win-probability points: {tsb.map((q: any) => `${q.label} ${f(q.mean_abs_shap_pp, 1)}`).join(", ")}.</li>
          <li><b>Key moments:</b> each top-10 player&apos;s three biggest chase swings are broken down by what changed in the match, so a big hit&apos;s credit can be traced to runs needed, the required rate or wickets.</li>
        </ul>
        <p>See <a href="/#explain" className="inl">What drives win probability</a> on the dashboard.</p>
      </section>

      <section className="sec" id="s8">
        <h2>8. How far to trust it</h2>
        <ul className="plain">
          <li><b>Stress tests:</b> <b>{S.n_scen}</b> variations of the pressure weights, the high-pressure cutoff, the wicket value, minimum sample, shrinkage and win-probability weight. <b>{S.robust_bat}</b> of 10 batters and <b>{S.robust_bowl}</b> of 10 bowlers stay in the top 10 in at least 75% of them.</li>
          <li><b>Stability over time:</b> rated separately on 2022-23 and on 2024 onwards, the top 10 overlap in only <b>{S.overlap_bat}</b> of 10 batters and <b>{S.overlap_bowl}</b> of 10 bowlers.</li>
          <li><b>Signal versus noise:</b> an estimated <b>{f(S.true_signal_bat_pct, 0)}%</b> of the spread in batters&apos; pressure value, and <b>{f(S.true_signal_bowl_pct, 0)}%</b> for bowlers, is real skill rather than noise. Treat the order as a shortlist.</li>
          <li><b>Limits:</b> there is no fielding data; weights are judgement calls; and IPL and international matches are only compared against each competition&apos;s own baseline, with no adjustment for opposition strength inside a series.</li>
        </ul>
        <p>Detail: <a href="/#trust" className="inl">stress tests, season ratings and stability</a>.</p>
      </section>
    </main>
  );
}
