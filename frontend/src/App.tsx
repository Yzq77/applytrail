import { lazy, Suspense, useEffect, useState } from "react";
import { api } from "./api";
import { ErrorBox } from "./components/ui";
import { MetaContext, type Thresholds } from "./meta";
import { ApplicationsPage } from "./pages/ApplicationsPage";
import { DataPage } from "./pages/DataPage";
import type { Meta } from "./types";

// Charts are the heaviest dependency, so they load only when the Analytics tab opens.
const AnalyticsPage = lazy(() => import("./pages/AnalyticsPage").then((m) => ({ default: m.AnalyticsPage })));

const TABS = [
  { id: "applications", label: "Applications" },
  { id: "analytics", label: "Analytics" },
  { id: "data", label: "Data & privacy" },
] as const;
type Tab = (typeof TABS)[number]["id"];

const tabFromHash = (): Tab => {
  const h = window.location.hash.slice(1);
  return (TABS.find((t) => t.id === h)?.id ?? "applications") as Tab;
};

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>(tabFromHash);
  const [thresholds, setThresholdsState] = useState<Thresholds | null>(null);

  useEffect(() => {
    api
      .meta()
      .then((m) => {
        setMeta(m);
        const stored = (key: string, fallback: number) => Number(localStorage.getItem(key)) || fallback;
        setThresholdsState({
          ghostDays: stored("applytrail.ghostDays", m.ghost_days_default),
          pendingDays: stored("applytrail.pendingDays", m.pending_days_default),
        });
      })
      .catch(() => setError("Can't reach the backend. Is it running on 127.0.0.1:8000? Try `make dev`."));
    const onHash = () => setTab(tabFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const setThresholds = (t: Thresholds) => {
    localStorage.setItem("applytrail.ghostDays", String(t.ghostDays));
    localStorage.setItem("applytrail.pendingDays", String(t.pendingDays));
    setThresholdsState(t);
  };

  if (error) return <main className="page"><ErrorBox error={error} /></main>;
  if (!meta || thresholds === null) return <main className="page muted">Loading…</main>;

  return (
    <MetaContext.Provider value={meta}>
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden>↗</span> Application Tracking
          {meta.demo && <span className="pill pill-warning" title="Fictional data from make seed">demo data</span>}
        </div>
        <nav className="tabs">
          {TABS.map((t) => (
            <a key={t.id} href={`#${t.id}`} className={tab === t.id ? "on" : ""}>
              {t.label}
            </a>
          ))}
        </nav>
      </header>
      <main className={tab === "applications" ? "page wide" : "page"}>
        {tab === "applications" && <ApplicationsPage thresholds={thresholds} />}
        {tab === "analytics" && (
          <Suspense fallback={<p className="muted">Loading charts…</p>}>
            <AnalyticsPage thresholds={thresholds} setThresholds={setThresholds} />
          </Suspense>
        )}
        {tab === "data" && <DataPage />}
      </main>
    </MetaContext.Provider>
  );
}
