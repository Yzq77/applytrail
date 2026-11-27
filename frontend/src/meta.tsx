import { createContext, useContext } from "react";
import type { Meta, Option } from "./types";

export const MetaContext = createContext<Meta | null>(null);

export function useMeta(): Meta {
  const meta = useContext(MetaContext);
  if (!meta) throw new Error("Meta not loaded");
  return meta;
}

/** User-adjustable day thresholds, remembered in localStorage. */
export type Thresholds = { ghostDays: number; pendingDays: number };

type OptionKey = "stages" | "outcomes" | "sources" | "levels" | "work_modes";

export function useLabel() {
  const meta = useMeta();
  return (key: OptionKey, value: string | null | undefined): string => {
    if (!value) return "";
    return (meta[key] as Option[]).find((o) => o.value === value)?.label ?? value;
  };
}

export const todayISO = () => {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};

export const pct = (x: number | null | undefined, digits = 0) =>
  x === null || x === undefined ? "–" : `${(x * 100).toFixed(digits)}%`;

export const fmtDate = (iso: string | null) =>
  iso
    ? new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "no date";
