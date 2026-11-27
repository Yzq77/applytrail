import type { Analytics, Application, ApplicationFields, Meta, QuickItem, Reason, StageEvent } from "./types";

type ImportResult = { imported: number };

function describeError(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "errors" in detail) {
    const d = detail as { message?: string; errors: { row?: number; error: string }[] };
    const lines = d.errors.slice(0, 5).map((e) => (e.row ? `Row ${e.row}: ${e.error}` : e.error));
    return [d.message, ...lines].filter(Boolean).join("\n");
  }
  if (Array.isArray(detail)) {
    return detail
      .map((e: { loc?: string[]; msg?: string }) => `${(e.loc ?? []).slice(1).join(".")}: ${e.msg}`)
      .join("\n");
  }
  return JSON.stringify(detail);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      message = describeError((await res.json()).detail);
    } catch {
      /* non-JSON error body */
    }
    throw new Error(message);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const send = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export type EventInput = Omit<StageEvent, "id" | "application_id">;

export const api = {
  meta: () => request<Meta>("/api/meta"),
  list: (params: { q?: string; outcome?: string; ghost_days: number; pending_days: number }) => {
    const qs = new URLSearchParams({
      ghost_days: String(params.ghost_days),
      pending_days: String(params.pending_days),
    });
    if (params.q) qs.set("q", params.q);
    if (params.outcome) qs.set("outcome", params.outcome);
    return request<Application[]>(`/api/applications?${qs}`);
  },
  create: (body: ApplicationFields) => request<Application>("/api/applications", send("POST", body)),
  update: (id: number, body: Partial<ApplicationFields>) =>
    request<Application>(`/api/applications/${id}`, send("PATCH", body)),
  remove: (id: number) => request<void>(`/api/applications/${id}`, { method: "DELETE" }),
  addEvent: (appId: number, body: EventInput) =>
    request<StageEvent>(`/api/applications/${appId}/events`, send("POST", body)),
  updateEvent: (id: number, body: Partial<EventInput>) =>
    request<StageEvent>(`/api/events/${id}`, send("PATCH", body)),
  deleteEvent: (id: number) => request<void>(`/api/events/${id}`, { method: "DELETE" }),
  quickAdd: (text: string, dryRun: boolean, resumeVersion?: string) =>
    request<{ items: QuickItem[]; created: number[] }>(
      "/api/applications/quick",
      send("POST", { text, dry_run: dryRun, resume_version: resumeVersion || null }),
    ),
  reasons: () => request<Reason[]>("/api/reasons"),
  addReason: (label: string) => request<Reason>("/api/reasons", send("POST", { label })),
  deleteReason: (key: string) =>
    request<void>(`/api/reasons/${encodeURIComponent(key)}`, { method: "DELETE" }),
  skills: () => request<{ skill: string; count: number }[]>("/api/skills"),
  analytics: (ghostDays: number, pendingDays: number) =>
    request<Analytics>(`/api/analytics?ghost_days=${ghostDays}&pending_days=${pendingDays}`),
  importFile: (kind: "json" | "csv", text: string, mode: "append" | "replace") =>
    request<ImportResult>(`/api/import/${kind}?mode=${mode}`, {
      method: "POST",
      headers: { "Content-Type": kind === "json" ? "application/json" : "text/csv" },
      body: text,
    }),
};
