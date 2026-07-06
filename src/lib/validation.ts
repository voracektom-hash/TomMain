import { isWeekend, listMonthDates } from "@/lib/dates";
import { czechHolidays } from "@/lib/holidays";
import type { DayType, MonthStatus } from "@/lib/types";

export interface DayEntryInput {
  date: string; // YYYY-MM-DD
  day_type: DayType;
  project_id: string | null;
}

export interface MonthValidationResult {
  /** Working dates (not weekend, not public holiday) without a valid entry. */
  missingDates: string[];
  /** Entries of type `project` without an assigned project. */
  invalidProjectDates: string[];
  isComplete: boolean;
  workingDayCount: number;
  filledWorkingDayCount: number;
}

/** Dates of the month that require an entry (Mon-Fri, not a public holiday). */
export function workingDates(year: number, month: number): string[] {
  const holidays = czechHolidays(year);
  return listMonthDates(year, month).filter(
    (iso) => !isWeekend(iso) && !holidays.has(iso),
  );
}

/**
 * Suggested day type when pre-filling a month:
 * weekends -> non_working, public holidays -> holiday, otherwise undefined
 * (the employee must choose a project or absence type).
 */
export function suggestedDayType(iso: string): DayType | undefined {
  if (isWeekend(iso)) return "non_working";
  const year = Number(iso.slice(0, 4));
  if (czechHolidays(year).has(iso)) return "holiday";
  return undefined;
}

function isValidEntry(entry: DayEntryInput): boolean {
  if (entry.day_type === "project") return entry.project_id !== null;
  return true;
}

/**
 * Validates a month before submission: every working day must have an entry,
 * and every `project` entry must reference a project.
 */
export function validateMonth(
  year: number,
  month: number,
  entries: DayEntryInput[],
): MonthValidationResult {
  const byDate = new Map(entries.map((e) => [e.date, e]));
  const required = workingDates(year, month);

  const missingDates: string[] = [];
  for (const iso of required) {
    const entry = byDate.get(iso);
    if (!entry || !isValidEntry(entry)) missingDates.push(iso);
  }

  const invalidProjectDates = entries
    .filter((e) => e.day_type === "project" && e.project_id === null)
    .map((e) => e.date);

  return {
    missingDates,
    invalidProjectDates,
    isComplete: missingDates.length === 0 && invalidProjectDates.length === 0,
    workingDayCount: required.length,
    filledWorkingDayCount: required.length - missingDates.length,
  };
}

/** Allowed status transitions and who may perform them. */
const TRANSITIONS: Record<
  MonthStatus,
  Partial<Record<MonthStatus, "employee" | "admin">>
> = {
  draft: { submitted: "employee" },
  returned: { submitted: "employee" },
  submitted: { approved: "admin", returned: "admin" },
  approved: {},
};

export function canTransition(
  from: MonthStatus,
  to: MonthStatus,
  role: "employee" | "admin",
): boolean {
  const actor = TRANSITIONS[from]?.[to];
  if (!actor) return false;
  // admins may also do employee transitions on their own timesheets
  return actor === role || (actor === "employee" && role === "admin");
}

export function isEditableStatus(status: MonthStatus): boolean {
  return status === "draft" || status === "returned";
}
