import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { fmtDate, useLabel } from "../meta";
import type { QuickItem } from "../types";
import { ErrorBox, useAsync } from "./ui";

const RESUME_KEY = "applytrail.quickResume";

const hostOf = (url: string) => {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "link";
  }
};

/** One-line logging: "link, company, job title, date", one application per line.
 *  The server parses it; we show its parse as a live preview before saving. */
export function QuickAdd({ resumeVersions, onAdded }: { resumeVersions: string[]; onAdded: (ids: number[]) => Promise<void> }) {
  const label = useLabel();
  const [text, setText] = useState("");
  const [items, setItems] = useState<QuickItem[]>([]);
  const [resume, setResume] = useState(() => localStorage.getItem(RESUME_KEY) ?? "");
  const [message, setMessage] = useState<string | null>(null);
  const { busy, error, run, setError } = useAsync();
  const latest = useRef(0);

  useEffect(() => {
    if (!text.trim()) {
      setItems([]);
      return;
    }
    const ticket = ++latest.current;
    const t = setTimeout(() => {
      api.quickAdd(text, true).then(
        (r) => ticket === latest.current && (setItems(r.items), setError(null)),
        (e) => ticket === latest.current && setError(e.message),
      );
    }, 200);
    return () => clearTimeout(t);
  }, [text, setError]);

  const valid = items.length > 0 && items.every((i) => !i.error);
  const submit = () =>
    valid &&
    run(async () => {
      localStorage.setItem(RESUME_KEY, resume);
      const r = await api.quickAdd(text, false, resume);
      latest.current++;
      setText("");
      setItems([]);
      setMessage(`Added ${r.created.length} application${r.created.length === 1 ? "" : "s"}.`);
      setTimeout(() => setMessage(null), 4000);
      await onAdded(r.created);
    });

  const lines = Math.min(6, Math.max(1, text.split("\n").length));

  return (
    <section className="card quick-add">
      <div className="quick-row">
        <textarea
          aria-label="Quick add applications"
          rows={lines}
          value={text}
          placeholder="Quick add: link, company, job title, date (optional) · Enter to save"
          title="e.g. https://…/jobs/123, Acme, Data Analyst, 11/26. The date defaults to today. Shift+Enter adds another line."
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <input
          className="quick-resume"
          list="quick-resume-versions"
          placeholder="Resume version"
          title="Resume version used for these applications (remembered)"
          value={resume}
          onChange={(e) => setResume(e.target.value)}
        />
        <datalist id="quick-resume-versions">
          {resumeVersions.map((v) => (
            <option key={v} value={v} />
          ))}
        </datalist>
        <button className="btn btn-primary" disabled={!valid || busy} onClick={submit}>
          {items.length > 1 ? `Add ${items.length}` : "Add"}
        </button>
      </div>

      {items.length > 0 && (
        <ul className="quick-preview">
          {items.map((i) => (
            <li key={i.line} className={i.error ? "bad" : ""}>
              {i.error ? (
                <>
                  <span className="status-dot bad" aria-hidden>!</span>
                  <span>
                    {items.length > 1 && `Line ${i.line}: `}
                    {i.error}
                  </span>
                </>
              ) : (
                <>
                  <span className="status-dot ok" aria-hidden>✓</span>
                  <strong>{i.role}</strong>
                  <span className="muted">at</span>
                  <strong>{i.company}</strong>
                  <span className="muted">
                    · {fmtDate(i.applied_date)}
                    {i.date_defaulted && " (today, no date given)"}
                  </span>
                  {i.source && <span className="tag">{label("sources", i.source)}</span>}
                  {i.job_url && (
                    <a className="small" href={i.job_url} target="_blank" rel="noreferrer noopener">
                      {hostOf(i.job_url)} ↗
                    </a>
                  )}
                  {i.warning && <span className="warn small">⚠ {i.warning}</span>}
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      {message && <p className="success small">{message}</p>}
      <ErrorBox error={error} />
    </section>
  );
}
