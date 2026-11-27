import { useEffect, useState } from "react";
import { api } from "../api";
import { fmtDate, todayISO, useLabel, useMeta } from "../meta";
import type { Application, StageEvent } from "../types";
import { ApplicationForm } from "./ApplicationForm";
import { PREFERRED_KEY, REQUIRED_KEY, ReasonPicker, splitSkills, type RejectionDraft } from "./ReasonPicker";
import { ErrorBox, Rating, StageTag, StatusPill, useAsync } from "./ui";

// Outcomes worth a reflection ("what would you do differently?").
const FAILED = new Set(["rejected", "ghosted", "unfinished"]);

export function ApplicationDrawer({
  app,
  resumeVersions,
  onChanged,
  onClose,
}: {
  app: Application;
  resumeVersions: string[];
  onChanged: () => Promise<void>;
  onClose: () => void;
}) {
  const meta = useMeta();
  const label = useLabel();
  const stageIdx = meta.stages.findIndex((s) => s.value === app.current_stage);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <aside className="drawer" aria-label={`${app.company} details`}>
      <header className="drawer-head">
        <div>
          <h2>{app.company}</h2>
          <p className="muted">
            {app.role}
            {app.location ? ` · ${app.location}` : ""}
            {app.job_url && (
              <>
                {" · "}
                <a href={app.job_url} target="_blank" rel="noreferrer noopener">
                  posting ↗
                </a>
              </>
            )}
          </p>
          <div className="row gap-s">
            <StageTag stage={app.current_stage} label={label("stages", app.current_stage)} />
            <StatusPill app={app} outcomeLabel={label("outcomes", app.outcome)} />
            {app.outcome === "active" && (
              <span className="muted small">
                {app.upcoming_date
                  ? `next step scheduled for ${fmtDate(app.upcoming_date)}`
                  : `${app.days_in_stage}d in this stage (since ${fmtDate(app.stage_since)})`}
              </span>
            )}
          </div>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close">
          ×
        </button>
      </header>

      <OutcomeEditor key={`o-${app.id}-${app.updated_at}`} app={app} onChanged={onChanged} />

      <section className="drawer-section">
        <h3>Timeline</h3>
        <ol className="timeline">
          {app.events.map((e) => (
            <EventItem key={e.id} event={e} onChanged={onChanged} />
          ))}
          {app.outcome !== "active" && (
            <li className={`timeline-item timeline-outcome outcome-${app.outcome}`}>
              <strong>{label("outcomes", app.outcome)}</strong>{" "}
              <span className="muted">{fmtDate(app.outcome_date)}</span>
            </li>
          )}
        </ol>
        <AddEvent key={`e-${app.id}-${app.events.length}`} app={app} stageIdx={stageIdx} onChanged={onChanged} />
      </section>

      <section className="drawer-section">
        <div className="row between">
          <h3>Details</h3>
          {!editing && (
            <button className="btn btn-small" onClick={() => setEditing(true)}>
              Edit
            </button>
          )}
        </div>
        {editing ? (
          <ApplicationForm
            initial={app}
            resumeVersions={resumeVersions}
            submitLabel="Save details"
            onCancel={() => setEditing(false)}
            onSubmit={async (v) => {
              await api.update(app.id, v);
              await onChanged();
              setEditing(false);
            }}
          />
        ) : (
          <dl className="details">
            <dt>Applied</dt>
            <dd>{fmtDate(app.applied_date)}</dd>
            <dt>Source</dt>
            <dd>
              {label("sources", app.source) || "–"}
              {app.referral ? " · referral" : ""}
            </dd>
            <dt>Resume</dt>
            <dd>
              {app.resume_version || "–"}
              {app.cover_letter ? " · cover letter" : ""}
            </dd>
            <dt>Level / mode</dt>
            <dd>{[label("levels", app.level), label("work_modes", app.work_mode)].filter(Boolean).join(" · ") || "–"}</dd>
            <dt>Salary</dt>
            <dd>
              {app.salary_min || app.salary_max
                ? [app.salary_min, app.salary_max].filter(Boolean).map((n) => n!.toLocaleString()).join(" – ")
                : "–"}
            </dd>
            <dt>Tags</dt>
            <dd>{app.tags || "–"}</dd>
            {app.notes && (
              <>
                <dt>Notes</dt>
                <dd className="prewrap">{app.notes}</dd>
              </>
            )}
          </dl>
        )}
      </section>

      <DeleteButton app={app} onDeleted={async () => { onClose(); await onChanged(); }} />
    </aside>
  );
}

function OutcomeEditor({ app, onChanged }: { app: Application; onChanged: () => Promise<void> }) {
  const meta = useMeta();
  const [outcome, setOutcome] = useState(app.outcome);
  const initialDraft: RejectionDraft = {
    reasons: app.rejection_reasons,
    required: app.missing_required_skills.join(", "),
    preferred: app.missing_preferred_skills.join(", "),
  };
  const [draft, setDraft] = useState<RejectionDraft>(initialDraft);
  const [reflection, setReflection] = useState(app.reflection ?? "");
  const [outcomeDate, setOutcomeDate] = useState(app.outcome_date ?? todayISO());
  const { busy, error, run } = useAsync();
  const closed = outcome !== "active";
  const dirty =
    outcome !== app.outcome ||
    (closed && outcomeDate !== (app.outcome_date ?? todayISO())) ||
    reflection !== (app.reflection ?? "") ||
    JSON.stringify(draft) !== JSON.stringify(initialDraft);

  const save = () =>
    run(async () => {
      const rejected = outcome === "rejected";
      await api.update(app.id, {
        outcome,
        outcome_date: closed ? outcomeDate || todayISO() : null,
        reflection: reflection.trim() || null,
        // Reasons and missing skills only belong to rejections; clear them otherwise.
        rejection_reasons: rejected ? draft.reasons : [],
        missing_required_skills:
          rejected && draft.reasons.includes(REQUIRED_KEY) ? splitSkills(draft.required) : [],
        missing_preferred_skills:
          rejected && draft.reasons.includes(PREFERRED_KEY) ? splitSkills(draft.preferred) : [],
      });
      await onChanged();
    });

  return (
    <section className="drawer-section">
      <h3>Outcome</h3>
      <div className="segmented" role="radiogroup" aria-label="Outcome">
        {meta.outcomes.map((o) => (
          <button
            key={o.value}
            role="radio"
            aria-checked={outcome === o.value}
            className={outcome === o.value ? "on" : ""}
            onClick={() => setOutcome(o.value)}
          >
            {o.label}
          </button>
        ))}
      </div>
      {closed && (
        <label className="outcome-date">
          {meta.outcomes.find((o) => o.value === outcome)?.label} on
          <input
            type="date"
            required
            value={outcomeDate}
            min={app.applied_date}
            max={todayISO()}
            onChange={(e) => setOutcomeDate(e.target.value)}
          />
        </label>
      )}
      {outcome === "rejected" && <ReasonPicker value={draft} onChange={setDraft} />}
      {(FAILED.has(outcome) || reflection) && (
        <label>
          Reflection <span className="hint">what would you do differently?</span>
          <textarea rows={3} value={reflection} onChange={(e) => setReflection(e.target.value)} />
        </label>
      )}
      <ErrorBox error={error} />
      {dirty && (
        <div className="actions">
          <button className="btn btn-primary" disabled={busy || (closed && !outcomeDate)} onClick={save}>
            Save outcome
          </button>
        </div>
      )}
    </section>
  );
}

function EventItem({ event, onChanged }: { event: StageEvent; onChanged: () => Promise<void> }) {
  const label = useLabel();
  const meta = useMeta();
  const [editing, setEditing] = useState(false);
  const [stage, setStage] = useState(event.stage);
  const [date, setDate] = useState(event.event_date ?? "");
  const [taken, setTaken] = useState(event.taken_date ?? "");
  const [rating, setRating] = useState(event.self_rating ? String(event.self_rating) : "");
  const [notes, setNotes] = useState(event.notes ?? "");
  const { busy, error, run } = useAsync();
  const isApplied = event.stage === "applied";

  if (editing) {
    return (
      <li className="timeline-item editing">
        {isApplied ? (
          <strong>{label("stages", event.stage)}</strong>
        ) : (
          <label>
            Stage
            <select value={stage} onChange={(e) => setStage(e.target.value)}>
              {meta.stages
                .filter((s) => s.value !== "applied")
                .map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
            </select>
          </label>
        )}
        <div className="grid-2">
          <label>
            {isApplied ? "Date" : "Received / invited on"}
            <input type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          {!isApplied && (
            <label>
              {takenLabel(stage)} <span className="hint">future date = scheduled</span>
              <input type="date" value={taken} min={date} onChange={(e) => setTaken(e.target.value)} />
            </label>
          )}
          {!isApplied && (
            <label>
              How did it go?
              <RatingSelect value={rating} onChange={setRating} />
            </label>
          )}
        </div>
        <label>
          Notes
          <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
        <ErrorBox error={error} />
        <div className="actions">
          <button className="btn btn-small" onClick={() => setEditing(false)}>
            Cancel
          </button>
          <button
            className="btn btn-small btn-primary"
            disabled={busy || !date}
            onClick={() =>
              run(async () => {
                await api.updateEvent(event.id, {
                  ...(!isApplied && stage !== event.stage && { stage }),
                  ...(!isApplied && { taken_date: taken || null }),
                  event_date: date || null,
                  self_rating: rating ? Number(rating) : null,
                  notes: notes.trim() || null,
                });
                await onChanged();
                setEditing(false);
              })
            }
          >
            Save
          </button>
        </div>
      </li>
    );
  }

  return (
    <li className="timeline-item">
      <div className="row between">
        <div>
          <StageTag stage={event.stage} label={label("stages", event.stage)} />{" "}
          <span className="muted">{fmtDate(event.event_date)}</span>
          {event.taken_date && <TakenNote stage={event.stage} date={event.taken_date} />}{" "}
          <Rating value={event.self_rating} />
        </div>
        <div className="row gap-s">
          <button className="link-btn" onClick={() => setEditing(true)}>
            edit
          </button>
          {!isApplied && (
            <button
              className="link-btn danger"
              onClick={() =>
                confirm(`Remove the "${label("stages", event.stage)}" event?`) &&
                run(async () => {
                  await api.deleteEvent(event.id);
                  await onChanged();
                })
              }
            >
              remove
            </button>
          )}
        </div>
      </div>
      {event.notes && <p className="prewrap small">{event.notes}</p>}
      <ErrorBox error={error} />
    </li>
  );
}

function RatingSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">–</option>
      <option value="1">1 · went badly</option>
      <option value="2">2</option>
      <option value="3">3 · okay</option>
      <option value="4">4</option>
      <option value="5">5 · nailed it</option>
    </select>
  );
}

function AddEvent({ app, stageIdx, onChanged }: { app: Application; stageIdx: number; onChanged: () => Promise<void> }) {
  const meta = useMeta();
  const stages = meta.stages.filter((s) => s.value !== "applied");
  const next = meta.stages[Math.min(stageIdx + 1, meta.stages.length - 1)].value;
  const [stage, setStage] = useState(next === "applied" ? "screen" : next);
  const [date, setDate] = useState(todayISO());
  const [taken, setTaken] = useState("");
  const [rating, setRating] = useState("");
  const [notes, setNotes] = useState("");
  const { busy, error, run } = useAsync();

  return (
    <div className="add-event">
      <h4>Log a stage</h4>
      <div className="grid-2">
        <label>
          Stage
          <select value={stage} onChange={(e) => setStage(e.target.value)}>
            {stages.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </label>
        <label>
          Received / invited on
          <input type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label>
          {takenLabel(stage)} <span className="hint">optional; future = scheduled</span>
          <input type="date" value={taken} min={date} onChange={(e) => setTaken(e.target.value)} />
        </label>
        <label>
          How did it go?
          <RatingSelect value={rating} onChange={setRating} />
        </label>
      </div>
      <label>
        Notes <span className="hint">questions asked, who you met, what tripped you up</span>
        <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      <ErrorBox error={error} />
      <div className="actions">
        <button
          className="btn btn-primary"
          disabled={busy || !date}
          title={date ? undefined : "Every stage needs a date"}
          onClick={() =>
            run(async () => {
              await api.addEvent(app.id, {
                stage,
                event_date: date || null,
                taken_date: taken || null,
                self_rating: rating ? Number(rating) : null,
                notes: notes.trim() || null,
              });
              await onChanged();
            })
          }
        >
          Add to timeline
        </button>
      </div>
    </div>
  );
}

function DeleteButton({ app, onDeleted }: { app: Application; onDeleted: () => Promise<void> }) {
  const { error, run } = useAsync();
  return (
    <section className="drawer-section">
      <ErrorBox error={error} />
      <button
        className="btn btn-danger"
        onClick={() =>
          confirm(`Delete ${app.company} – ${app.role}? This can't be undone.`) &&
          run(async () => {
            await api.remove(app.id);
            await onDeleted();
          })
        }
      >
        Delete application
      </button>
    </section>
  );
}

const takenLabel = (stage: string) => (stage === "assessment" ? "Taken on" : "Takes place on");

/** "· taken Nov 10" / "· held Nov 17" / "· scheduled Dec 8" next to a timeline entry. */
function TakenNote({ stage, date }: { stage: string; date: string }) {
  if (date > todayISO()) {
    return <span className="pill pill-neutral scheduled">scheduled {fmtDate(date)}</span>;
  }
  return (
    <span className="muted">
      {" "}
      · {stage === "assessment" ? "taken" : "held"} {fmtDate(date)}
    </span>
  );
}
