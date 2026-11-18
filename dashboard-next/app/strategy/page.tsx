import raw from "@/data/strategy.json";

const S: any = raw;
const f = (v: number | null | undefined, d = 2) => (v == null || Number.isNaN(+v) ? "–" : (+v).toFixed(d));
const n0 = (v: number) => Math.round(v).toLocaleString("en-US");

export const metadata = { title: "Auction strategy · Most Reliable Players Under Pressure" };

const AREAS = [
  { key: "Middle-order batting", view: "Lack of consistency and finishing ability during crucial middle and death overs." },
  { key: "Death-over bowling", view: "Difficulty controlling runs during overs 16 to 20, particularly when defending competitive totals." },
  { key: "Spin bowling", view: "The need for greater consistency and balance between middle-over wicket-taking and run control." },
];

function tone(rank: number, n: number) {
  if (rank <= Math.ceil(n * 0.3)) return "good";
  if (rank >= Math.floor(n * 0.7) + 1) return "bad";
  return "mid";
}

function RankStrip({ rank, n }: { rank: number; n: number }) {
  return (
    <span className="strip" aria-label={`Ranked ${rank} of ${n}`}>
      {Array.from({ length: n }, (_, i) => (
        <i key={i} className={i + 1 === rank ? `on ${tone(rank, n)}` : ""} />
      ))}
    </span>
  );
}

function Check({ area }: { area: string }) {
  const rows = S.rr_checks.filter((r: any) => r.area === area);
  const metrics = Array.from(new Set(rows.map((r: any) => r.metric))) as string[];
  return (
    <div className="tablewrap">
      <table className="small">
        <thead>
          <tr><th>Measure</th><th>Season</th><th className="n">RR</th><th className="n">League average</th><th>Rank among 10 teams (best first)</th></tr>
        </thead>
        <tbody>
          {metrics.flatMap((m) =>
            rows.filter((r: any) => r.metric === m).map((r: any) => (
              <tr key={m + r.season}>
                <td>{m}<div className="muted unit">{r.unit}</div></td>
                <td>{r.season}</td>
                <td className="n"><b>{f(r.rr, 2)}</b></td>
                <td className="n">{f(r.league_avg, 2)}</td>
                <td><RankStrip rank={r.rank} n={r.teams} /> <span className="muted small">{r.rank} of {r.teams}</span></td>
              </tr>
            )),
          )}
        </tbody>
      </table>
    </div>
  );
}

function verdict(area: string) {
  const rows = S.rr_checks.filter((r: any) => r.area === area);
  return {
    bad: rows.filter((r: any) => tone(r.rank, r.teams) === "bad").length,
    good: rows.filter((r: any) => tone(r.rank, r.teams) === "good").length,
    total: rows.length,
  };
}

const P: Record<string, any> = Object.fromEntries(S.players.map((p: any) => [p.name, p]));
const raza = P["Sikandar Raza"], chap = P["Mark Chapman"], path = P["Matheesha Pathirana"], mus = P["Mustafizur Rahman"];
const B = S.benchmarks;
const C = S.chapman;

export default function Strategy() {
  const vs = [verdict("Middle-order batting"), verdict("Death-over bowling"), verdict("Spin bowling")];
  return (
    <main className="wrap">
      <header className="top">
        <h1>Auction strategy</h1>
        <p className="muted">The selector&apos;s view for the IPL 2027 auction, from watching the IPL and studying the dataset</p>
        <p className="take">
          Rajasthan Royals have <b>six squad positions</b> to fill, including <b>three overseas slots</b>. The recommendation is to prioritise three areas, middle-order batting, spin and death-over bowling, rather than investing heavily in another top-order batter.
          Panels headed <i>What the data shows</i> check each point against the supplied ball-by-ball data. Everything else is the selector&apos;s own judgement.
        </p>
        <nav className="nav" aria-label="Sections">
          <a href="#weak">Where RR fell short</a><a href="#recs">The recommendations</a><a href="#plan">Priorities and bidding</a><a href="#final">Final recommendation</a>
        </nav>
      </header>

      <section className="sec" id="weak">
        <h2>1. Where the previous season fell short</h2>
        <p className="lede">Three areas affected the team&apos;s ability to deliver match-winning performances consistently. They should be prioritised ahead of another top-order batter.</p>
        <div className="areas">
          {AREAS.map((a, i) => (
            <article className="area" key={a.key}>
              <span className="tag">Weakness {i + 1}</span>
              <h3>{a.key}</h3>
              <p>{a.view}</p>
              <p className="muted small">Data check: {vs[i].bad} of {vs[i].total} measures rank in RR&apos;s bottom three, {vs[i].good} in its top three.</p>
            </article>
          ))}
        </div>
        <h3 className="sub2">What the data shows</h3>
        <p className="lede">RR against the other nine teams in IPL 2026 and IPL 2025. Each strip has ten segments, best on the left; the lit one is RR.</p>
        {AREAS.map((a) => (
          <div key={a.key} className="checkblock">
            <h4>{a.key}</h4>
            <Check area={a.key} />
          </div>
        ))}
        <p className="note">
          Reading it fairly: the middle-order point holds in both seasons, since RR&apos;s strike rate at positions 4 to 6 was good but the batting average ranked 8th of 10, which fits a lack of consistency.
          Death bowling was clearly the weakest in the league in 2025; in 2026 economy was about average but wicket-taking in overs 16 to 20 ranked 8th.
          Spin is mixed: in 2026 RR&apos;s spinners took wickets faster than any other team, but run control in overs 7 to 15 was below average, and 2025 was weak on both.
        </p>
      </section>

      <section className="sec" id="recs">
        <h2>2. Recommended player targets</h2>

        <article className="rec">
          <header><span className="prio">Recommendation 1</span><h3>Sikandar Raza</h3><span className="role">Spin all-rounder</span></header>
          <p className="primary">The primary recommendation.</p>
          <ul className="plain">
            <li>Provides batting depth in the middle order.</li>
            <li>Offers off-spin bowling options.</li>
            <li>Brings valuable all-round capabilities.</li>
            <li>Provides flexibility in team combinations.</li>
          </ul>
          <p>He could address two requirements at once, middle-order batting and spin bowling, so the auction budget is used efficiently.</p>
          <div className="data">
            <h4>What the data shows</h4>
            <ul className="plain">
              <li><b>Batting:</b> rank {raza.batting.final_rank} in the pressure ranking, rating {f(raza.batting.rating)} from {raza.batting.hp_balls} high-pressure balls, in the top 10 in {f(raza.batting.robust_pct, 0)}% of stress tests.</li>
              <li><b>Spin in overs 7 to 15:</b> economy {f(raza.spin_middle_overs.econ)} over {raza.spin_middle_overs.balls} balls, against {f(B.spin_middle_econ)} for all spinners in the dataset. Strong run control in the middle overs.</li>
            </ul>
            <h4>Watch</h4>
            <ul className="plain warn">
              <li>Bowling under pressure rates below the average rated bowler (rating {f(raza.bowling.rating)} on {raza.bowling.hp_balls} high-pressure balls), so the case for him rests on his batting and his middle-over spin more than on pressure bowling.</li>
              <li>Only {f(raza.batting.ipl_share_pct, 0)}% of his high-pressure batting balls came in the IPL, so most of the evidence is from international cricket.</li>
            </ul>
          </div>
        </article>

        <article className="rec">
          <header><span className="prio">Recommendation 2</span><h3>Mark Chapman</h3><span className="role">Middle-order batter</span></header>
          <p className="primary">Another strong candidate worth considering.</p>
          <p>His New Zealand international T20 performances show his ability to contribute in the middle order.</p>
          <h4 className="mini">T20I statistics as given by the selector</h4>
          <div className="tablewrap">
            <table className="small">
              <thead><tr><th>Source</th><th className="n">Runs</th><th className="n">Average</th><th className="n">Strike rate</th><th className="n">Half-centuries</th><th className="n">Centuries</th></tr></thead>
              <tbody>
                <tr><td>Career T20I (selector)</td><td className="n">{n0(C.stated.runs)}</td><td className="n">{f(C.stated.average)}</td><td className="n">{f(C.stated.strike_rate)}</td><td className="n">{C.stated.fifties}</td><td className="n">{C.stated.hundreds}</td></tr>
                <tr><td>Supplied data, 2022 onward ({C.dataset.innings} innings)</td><td className="n">{n0(C.dataset.runs)}</td><td className="n">{f(C.dataset.average)}</td><td className="n">{f(C.dataset.strike_rate)}</td><td className="n">{C.dataset.fifties}</td><td className="n">{C.dataset.hundreds}</td></tr>
              </tbody>
            </table>
          </div>
          <p className="muted small">The career line is the selector&apos;s figure and is not computed from the dataset, which starts in 2022. The second line is computed from it.</p>
          <h4 className="mini">Why he is recommended</h4>
          <ul className="plain">
            <li>Left-handed batting provides variety to the middle order.</li>
            <li>Capable of accelerating during the middle overs.</li>
            <li>Has experience against international bowling attacks.</li>
            <li>Offers occasional left-arm spin as an additional option.</li>
          </ul>
          <p>He could help address RR&apos;s middle-over scoring slowdown and provide another dependable batting option. His IPL experience and adaptation to Indian conditions should be evaluated before committing to a high bid.</p>
          <div className="data">
            <h4>What the data shows</h4>
            <ul className="plain">
              <li><b>Left-handed:</b> yes, recorded as a left-hand batter in the dataset.</li>
              <li><b>Middle overs 7 to 15:</b> strike rate {f(C.middle_overs.strike_rate, 1)} over {C.middle_overs.balls} balls, against {f(C.middle_overs.t20i_all_batters, 1)} for all T20I batters and {f(C.middle_overs.t20i_positions_4_6, 1)} for batters at positions 4 to 6. Clearly faster than usual when the innings is built.</li>
              <li><b>Pressure ranking:</b> batter rank {chap.batting.final_rank}, rating {f(chap.batting.rating)} from {chap.batting.hp_balls} high-pressure balls, in the top 10 in {f(chap.batting.robust_pct, 0)}% of stress tests.</li>
              <li><b>Since 2022 his numbers are better than his career line:</b> average {f(C.dataset.average)} against {f(C.stated.average)} and strike rate {f(C.dataset.strike_rate, 1)} against {f(C.stated.strike_rate, 1)}.</li>
            </ul>
            <h4>Watch</h4>
            <ul className="plain warn">
              <li>The dataset holds no IPL balls for him ({C.dataset.ipl_balls} faced), so his IPL adaptation cannot be tested here. This matches the caution above.</li>
              <li>His {chap.batting.hp_balls} high-pressure balls are a modest sample, and all are from international matches.</li>
              <li>His bowling in the dataset is only {C.bowling.balls} balls of slow left-arm orthodox, so treat it as a rare option at most.</li>
            </ul>
          </div>
        </article>

        <article className="rec">
          <header><span className="prio">Recommendation 3</span><h3>Matheesha Pathirana</h3><span className="role">Death-over specialist</span></header>
          <p className="primary">A premium target if the team will invest a significant part of its budget.</p>
          <ul className="plain">
            <li>Specialises in death-over bowling.</li>
            <li>Provides an additional wicket-taking option.</li>
            <li>Can strengthen the bowling attack during overs 16 to 20.</li>
          </ul>
          <p>His acquisition should be weighed against the remaining purse and alternative death-over specialists.</p>
          <div className="data">
            <h4>What the data shows</h4>
            <ul className="plain">
              <li><b>Pressure ranking:</b> bowler rank {path.bowling.final_rank}, rating {f(path.bowling.rating)} from {path.bowling.hp_balls} high-pressure balls, {f(path.bowling.ipl_share_pct, 0)}% of them in the IPL, in the top 10 in {f(path.bowling.robust_pct, 0)}% of stress tests.</li>
              <li><b>Overs 16 to 20:</b> economy {f(path.death_overs.econ)} and {f(path.death_overs.wpo)} wickets per over over {path.death_overs.balls} balls, against {f(B.death_econ)} and {f(B.death_wpo)} for all bowlers in the dataset. Better than average on both.</li>
            </ul>
          </div>
        </article>

        <article className="rec">
          <header><span className="prio">Recommendation 4</span><h3>Mustafizur Rahman</h3><span className="role">Death-over alternative</span></header>
          <p className="primary">An alternative or complementary option.</p>
          <p>His variations and change-of-pace deliveries could provide additional options during the death overs.</p>
          <div className="data">
            <h4>What the data shows</h4>
            <ul className="plain">
              <li><b>Pressure ranking:</b> bowler rank {mus.bowling.final_rank}, rating {f(mus.bowling.rating)} from {mus.bowling.hp_balls} high-pressure balls, in the top 10 in {f(mus.bowling.robust_pct, 0)}% of stress tests.</li>
              <li><b>Overs 16 to 20:</b> economy {f(mus.death_overs.econ)} over {mus.death_overs.balls} balls, better than the {f(B.death_econ)} dataset average; wickets per over {f(mus.death_overs.wpo)}, below the {f(B.death_wpo)} average. The value is in run control more than in wickets.</li>
            </ul>
            <h4>Watch</h4>
            <ul className="plain warn">
              <li>Only {f(mus.bowling.ipl_share_pct, 0)}% of his high-pressure balls came in the IPL.</li>
            </ul>
          </div>
        </article>
      </section>

      <section className="sec" id="plan">
        <h2>3. Auction priorities and bidding strategy</h2>
        <div className="tablewrap">
          <table>
            <thead><tr><th className="n">Priority</th><th>Player</th><th>Primary requirement</th></tr></thead>
            <tbody>
              <tr><td className="n">1</td><td>Sikandar Raza</td><td>Middle-order batting + spin</td></tr>
              <tr><td className="n">2</td><td>Mark Chapman</td><td>Middle-order batting</td></tr>
              <tr><td className="n">3</td><td>Matheesha Pathirana</td><td>Premium death-over bowling</td></tr>
              <tr><td className="n">4</td><td>Mustafizur Rahman</td><td>Alternative death-over bowling</td></tr>
            </tbody>
          </table>
        </div>
        <h3 className="sub2">Bidding for the death-over options</h3>
        <div className="flow">
          <div className="fnode">Is Matheesha Pathirana acquired?</div>
          <div className="fbranches">
            <div className="fbranch yes">
              <span className="fl">Yes</span>
              <p>Target <b>Mustafizur Rahman</b> at a reasonable price, provided the budget permits.</p>
            </div>
            <div className="fbranch no">
              <span className="fl">No</span>
              <p>Make <b>Mustafizur Rahman</b> a higher-priority target and put a larger share of the available budget into securing him.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="sec" id="final">
        <h2>4. Final recommendation</h2>
        <p>With six squad positions, including three overseas slots, RR should focus on acquiring versatile players who can improve several departments at once. The recommended approach:</p>
        <ol className="plain steps-list">
          <li>Strengthen the middle order with Mark Chapman.</li>
          <li>Consider Sikandar Raza for his combined batting and spin capabilities.</li>
          <li>Prioritise a dependable death-over specialist.</li>
          <li>Avoid overspending on multiple players with overlapping roles.</li>
          <li>Keep enough auction budget for Indian bowling depth and backup options.</li>
        </ol>
        <p className="pull">
          The ultimate objective is a balanced squad with dependable middle-order contributions, effective spin options and reliable death-over bowling.
        </p>
        <p className="muted">Addressing these weaknesses should give Rajasthan Royals a more balanced squad and improve their ability to perform consistently in high-pressure matches.</p>
      </section>
    </main>
  );
}
