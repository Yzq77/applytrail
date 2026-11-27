export type Option = { value: string; label: string };

export interface Meta {
  stages: Option[];
  outcomes: Option[];
  sources: Option[];
  levels: Option[];
  work_modes: Option[];
  demo: boolean;
  db_file: string;
  ghost_days_default: number;
  pending_days_default: number;
}

export interface StageEvent {
  id: number;
  application_id: number;
  stage: string;
  event_date: string | null;
  taken_date: string | null; // when you took it / it takes place (future = scheduled)
  self_rating: number | null;
  notes: string | null;
}

export interface ApplicationFields {
  company: string;
  role: string;
  applied_date: string;
  level: string | null;
  location: string | null;
  work_mode: string | null;
  source: string | null;
  referral: boolean;
  job_url: string | null;
  salary_min: number | null;
  salary_max: number | null;
  resume_version: string | null;
  cover_letter: boolean;
  outcome: string;
  outcome_date: string | null;
  rejection_reasons: string[];
  missing_required_skills: string[];
  missing_preferred_skills: string[];
  reflection: string | null;
  notes: string | null;
  tags: string | null;
}

export interface Application extends ApplicationFields {
  id: number;
  created_at: string;
  updated_at: string;
  current_stage: string;
  last_activity: string;
  days_since_activity: number;
  is_stale: boolean;
  stage_since: string;
  days_in_stage: number;
  upcoming_date: string | null;
  status: string; // "active" | "pending" while open, otherwise the outcome
  events: StageEvent[];
}

export interface Summary {
  total: number;
  open: number;
  active: number;
  pending: number;
  stale: number;
  eligible: number;
  responses: number;
  response_rate: number | null;
  interview_rate: number | null;
  offer_rate: number | null;
  offers: number;
  ghost_rate: number | null;
  median_days_to_response: number | null;
}

export interface FunnelRow {
  stage: string;
  label: string;
  reached: number; // actually went through this stage
  reached_rate: number | null;
  skipped: number; // went further without this stage
  reached_or_later: number;
}

export interface StageRow {
  stage: string;
  label: string;
  through: number;
  passed: number;
  failed: number;
  rejected: number;
  ghosted: number;
  likely_ghosted: number;
  withdrawn: number;
  unfinished: number;
  cancelled: number;
  pending: number;
  pass_rate: number | null;
  pass_ci: [number, number] | null;
  reasons: { reason: string; label: string; count: number }[];
  unlogged: number;
}

export interface Reason {
  key: string;
  label: string;
  builtin: boolean;
  skill_kind: "required" | "preferred" | null;
  used: number;
}

export interface QuickItem {
  line: number;
  raw: string;
  company: string | null;
  role: string | null;
  job_url: string | null;
  applied_date: string | null;
  date_defaulted: boolean;
  source: string | null;
  error: string | null;
  warning: string | null;
}

export interface PipelineRow {
  stage: string;
  label: string;
  total: number;
  [status: string]: string | number;
}

export interface BreakdownRow {
  value: string;
  n: number;
  responses: number;
  interviews: number;
  offers: number;
  response_rate: number | null;
  interview_rate: number | null;
  offer_rate: number | null;
  response_ci: [number, number] | null;
  low_sample: boolean;
}

export interface Insight {
  severity: "good" | "warning" | "info";
  title: string;
  detail: string;
}

export interface Analytics {
  generated_on: string;
  ghost_days: number;
  pending_days: number;
  summary: Summary;
  waiting: {
    pending_days: number;
    points: {
      id: number;
      name: string;
      stage: string;
      stage_index: number;
      label: string;
      since: string;
      upcoming: string | null;
      days: number;
      status: "active" | "pending";
    }[];
    by_stage: {
      stage: string;
      label: string;
      active: number;
      pending: number;
      median_days: number | null;
      max_days: number | null;
    }[];
  };
  pipeline: PipelineRow[];
  pipeline_statuses: { key: string; label: string }[];
  funnel: FunnelRow[];
  stages: StageRow[];
  rejection_reasons: {
    rejected: number;
    unlogged: number;
    rows: { reason: string; label: string; count: number; share: number | null; by_stage: Record<string, number> }[];
  };
  missing_skills: {
    rejections_with_skill_gap: number;
    rejected: number;
    rows: { skill: string; required: number; preferred: number; total: number }[];
  };
  offers: { total: number; accepted: number; declined: number; pending: number };
  assessments: {
    count: number;
    taken: number;
    not_taken: number;
    days_to_receive: { median: number | null; n: number };
    days_to_take: { median: number | null; n: number };
    days_to_result: { median: number | null; n: number };
    pass_rate: number | null;
    passed: number;
    decided: number;
    rows: {
      id: number;
      name: string;
      applied: string;
      received: string;
      taken: string | null;
      result: string;
      result_date: string | null;
      days_to_receive: number;
      days_to_take: number | null;
      days_to_result: number | null;
      days_open: number | null;
    }[];
  };
  breakdowns: Record<string, { label: string; rows: BreakdownRow[] }>;
  timing: {
    days_to_first_response: { median: number | null; n: number };
    days_to_rejection: { median: number | null; n: number };
    stage_durations: {
      stage: string;
      label: string;
      median_days: number | null;
      n: number;
      median_days_to_rejection: number | null;
      rejected_n: number;
    }[];
  };
  calibration: { rating: number; passed: number; failed: number; n: number; pass_rate: number | null }[];
  activity: { week: string; applied: number; responses: number }[];
  insights: Insight[];
}
