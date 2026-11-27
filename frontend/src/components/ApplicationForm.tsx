import { useState, type FormEvent } from "react";
import { useMeta } from "../meta";
import type { ApplicationFields } from "../types";
import { ErrorBox, useAsync } from "./ui";

type Draft = Record<keyof ApplicationFields, string | boolean>;

const TEXT_FIELDS = [
  "company", "role", "applied_date", "level", "location", "work_mode", "source", "job_url",
  "resume_version", "tags", "notes",
] as const;

function toDraft(v: ApplicationFields): Draft {
  const d = {} as Draft;
  for (const [k, val] of Object.entries(v)) {
    d[k as keyof ApplicationFields] = typeof val === "boolean" ? val : val === null ? "" : String(val);
  }
  return d;
}

/** Turn the form's strings back into API values (empty → null, numbers parsed). */
function fromDraft(d: Draft): Partial<ApplicationFields> {
  const out: Record<string, unknown> = { referral: d.referral, cover_letter: d.cover_letter };
  for (const k of TEXT_FIELDS) {
    const s = String(d[k] ?? "").trim();
    out[k] = s === "" ? null : s;
  }
  for (const k of ["salary_min", "salary_max"] as const) {
    const s = String(d[k] ?? "").replace(/[, ]/g, "");
    out[k] = s === "" ? null : Number(s);
  }
  return out as Partial<ApplicationFields>;
}

export function ApplicationForm({
  initial,
  resumeVersions,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial: ApplicationFields;
  resumeVersions: string[];
  submitLabel: string;
  onSubmit: (values: Partial<ApplicationFields>) => Promise<unknown>;
  onCancel?: () => void;
}) {
  const meta = useMeta();
  const [draft, setDraft] = useState<Draft>(() => toDraft(initial));
  const { busy, error, run } = useAsync();

  const text = (k: keyof ApplicationFields) => ({
    value: String(draft[k] ?? ""),
    onChange: (e: { target: { value: string } }) => setDraft({ ...draft, [k]: e.target.value }),
  });
  const check = (k: "referral" | "cover_letter") => ({
    checked: Boolean(draft[k]),
    onChange: (e: { target: { checked: boolean } }) => setDraft({ ...draft, [k]: e.target.checked }),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(() => onSubmit(fromDraft(draft)));
  };

  return (
    <form className="form" onSubmit={submit}>
      <div className="grid-2">
        <label>
          Company *
          <input required autoFocus {...text("company")} />
        </label>
        <label>
          Role *
          <input required {...text("role")} />
        </label>
        <label>
          Applied on *
          <input type="date" required {...text("applied_date")} />
        </label>
        <label>
          Source
          <select {...text("source")}>
            <option value="">–</option>
            {meta.sources.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </label>
        <label>
          Resume version
          <input list="resume-versions" placeholder="e.g. v2-backend" {...text("resume_version")} />
          <datalist id="resume-versions">
            {resumeVersions.map((v) => (
              <option key={v} value={v} />
            ))}
          </datalist>
        </label>
        <label>
          Level
          <select {...text("level")}>
            <option value="">–</option>
            {meta.levels.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </label>
        <label>
          Location
          <input {...text("location")} />
        </label>
        <label>
          Work mode
          <select {...text("work_mode")}>
            <option value="">–</option>
            {meta.work_modes.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </label>
        <label>
          Salary min
          <input inputMode="numeric" {...text("salary_min")} />
        </label>
        <label>
          Salary max
          <input inputMode="numeric" {...text("salary_max")} />
        </label>
      </div>
      <div className="checks">
        <label className="check">
          <input type="checkbox" {...check("referral")} /> Referred by someone
        </label>
        <label className="check">
          <input type="checkbox" {...check("cover_letter")} /> Sent a cover letter
        </label>
      </div>
      <label>
        Job posting URL
        <input type="url" placeholder="https://…" {...text("job_url")} />
      </label>
      <label>
        Tags <span className="hint">comma-separated</span>
        <input placeholder="dream, fintech" {...text("tags")} />
      </label>
      <label>
        Notes
        <textarea rows={3} {...text("notes")} />
      </label>
      <ErrorBox error={error} />
      <div className="actions">
        {onCancel && (
          <button type="button" className="btn" onClick={onCancel}>
            Cancel
          </button>
        )}
        <button className="btn btn-primary" disabled={busy}>
          {busy ? "Saving…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
