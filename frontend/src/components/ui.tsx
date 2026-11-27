import { useEffect, useState, type ReactNode } from "react";

export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="overlay" onMouseDown={onClose}>
      <div className="modal" role="dialog" aria-label={title} onMouseDown={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <h2>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>
        {children}
      </div>
    </div>
  );
}

const OUTCOME_TONE: Record<string, string> = {
  active: "neutral",
  rejected: "critical",
  ghosted: "muted",
  withdrawn: "muted",
  unfinished: "warning",
  cancelled: "muted",
  accepted: "good",
  declined: "neutral",
};

/** Active / Pending for open applications (by days in the current stage), otherwise the outcome. */
export function StatusPill({
  app,
  outcomeLabel,
}: {
  app: { status: string; outcome: string; days_in_stage: number; is_stale: boolean; upcoming_date: string | null };
  outcomeLabel: string;
}) {
  if (app.status === "active" && app.upcoming_date) {
    const when = new Date(`${app.upcoming_date}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
    return (
      <span className="pill pill-neutral" title="A step in this stage is scheduled">
        Scheduled · {when}
      </span>
    );
  }
  if (app.status === "active") {
    return (
      <span className="pill pill-good" title={`Moved ${app.days_in_stage} day(s) ago in this stage`}>
        Active
      </span>
    );
  }
  if (app.status === "pending") {
    return (
      <span
        className="pill pill-warning"
        title={
          app.is_stale
            ? "Silent long enough to count as no-reply: follow up or mark as ghosted"
            : "No movement in this stage for a while: consider a follow-up"
        }
      >
        {app.is_stale ? "⏳ " : ""}Pending · {app.days_in_stage}d
      </span>
    );
  }
  return <span className={`pill pill-${OUTCOME_TONE[app.outcome] ?? "neutral"}`}>{outcomeLabel}</span>;
}

/** The current stage as a tag tinted with that stage's chart color (see styles.css). */
export function StageTag({ stage, label }: { stage: string; label: string }) {
  return <span className={`stage-tag stage-${stage}`}>{label}</span>;
}

const SEVERITY_ICON: Record<string, string> = { good: "✓", warning: "!", info: "i" };
const SEVERITY_LABEL: Record<string, string> = { good: "Working", warning: "Needs attention", info: "Note" };

export function StatusBadge({ severity }: { severity: string }) {
  return (
    <span className={`status status-${severity}`}>
      <span className="status-icon" aria-hidden>
        {SEVERITY_ICON[severity]}
      </span>
      {SEVERITY_LABEL[severity]}
    </span>
  );
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <div className="error" role="alert">
      {error}
    </div>
  );
}

export function useAsync() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, run, setError };
}

export function Rating({ value }: { value: number | null }) {
  if (!value) return null;
  return (
    <span className="rating" title={`Felt like ${value}/5`}>
      {"★".repeat(value)}
      <span className="rating-off">{"★".repeat(5 - value)}</span>
    </span>
  );
}
