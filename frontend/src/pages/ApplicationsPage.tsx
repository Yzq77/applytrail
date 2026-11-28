import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { ApplicationDrawer } from "../components/ApplicationDrawer";
import { ApplicationForm } from "../components/ApplicationForm";
import { QuickAdd } from "../components/QuickAdd";
import { ErrorBox, Modal, StageTag, StatusPill } from "../components/ui";
import { fmtDate, todayISO, useLabel, useMeta, type Thresholds } from "../meta";
import type { Application, ApplicationFields } from "../types";

const EMPTY = (): ApplicationFields => ({
  company: "",
  role: "",
  applied_date: todayISO(),
  level: null,
  location: null,
  work_mode: null,
  source: null,
  referral: false,
  job_url: null,
  salary_min: null,
  salary_max: null,
  resume_version: null,
  cover_letter: false,
  outcome: "active",
  outcome_date: null,
  rejection_reasons: [],
  missing_required_skills: [],
  missing_preferred_skills: [],
  reflection: null,
  notes: null,
  tags: null,
});

// Filter values: "" (all), "open:active", "open:pending", or an outcome.
const OPEN_PREFIX = "open:";

export function ApplicationsPage({ thresholds }: { thresholds: Thresholds }) {
  const { ghostDays, pendingDays } = thresholds;
  const meta = useMeta();
  const label = useLabel();
  const [apps, setApps] = useState<Application[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [outcome, setOutcome] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);

  const reload = useCallback(async () => {
    try {
      const open = outcome.startsWith(OPEN_PREFIX);
      const rows = await api.list({
        q,
        outcome: open ? "active" : outcome,
        ghost_days: ghostDays,
        pending_days: pendingDays,
      });
      setApps(open ? rows.filter((a) => a.status === outcome.slice(OPEN_PREFIX.length)) : rows);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoaded(true);
    }
  }, [q, outcome, ghostDays, pendingDays]);

  useEffect(() => {
    const t = setTimeout(reload, 150);
    return () => clearTimeout(t);
  }, [reload]);

  const resumeVersions = useMemo(
    () => [...new Set(apps.map((a) => a.resume_version).filter((v): v is string => !!v))].sort(),
    [apps],
  );
  const selected = apps.find((a) => a.id === selectedId) ?? null;
  const pendingCount = apps.filter((a) => a.status === "pending").length;

  return (
    <div>
      <QuickAdd
        resumeVersions={resumeVersions}
        onAdded={async (ids) => {
          await reload();
          if (ids.length === 1) setSelectedId(ids[0]);
        }}
      />
      <div className="toolbar">
        <input
          className="search"
          type="search"
          placeholder="Search company, role, tag, location…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select value={outcome} onChange={(e) => setOutcome(e.target.value)} aria-label="Filter by outcome">
          <option value="">All applications</option>
          <option value="open:active">Open: active (moved in last {pendingDays}d)</option>
          <option value="open:pending">Open: pending ({pendingDays}+ days, no movement)</option>
          {meta.outcomes.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <span className="spacer" />
        {pendingCount > 0 && outcome !== "open:pending" && (
          <button className="link-btn small" onClick={() => setOutcome("open:pending")}>
            {pendingCount} pending {pendingDays}+ days, show them
          </button>
        )}
        <button className="btn btn-primary" onClick={() => setCreating(true)}>
          + New application
        </button>
      </div>

      <ErrorBox error={error} />

      {loaded && apps.length === 0 && !q && !outcome ? (
        <div className="empty">
          <h2>Track your first application</h2>
          <p className="muted">
            Paste a line like <code>https://…/jobs/123, Acme, Data Analyst, 11/26</code> into the quick-add bar
            above, or use the full form.
          </p>
          <p className="muted">
            Log each application and every stage it reaches. The Analytics tab then shows where in the
            process you get filtered out, and which changes (referrals, resume versions, sources) help.
          </p>
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            + New application
          </button>
        </div>
      ) : (
        <div className="card table-wrap">
          <table className="table clickable">
            <thead>
              <tr>
                <th>Company</th>
                <th>Role</th>
                <th>Applied</th>
                <th>Furthest stage</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {apps.map((a) => (
                <tr
                  key={a.id}
                  className={a.id === selectedId ? "selected" : ""}
                  onClick={() => setSelectedId(a.id)}
                  tabIndex={0}
                  onKeyDown={(e) => e.key === "Enter" && setSelectedId(a.id)}
                >
                  <td>
                    <strong>{a.company}</strong>
                    {a.referral && <span className="tag" title="Referral">ref</span>}
                  </td>
                  <td>{a.role}</td>
                  <td className="nowrap">{fmtDate(a.applied_date)}</td>
                  <td className="nowrap">
                    <StageTag stage={a.current_stage} label={label("stages", a.current_stage)} />
                  </td>
                  <td className="nowrap">
                    <StatusPill app={a} outcomeLabel={label("outcomes", a.outcome)} />
                  </td>
                </tr>
              ))}
              {apps.length === 0 && (
                <tr>
                  <td colSpan={5} className="muted center">
                    {loaded ? "No applications match." : "Loading…"}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <ApplicationDrawer
          app={selected}
          resumeVersions={resumeVersions}
          onChanged={reload}
          onClose={() => setSelectedId(null)}
        />
      )}

      {creating && (
        <Modal title="New application" onClose={() => setCreating(false)}>
          <ApplicationForm
            initial={EMPTY()}
            resumeVersions={resumeVersions}
            submitLabel="Add application"
            onCancel={() => setCreating(false)}
            onSubmit={async (v) => {
              const created = await api.create({ ...EMPTY(), ...v } as ApplicationFields);
              setCreating(false);
              await reload();
              setSelectedId(created.id);
            }}
          />
        </Modal>
      )}
    </div>
  );
}
