import { useEffect, useState } from "react";
import { api } from "../api";
import {
  AssessmentTimeline,
  PipelineChart,
  RateBar,
  ReasonsChart,
  SkillsChart,
  TAKEN_RESULTS,
  TimingChart,
  WaitingBars,
} from "../components/charts";
import { ErrorBox } from "../components/ui";
import { fmtDate, pct, type Thresholds } from "../meta";

const days = (n: number | null) => (n === null ? "–" : `${n}d`);
import type { Analytics } from "../types";

export function AnalyticsPage({
  thresholds,
  setThresholds,
}: {
  thresholds: Thresholds;
  setThresholds: (t: Thresholds) => void;
}) {
  const { ghostDays, pendingDays } = thresholds;
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.analytics(ghostDays, pendingDays).then(setData, (e) => setError(String(e.message ?? e)));
  }, [ghostDays, pendingDays]);

  if (error) return <ErrorBox error={error} />;
  if (!data) return <p className="muted">Crunching numbers…</p>;

  const s = data.summary;

  return (
    <div className="analytics">
      <div className="toolbar">
        <label className="inline">
          Pending after
          <input
            type="number"
            min={1}
            max={365}
            value={pendingDays}
            onChange={(e) =>
              setThresholds({ ...thresholds, pendingDays: Math.max(1, Number(e.target.value) || 1) })
            }
            className="num-input"
          />
          days in a stage
        </label>
        <label className="inline">
          Count as “no reply” after
          <input
            type="number"
            min={1}
            max={365}
            value={ghostDays}
            onChange={(e) => setThresholds({ ...thresholds, ghostDays: Math.max(1, Number(e.target.value) || 1) })}
            className="num-input"
          />
          days of silence
        </label>
        <span className="spacer" />
        <span className="muted small">
          Rates use the {s.eligible} of {s.total} applications that have a result. The{" "}
          {s.total - s.eligible} still waiting on a first reply are left out.
        </span>
      </div>

      <section className="kpis">
        <Kpi label="Applications" value={String(s.total)} sub={`${s.active} active · ${s.pending} pending`} />
        <Kpi label="Response rate" value={pct(s.response_rate)} sub={`${s.responses} heard back`} />
        <Kpi label="Interview rate" value={pct(s.interview_rate)} sub="reached a technical round" />
        <Kpi label="Offers" value={String(s.offers)} sub={`${pct(s.offer_rate, 1)} of applications`} />
        <Kpi label="Ghost rate" value={pct(s.ghost_rate)} sub="never heard back" />
        <Kpi
          label="Time to first reply"
          value={s.median_days_to_response === null ? "–" : `${s.median_days_to_response}d`}
          sub="median"
        />
      </section>

      <section className="card">
        <h2>Where your applications are now</h2>
        <p className="muted small">
          Every application, placed at the furthest stage it reached and colored by its current status. Open
          applications are <strong>active</strong> if their stage moved in the last {data.pending_days} days and{" "}
          <strong>pending</strong> after that.
        </p>
        <PipelineChart data={data.pipeline} statuses={data.pipeline_statuses} />
      </section>

      <section className="card">
        <div className="row between wrap">
          <h2>How long you’ve been waiting</h2>
          <span className="small">
            <strong>{s.active}</strong> active · <strong>{s.pending}</strong> pending
            {s.stale > 0 && (
              <span className="muted">
                {" "}
                ({s.stale} of them {data.ghost_days}+ days)
              </span>
            )}
          </span>
        </div>
        <p className="muted small">
          Open applications grouped by how long their current stage has gone without movement (counted from
          when you took a step such as an OA, otherwise from when you received it), colored by the stage they’re
          in. Steps scheduled in the future get their own bar. Hover a bar to see which applications are in it.
        </p>
        {data.waiting.points.length ? (
          <div className="waiting">
            <WaitingBars data={data.waiting} pendingDays={data.pending_days} ghostDays={data.ghost_days} />
            <table className="table compact">
              <thead>
                <tr>
                  <th>Stage</th>
                  <th className="num">Active</th>
                  <th className="num">Pending</th>
                  <th className="num">Median wait</th>
                  <th className="num">Longest</th>
                </tr>
              </thead>
              <tbody>
                {data.waiting.by_stage
                  .filter((r) => r.active + r.pending > 0)
                  .map((r) => (
                    <tr key={r.stage}>
                      <td>{r.label}</td>
                      <td className="num">{r.active}</td>
                      <td className="num">{r.pending}</td>
                      <td className="num">{r.median_days === null ? "–" : `${r.median_days}d`}</td>
                      <td className="num muted">{r.max_days === null ? "–" : `${r.max_days}d`}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-chart">No open applications right now.</p>
        )}
      </section>

      <section className="card">
        <h2>Timing</h2>
        <p className="muted small">
          Median days spent at each stage before moving on, and before a rejection arrived.
        </p>
        <div className="mini-kpis">
          <Kpi
            label="First reply after applying"
            value={days(data.timing.days_to_first_response.median)}
            sub={`median · ${data.timing.days_to_first_response.n} replies`}
          />
          <Kpi
            label="Rejection after applying"
            value={days(data.timing.days_to_rejection.median)}
            sub={`median · ${data.timing.days_to_rejection.n} rejections`}
          />
        </div>
        <TimingChart data={data.timing.stage_durations} />
      </section>

      <section className="card">
        <h2>Online assessments</h2>
        <p className="muted small">
          When each OA arrived after you applied, how long you took to do it, and how long until you heard back.
          “Taken” comes from the date you record on the OA step.
        </p>
        {data.assessments.count ? (
          <>
            <div className="mini-kpis">
              <Kpi
                label="OA arrives after applying"
                value={days(data.assessments.days_to_receive.median)}
                sub={`median · ${data.assessments.days_to_receive.n} OAs`}
              />
              <Kpi
                label="You take it within"
                value={days(data.assessments.days_to_take.median)}
                sub={`median · ${data.assessments.taken} taken, ${data.assessments.not_taken} not yet`}
              />
              <Kpi
                label="Result arrives after"
                value={days(data.assessments.days_to_result.median)}
                sub={`median · ${data.assessments.days_to_result.n} with a result`}
              />
              <Kpi
                label="OA pass rate"
                value={pct(data.assessments.pass_rate)}
                sub={`${data.assessments.passed} of ${data.assessments.decided} decided`}
              />
            </div>
            <AssessmentTimeline data={data.assessments.rows} />
            <div className="table-wrap">
              <table className="table compact">
                <thead>
                  <tr>
                    <th>Company</th>
                    <th>Applied</th>
                    <th>OA received</th>
                    <th>Taken</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {data.assessments.rows.map((r) => (
                    <tr key={r.id}>
                      <td>{r.name.split(" · ")[0]}</td>
                      <td className="nowrap">{fmtDate(r.applied)}</td>
                      <td className="nowrap">
                        {fmtDate(r.received)} <span className="muted small">+{r.days_to_receive}d</span>
                      </td>
                      <td className="nowrap">
                        {r.taken ? (
                          <>
                            {fmtDate(r.taken)} <span className="muted small">+{r.days_to_take}d</span>
                          </>
                        ) : (
                          <span className="muted">{TAKEN_RESULTS.has(r.result) ? "date not recorded" : "not taken"}</span>
                        )}
                      </td>
                      <td className="nowrap">
                        {r.result}
                        {r.result_date && (
                          <span className="muted small">
                            {" "}
                            {fmtDate(r.result_date)} · +{r.days_to_result}d
                          </span>
                        )}
                        {r.days_open !== null && <span className="muted small"> · {r.days_open}d so far</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p className="empty-chart">No online assessments logged yet.</p>
        )}
      </section>

      <div className="grid-cards">
        <section className="card">
          <h2>Why you were rejected</h2>
          <p className="muted small">
            Reasons you logged, colored by the stage the rejection happened at. One rejection can have
            several reasons, so the percentages are “share of {data.rejection_reasons.rejected} rejections
            citing it” and can add up to more than 100%.
            {data.rejection_reasons.unlogged > 0 &&
              ` ${data.rejection_reasons.unlogged} rejection(s) have no reason logged yet.`}
          </p>
          {data.rejection_reasons.rows.length ? (
            <ReasonsChart data={data.rejection_reasons.rows} />
          ) : (
            <p className="empty-chart">Mark an application as Rejected and pick reasons to see this chart.</p>
          )}
        </section>
        <section className="card">
          <h2>Missing skills</h2>
          <p className="muted small">
            Skills you noted under “Missing required/preferred skill”, counted across rejections
            {data.missing_skills.rejected > 0 &&
              ` (${data.missing_skills.rejections_with_skill_gap} of ${data.missing_skills.rejected} rejections list one)`}
            . The top of this list is the best thing to learn next.
          </p>
          {data.missing_skills.rows.length ? (
            <SkillsChart data={data.missing_skills.rows.slice(0, 15)} />
          ) : (
            <p className="empty-chart">
              No missing skills logged yet. Choose a “Missing … skill” reason on a rejection and list the skills.
            </p>
          )}
          {data.missing_skills.rows.length > 15 && (
            <p className="small muted">
              Also: {data.missing_skills.rows.slice(15).map((r) => `${r.skill} (${r.total})`).join(", ")}
            </p>
          )}
        </section>
      </div>

      <section className="card">
        <h2>Pass rate by stage</h2>
        <p className="muted small">
          Of the applications that actually went through a stage and got a decision, how many moved on.
          The pale band is the 95% confidence interval, so wide bands mean too little data to be sure.
        </p>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Stage</th>
                <th className="num">Went through</th>
                <th className="num">Passed</th>
                <th className="num">Failed</th>
                <th className="num" title="No decision yet and not silent long enough to count as no-reply">
                  Still open
                </th>
                <th>Pass rate</th>
                <th>Top logged reasons</th>
              </tr>
            </thead>
            <tbody>
              {data.stages.map((st) => (
                <tr key={st.stage}>
                  <td><strong>{st.label}</strong></td>
                  <td className="num">{st.through}</td>
                  <td className="num">{st.passed}</td>
                  <td className="num" title={`${st.rejected} rejected · ${st.ghosted} ghosted · ${st.likely_ghosted} no reply`}>
                    {st.failed}
                  </td>
                  <td className="num muted">{st.pending}</td>
                  <td><RateBar rate={st.pass_rate} ci={st.pass_ci} /></td>
                  <td className="small">
                    {st.reasons.slice(0, 3).map((r) => (
                      <span key={r.reason} className="tag">
                        {r.label} · {r.count}
                      </span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data.offers.total > 0 && (
          <p className="small">
            Offers: <strong>{data.offers.total}</strong> ({data.offers.accepted} accepted · {data.offers.declined} declined ·{" "}
            {data.offers.pending} pending)
          </p>
        )}
      </section>

    </div>
  );
}

function Kpi({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-sub">{sub}</div>
    </div>
  );
}
