export type Role = "employee" | "admin";

export type MonthStatus = "draft" | "submitted" | "approved" | "returned";

export type DayType =
  | "project"
  | "vacation"
  | "sick"
  | "holiday"
  | "non_working";

export interface Profile {
  id: string;
  full_name: string | null;
  email: string | null;
  role: Role;
  created_at: string;
}

export interface Project {
  id: string;
  project_code: string;
  project_name: string;
  client_name: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface TimesheetMonth {
  id: string;
  user_id: string;
  year: number;
  month: number;
  status: MonthStatus;
  submitted_at: string | null;
  approved_at: string | null;
  approved_by: string | null;
  returned_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface TimesheetDay {
  id: string;
  timesheet_month_id: string;
  date: string; // YYYY-MM-DD
  day_type: DayType;
  project_id: string | null;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuditLog {
  id: string;
  user_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

/** Czech labels used across the UI. */
export const MONTH_STATUS_LABELS: Record<MonthStatus, string> = {
  draft: "Rozpracováno",
  submitted: "Odesláno ke schválení",
  approved: "Schváleno",
  returned: "Vráceno k opravě",
};

export const DAY_TYPE_LABELS: Record<DayType, string> = {
  project: "Projekt",
  vacation: "Dovolená",
  sick: "Nemoc",
  holiday: "Svátek",
  non_working: "Nepracovní den",
};
