import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
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
const LIGHT = {
  surface: "#ffffff",
  grid: "#ebebeb",
  axis: "#666666",
  text: "#191919",
  series: ["#257de0", "#f47230", "#00b894", "#f2a600", "#ee7fac", "#008a17", "#6a4ce2", "#ec4647"],
};
const DARK = {
  surface: "#191919",
  grid: "#2e2e2e",
  axis: "#9c9c9c",
  text: "#efefef",
  series: ["#338ced", "#e76624", "#00a888", "#d28e05", "#e24d8b", "#0aac23", "#9887ef", "#eb6263"],
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
  rejected: 2,
  ghosted: 3,
  withdrawn: 4,
  accepted: 5,
  unfinished: 6,
  cancelled: 7,
};

const DROP_SERIES = [
  { key: "likely_ghosted", name: "No reply (pending too long)", slot: STATUS_SLOT.pending },
  { key: "rejected", name: "Rejected", slot: STATUS_SLOT.rejected },
  { key: "ghosted", name: "Ghosted (marked)", slot: STATUS_SLOT.ghosted },
  { key: "withdrawn", name: "Withdrew", slot: STATUS_SLOT.withdrawn },
  { key: "unfinished", name: "Unfinished", slot: STATUS_SLOT.unfinished },
  { key: "cancelled", name: "Job cancelled", slot: STATUS_SLOT.cancelled },
] as const;

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
const SHORT_STAGE: Record<string, string> = Object.fromEntries(STAGE_SERIES.map((st) => [st.key, st.short]));

export function DropOffChart({ data }: { data: Analytics["stages"] }) {
  const t = useChartTheme();
  const rows = data.map((d) => ({ ...d, short: SHORT_STAGE[d.stage] ?? d.label }));
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={rows} margin={{ left: -16, right: 8, top: 8, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={t.grid} />
        <XAxis dataKey="short" {...axisProps(t)} interval={0} />
        <YAxis allowDecimals={false} {...axisProps(t)} axisLine={false} />
        <Tooltip {...tooltipProps(t)} />
        <Legend {...legendProps(t)} />
        {DROP_SERIES.map((s) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            name={s.name}
            stackId="drop"
            fill={t.series[s.slot]}
            stroke={t.surface}
            strokeWidth={2}
            barSize={34}
            isAnimationActive={false}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

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
        {statuses.map((s) => (
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
            fill={t.series[s.slot]}
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
              <span style={{ color: t.series[st.slot] }}>●</span> {st.name}: {b[st.key] as number}
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
            fill={t.series[st.slot]}
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
    { key: "unknown", name: "Arrived → result (taken date not recorded)" },
  ].map((st, slot) => ({ ...st, slot }));
  return (
    <ResponsiveContainer width="100%" height={rowHeight(rows.length)}>
      <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
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
            fill={t.series[st.slot]}
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
