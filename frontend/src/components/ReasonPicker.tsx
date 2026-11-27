import { useEffect, useState } from "react";
import { api } from "../api";
import type { Reason } from "../types";
import { ErrorBox } from "./ui";

export type RejectionDraft = {
  reasons: string[];
  required: string; // comma-separated, as typed
  preferred: string;
};

export const REQUIRED_KEY = "missing_required_skill";
export const PREFERRED_KEY = "missing_preferred_skill";

export const splitSkills = (text: string) => {
  const seen = new Set<string>();
  return text
    .split(/[,;，、\n]/)
    .map((s) => s.trim().replace(/\s+/g, " "))
    .filter((s) => s && !seen.has(s.toLowerCase()) && seen.add(s.toLowerCase()));
};

/** Multi-select rejection reasons, a free-text "Other" that becomes a reusable option,
 *  and skill inputs for the two missing-skill reasons. */
export function ReasonPicker({ value, onChange }: { value: RejectionDraft; onChange: (v: RejectionDraft) => void }) {
  const [reasons, setReasons] = useState<Reason[]>([]);
  const [skills, setSkills] = useState<string[]>([]);
  const [otherOpen, setOtherOpen] = useState(false);
  const [otherText, setOtherText] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.reasons().then(setReasons, (e) => setError(e.message));
    api.skills().then((s) => setSkills(s.map((x) => x.skill)), () => undefined);
  }, []);

  const selected = new Set(value.reasons);
  const toggle = (key: string) =>
    onChange({
      ...value,
      reasons: selected.has(key) ? value.reasons.filter((k) => k !== key) : [...value.reasons, key],
    });

  const addOther = async () => {
    const label = otherText.trim();
    if (!label) return;
    try {
      const created = await api.addReason(label);
      setReasons((rs) => (rs.some((r) => r.key === created.key) ? rs : [...rs, created]));
      if (!selected.has(created.key)) onChange({ ...value, reasons: [...value.reasons, created.key] });
      setOtherText("");
      setOtherOpen(false);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const remove = async (r: Reason) => {
    if (!confirm(`Remove "${r.label}" from the list of reasons?`)) return;
    try {
      await api.deleteReason(r.key);
      setReasons((rs) => rs.filter((x) => x.key !== r.key));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <fieldset className="reason-picker">
      <legend>
        Why were you rejected? <span className="hint">select all that apply</span>
      </legend>
      <div className="chips">
        {reasons.map((r) => {
          const on = selected.has(r.key);
          return (
            <span key={r.key} className="chip-wrap">
              <button type="button" className={`chip ${on ? "on" : ""}`} aria-pressed={on} onClick={() => toggle(r.key)}>
                {on && <span aria-hidden>✓ </span>}
                {r.label}
              </button>
              {!r.builtin && !on && r.used === 0 && (
                <button
                  type="button"
                  className="chip-x"
                  title="Remove this reason from the list"
                  aria-label={`Remove ${r.label}`}
                  onClick={() => remove(r)}
                >
                  ×
                </button>
              )}
            </span>
          );
        })}
        {!otherOpen && (
          <button type="button" className="chip chip-other" onClick={() => setOtherOpen(true)}>
            + Other…
          </button>
        )}
      </div>

      {otherOpen && (
        <div className="row gap-s">
          <input
            autoFocus
            placeholder="Type a new reason; it'll be saved to the list"
            value={otherText}
            maxLength={80}
            onChange={(e) => setOtherText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addOther();
              }
              if (e.key === "Escape") {
                e.stopPropagation();
                setOtherOpen(false);
              }
            }}
          />
          <button type="button" className="btn btn-small btn-primary" onClick={addOther} disabled={!otherText.trim()}>
            Add
          </button>
          <button type="button" className="btn btn-small" onClick={() => setOtherOpen(false)}>
            Cancel
          </button>
        </div>
      )}

      {selected.has(REQUIRED_KEY) && (
        <SkillInput
          label="Which required skills were missing?"
          value={value.required}
          suggestions={skills}
          onChange={(required) => onChange({ ...value, required })}
        />
      )}
      {selected.has(PREFERRED_KEY) && (
        <SkillInput
          label="Which preferred skills were missing?"
          value={value.preferred}
          suggestions={skills}
          onChange={(preferred) => onChange({ ...value, preferred })}
        />
      )}
      <ErrorBox error={error} />
    </fieldset>
  );
}

function SkillInput({
  label,
  value,
  suggestions,
  onChange,
}: {
  label: string;
  value: string;
  suggestions: string[];
  onChange: (v: string) => void;
}) {
  const typed = new Set(splitSkills(value).map((s) => s.toLowerCase()));
  const offer = suggestions.filter((s) => !typed.has(s.toLowerCase())).slice(0, 8);
  const append = (skill: string) => {
    const parts = splitSkills(value);
    onChange([...parts, skill].join(", "));
  };
  return (
    <div className="skill-input">
      <label>
        {label} <span className="hint">comma-separated, e.g. Kubernetes, Go, AWS</span>
        <input value={value} onChange={(e) => onChange(e.target.value)} placeholder="Kubernetes, Go" />
      </label>
      {offer.length > 0 && (
        <div className="suggestions">
          <span className="muted small">Used before:</span>
          {offer.map((s) => (
            <button key={s} type="button" className="chip chip-small" onClick={() => append(s)}>
              + {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
