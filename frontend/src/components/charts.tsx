import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { pct } from "../meta";
import type { Analytics } from "../types";

/* Validated reference palette (categorical slots in fixed order), stepped per mode.
   SVG presentation attributes can't read CSS variables, so colors are resolved in JS. */
// Low-saturation version of the reference palette (same hue order and lightness, chroma
// lowered to ~0.115 light / ~0.135 dark): still passes the colour-blind separation checks.
const LIGHT = {
  surface: "#ffffff",
  grid: "#ebe8e2",
  axis: "#6c6860",
  text: "#2b2a27",
  series: ["#4b80c1", "#d98560", "#3eb495", "#e1ad5d", "#e189ab", "#438243", "#6962ad", "#c76d67"],
  // Stage progress: Applied (gray) -> Offer (green), one hue, validated as an ordinal ramp.
  stages: ["#b3b5b3", "#98a598", "#7e967e", "#648664", "#49774b", "#2d6731", "#015814"],
  progress: "#2d6731", // "moved on": deep green, separable from red by lightness
  rejected: "#c76d67",
  // Online-assessment phases: one gray -> green family (validated ordinal steps), so
  // neighbouring segments differ by lightness instead of clashing hues.
  oa: { wait: "#b3b5b3", took: "#7e967e", result: "#49774b", notTaken: "#cdb68c" },
};
const DARK = {
  surface: "#1e1e1c",
  grid: "#35342f",
  axis: "#a29e96",
  text: "#e8e6e1",
  series: ["#4b8dda", "#d57449", "#00a888", "#ce9027", "#cc668b", "#56a356", "#988ae7", "#dc706e"],
  stages: ["#545654", "#5f6c5f", "#698369", "#749b74", "#7eb47f", "#87cc89", "#91e694"],
  progress: "#357339",
  rejected: "#dc706e",
  oa: { wait: "#545654", took: "#698369", result: "#7eb47f", notTaken: "#8c7b58" },
};

export function useChartTheme() {
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  const [dark, setDark] = useState(mq.matches);
  useEffect(() => {
    const on = (e: MediaQueryListEvent) => setDark(e.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [mq]);
  return dark ? DARK : LIGHT;
}

type Theme = typeof LIGHT;

const axisProps = (t: Theme) => ({
  stroke: t.grid,
  tick: { fill: t.axis, fontSize: 12 },
  tickLine: false,
});

const tooltipProps = (t: Theme) => ({
  contentStyle: {
    background: t.surface,
    border: `1px solid ${t.grid}`,
    borderRadius: 8,
    color: t.text,
    fontSize: 13,
    boxShadow: "0 4px 16px rgba(0,0,0,.12)",
  },
  labelStyle: { color: t.text, fontWeight: 600, marginBottom: 4 },
  itemStyle: { color: t.text, padding: 0 },
  cursor: { fill: t.grid, opacity: 0.5 },
});

// Legend text stays in the text ink; only the swatch carries the series color.
const legendProps = (t: Theme) => ({
  wrapperStyle: { fontSize: 12 },
  iconType: "circle" as const,
  iconSize: 8,
  formatter: (value: string) => <span style={{ color: t.axis }}>{value}</span>,
  itemSorter: () => 0, // keep series (stack) order instead of alphabetical
});

/* One color per application status, shared by every chart (color follows the entity).
   Slots follow the palette's fixed, CVD-validated order. */
export const STATUS_SLOT: Record<string, number> = {
  active: 0,
  pending: 1,
  ghosted: 2,
  withdrawn: 3,
  unfinished: 4,
  accepted: 5, // green
  cancelled: 6,
  rejected: 7, // red
};

/* One color per stage, shared by every chart that splits by stage (fixed slot order). */
const STAGE_SERIES = [
  { key: "applied", name: "Applied", short: "Applied" },
  { key: "screen", name: "Recruiter screen", short: "Screen" },
  { key: "webinar", name: "Webinar", short: "Webinar" },
  { key: "assessment", name: "Assessment / OA", short: "OA" },
  { key: "technical", name: "Technical", short: "Technical" },
  { key: "onsite", name: "Onsite", short: "Onsite" },
  { key: "offer", name: "Offer", short: "Offer" },
].map((st, slot) => ({ ...st, slot }));

/** Inline rate bar with a 95% confidence-interval whisker, used inside tables. */
export function RateBar({ rate, ci }: { rate: number | null; ci: [number, number] | null }) {
  if (rate === null) return <span className="muted">–</span>;
  return (
    <span className="ratebar" title={ci ? `95% CI ${pct(ci[0])} – ${pct(ci[1])}` : undefined}>
      <span className="ratebar-track">
        <span className="ratebar-fill" style={{ width: `${rate * 100}%` }} />
        {ci && (
          <span className="ratebar-ci" style={{ left: `${ci[0] * 100}%`, width: `${(ci[1] - ci[0]) * 100}%` }} />
        )}
      </span>
      <span className="ratebar-value">{pct(rate)}</span>
    </span>
  );
}

const rowHeight = (n: number) => Math.max(160, n * 36 + 70);

export function PipelineChart({
  data,
  statuses,
}: {
  data: Analytics["pipeline"];
  statuses: Analytics["pipeline_statuses"];
}) {
  const t = useChartTheme();
  const rows = data.map((d) => ({ ...d, axisLabel: `${d.label} · ${d.total}` }));
  return (
    <ResponsiveContainer width="100%" height={rowHeight(rows.length)}>
      <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
        <CartesianGrid horizontal={false} stroke={t.grid} />
        <XAxis type="number" allowDecimals={false} {...axisProps(t)} />
        <YAxis type="category" dataKey="axisLabel" width={170} {...axisProps(t)} axisLine={false} />
        <Tooltip {...tooltipProps(t)} />
        <Legend {...legendProps(t)} />
        {[...statuses].sort((a, b) => STATUS_SLOT[a.key] - STATUS_SLOT[b.key]).map((s) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            name={s.label}
            stackId="now"
            fill={t.series[STATUS_SLOT[s.key]]}
            stroke={t.surface}
            strokeWidth={2}
            barSize={22}
            isAnimationActive={false}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function ReasonsChart({ data }: { data: Analytics["rejection_reasons"]["rows"] }) {
  const t = useChartTheme();
  const rows = data.map((d) => ({
    axisLabel: `${d.label} · ${d.count} (${pct(d.share)})`,
    ...d.by_stage,
  }));
  // Only draw stages that actually appear, so the legend stays honest.
  const used = STAGE_SERIES.filter((st) => data.some((d) => (d.by_stage[st.key] ?? 0) > 0));
  return (
    <ResponsiveContainer width="100%" height={rowHeight(rows.length)}>
      <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
        <CartesianGrid horizontal={false} stroke={t.grid} />
        <XAxis type="number" allowDecimals={false} {...axisProps(t)} />
        <YAxis type="category" dataKey="axisLabel" width={260} {...axisProps(t)} axisLine={false} interval={0} />
        <Tooltip {...tooltipProps(t)} labelFormatter={(l) => `${l}, rejected at:`} />
        <Legend {...legendProps(t)} />
        {used.map((s) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            name={s.name}
            stackId="reason"
            fill={t.stages[s.slot]}
            stroke={t.surface}
            strokeWidth={2}
            barSize={20}
            isAnimationActive={false}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function SkillsChart({ data }: { data: Analytics["missing_skills"]["rows"] }) {
  const t = useChartTheme();
  const rows = data.map((d) => ({ ...d, axisLabel: `${d.skill} · ${d.total}` }));
  return (
    <ResponsiveContainer width="100%" height={rowHeight(rows.length)}>
      <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
        <CartesianGrid horizontal={false} stroke={t.grid} />
        <XAxis type="number" allowDecimals={false} {...axisProps(t)} />
        <YAxis type="category" dataKey="axisLabel" width={150} {...axisProps(t)} axisLine={false} interval={0} />
        <Tooltip {...tooltipProps(t)} labelFormatter={(l) => `${l}, missing in rejections`} />
        <Legend {...legendProps(t)} />
        <Bar dataKey="required" name="Required skill" stackId="skill" fill={t.series[0]} stroke={t.surface} strokeWidth={2} barSize={18} isAnimationActive={false} />
        <Bar dataKey="preferred" name="Preferred skill" stackId="skill" fill={t.series[1]} stroke={t.surface} strokeWidth={2} barSize={18} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}

type WaitBin = {
  label: string;
  status: string;
  total: number;
  names: string[];
  [stage: string]: number | string | string[];
};

/** Open applications bucketed by how long they've waited in their current stage,
 *  stacked by that stage. Scheduled steps get their own bar. */
export function WaitingBars({
  data,
  pendingDays,
  ghostDays,
}: {
  data: Analytics["waiting"];
  pendingDays: number;
  ghostDays: number;
}) {
  const t = useChartTheme();
  const lastEdge = Math.max(28, Math.ceil((ghostDays + 1) / 7) * 7);
  const edges: number[] = [];
  for (let e = 0; e <= lastEdge; e += 7) edges.push(e);

  const statusOf = (lo: number, hi: number) =>
    lo >= ghostDays ? "no reply" : lo >= pendingDays ? "pending" : hi < pendingDays ? "active" : "active / pending";
  const bins: WaitBin[] = [];
  const empty = () => Object.fromEntries(STAGE_SERIES.map((st) => [st.key, 0]));
  bins.push({ label: "Scheduled", status: "upcoming", total: 0, names: [], ...empty() } as WaitBin);
  edges.forEach((lo, i) => {
    const hi = i < edges.length - 1 ? edges[i + 1] - 1 : Infinity;
    const label = hi === Infinity ? `${lo}+ days` : `${lo}–${hi} days`;
    bins.push({ label, status: statusOf(lo, hi), total: 0, names: [], lo, hi, ...empty() } as unknown as WaitBin);
  });
  for (const p of data.points) {
    const bin = p.upcoming
      ? bins[0]
      : bins.slice(1).find((b) => p.days >= (b.lo as number) && p.days <= (b.hi as number))!;
    (bin[p.stage] as number) += 1;
    bin.total += 1;
    bin.names.push(`${p.name.split(" · ")[0]} (${p.upcoming ? `on ${p.upcoming}` : `${p.days}d`})`);
  }
  const rows = bins.filter((b) => b.label !== "Scheduled" || b.total > 0);
  const used = STAGE_SERIES.filter((st) => data.points.some((p) => p.stage === st.key));

  const Tick = ({ x, y, payload }: { x?: number; y?: number; payload?: { value: string } }) => {
    const bin = rows.find((b) => b.label === payload?.value);
    return (
      <g transform={`translate(${x},${y})`}>
        <text textAnchor="middle" fill={t.axis} fontSize={12}>
          <tspan x={0} dy={14}>{payload?.value}</tspan>
          <tspan x={0} dy={15} fontSize={11} fontWeight={bin?.status === "pending" ? 700 : 400}>
            {bin ? `${bin.status} · ${bin.total}` : ""}
          </tspan>
        </text>
      </g>
    );
  };

  const BinTooltip = ({ active, payload }: { active?: boolean; payload?: { payload: WaitBin }[] }) => {
    if (!active || !payload?.length) return null;
    const b = payload[0].payload;
    return (
      <div style={{ ...tooltipProps(t).contentStyle, padding: "8px 10px", maxWidth: 320 }}>
        <div style={{ fontWeight: 600 }}>
          {b.label}: {b.total} application{b.total === 1 ? "" : "s"} ({b.status})
        </div>
        {used
          .filter((st) => (b[st.key] as number) > 0)
          .map((st) => (
            <div key={st.key} style={{ color: t.axis }}>
              <span style={{ color: t.stages[st.slot] }}>●</span> {st.name}: {b[st.key] as number}
            </div>
          ))}
        <div style={{ color: t.axis, marginTop: 4, fontSize: 12 }}>
          {b.names.slice(0, 8).join(", ")}
          {b.names.length > 8 ? `, +${b.names.length - 8} more` : ""}
        </div>
      </div>
    );
  };

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={rows} margin={{ left: -16, right: 8, top: 8, bottom: 22 }}>
        <CartesianGrid vertical={false} stroke={t.grid} />
        <XAxis dataKey="label" {...axisProps(t)} interval={0} tick={<Tick />} />
        <YAxis allowDecimals={false} {...axisProps(t)} axisLine={false} />
        <Tooltip content={<BinTooltip />} cursor={{ fill: t.grid, opacity: 0.5 }} />
        <Legend {...legendProps(t)} wrapperStyle={{ fontSize: 12, paddingTop: 18 }} />
        {used.map((st) => (
          <Bar
            key={st.key}
            dataKey={st.key}
            name={st.name}
            stackId="wait"
            fill={t.stages[st.slot]}
            stroke={t.surface}
            strokeWidth={2}
            barSize={44}
            isAnimationActive={false}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

const RESULT_LABEL: Record<string, string> = {
  passed: "passed",
  rejected: "rejected",
  ghosted: "ghosted",
  unfinished: "unfinished",
  cancelled: "job cancelled",
  withdrawn: "withdrew",
  waiting: "waiting for result",
  "not taken": "not taken yet",
};

export const TAKEN_RESULTS = new Set(["passed", "rejected", "ghosted"]);

const daysBetween = (a: string, b: string) =>
  Math.max(0, Math.round((Date.parse(`${b}T00:00:00`) - Date.parse(`${a}T00:00:00`)) / 86400000));

/** One bar per OA: waiting for it, your time to take it, then waiting for the result. */
export function AssessmentTimeline({ data }: { data: Analytics["assessments"]["rows"] }) {
  const t = useChartTheme();
  const rows = data.map((r) => {
    // A pass or rejection means it was taken, even if the date wasn't recorded.
    const unknown = !r.taken && TAKEN_RESULTS.has(r.result);
    const untilEnd = r.result_date ? daysBetween(r.received, r.result_date) : (r.days_open ?? 0);
    const notTaken = r.taken || unknown ? 0 : untilEnd;
    return {
      axisLabel: `${r.name.split(" · ")[0]} · ${RESULT_LABEL[r.result] ?? r.result}`,
      wait: r.days_to_receive,
      took: r.taken ? (r.days_to_take ?? 0) : 0,
      result: r.taken ? (r.days_to_result ?? r.days_open ?? 0) : 0,
      notTaken,
      unknown: unknown ? untilEnd : 0,
    };
  });
  const series = [
    { key: "wait", name: "Applied → OA arrived" },
    { key: "took", name: "OA arrived → you took it" },
    { key: "result", name: "Took it → result (or today)" },
    { key: "notTaken", name: "Not taken" },
    { key: "unknown", name: "Striped: arrived → result, taken date not recorded" },
  ] as const;
  return (
    <ResponsiveContainer width="100%" height={rowHeight(rows.length)}>
      <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
        <defs>
          {/* "Taken, date unknown" spans both of your phases, so it's drawn as stripes of the two. */}
          <pattern id="oa-unknown" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="6" height="6" fill={t.oa.took} />
            <rect width="3" height="6" fill={t.oa.result} />
          </pattern>
        </defs>
        <CartesianGrid horizontal={false} stroke={t.grid} />
        <XAxis type="number" allowDecimals={false} {...axisProps(t)} unit="d" />
        <YAxis type="category" dataKey="axisLabel" width={260} {...axisProps(t)} axisLine={false} interval={0} />
        <Tooltip {...tooltipProps(t)} formatter={(v) => `${v} days`} />
        <Legend {...legendProps(t)} />
        {series.map((st) => (
          <Bar
            key={st.key}
            dataKey={st.key}
            name={st.name}
            stackId="oa"
            fill={st.key === "unknown" ? "url(#oa-unknown)" : t.oa[st.key]}
            stroke={t.surface}
            strokeWidth={2}
            barSize={18}
            isAnimationActive={false}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Median days per stage: until moving on, and until a rejection. Bars are labelled directly. */
export function TimingChart({ data }: { data: Analytics["timing"]["stage_durations"] }) {
  const t = useChartTheme();
  const rows = data
    .filter((d) => d.median_days !== null || d.median_days_to_rejection !== null)
    .map((d) => ({
      label: d.label,
      next: d.median_days,
      rejected: d.median_days_to_rejection,
      nextN: d.n,
      rejectedN: d.rejected_n,
    }));
  if (!rows.length) return <p className="empty-chart">Not enough dated stages yet.</p>;
  const label = (v: unknown) => (v === null || v === undefined ? "" : `${v}d`);
  return (
    <ResponsiveContainer width="100%" height={Math.max(180, rows.length * 64 + 60)}>
      <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 40, top: 4, bottom: 4 }} barGap={3}>
        <CartesianGrid horizontal={false} stroke={t.grid} />
        <XAxis type="number" allowDecimals={false} {...axisProps(t)} unit="d" />
        <YAxis type="category" dataKey="label" width={170} {...axisProps(t)} axisLine={false} interval={0} />
        <Tooltip
          {...tooltipProps(t)}
          formatter={(v, name, item) => {
            const r = item.payload as (typeof rows)[number];
            const n = name === "Until the next stage" ? r.nextN : r.rejectedN;
            return [v === null ? "no data" : `${v} days (median of ${n})`, name];
          }}
        />
        <Legend {...legendProps(t)} />
        <Bar dataKey="next" name="Until the next stage" fill={t.progress} radius={[0, 4, 4, 0]} barSize={16} isAnimationActive={false}>
          <LabelList dataKey="next" position="right" fill={t.text} fontSize={12} formatter={label} />
        </Bar>
        <Bar dataKey="rejected" name="Until a rejection" fill={t.rejected} radius={[0, 4, 4, 0]} barSize={16} isAnimationActive={false}>
          <LabelList dataKey="rejected" position="right" fill={t.text} fontSize={12} formatter={label} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
