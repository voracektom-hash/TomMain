/**
 * Type-safe date helpers for timesheet months.
 *
 * All dates are handled as ISO strings (`YYYY-MM-DD`) to stay
 * timezone-independent; Date objects are only created in UTC.
 */

export interface YearMonth {
  year: number;
  month: number; // 1-12
}

/** Czech weekday abbreviations, Monday first. */
export const CZECH_WEEKDAYS_SHORT = [
  "Po",
  "Út",
  "St",
  "Čt",
  "Pá",
  "So",
  "Ne",
] as const;

export const CZECH_MONTH_NAMES = [
  "Leden",
  "Únor",
  "Březen",
  "Duben",
  "Květen",
  "Červen",
  "Červenec",
  "Srpen",
  "Září",
  "Říjen",
  "Listopad",
  "Prosinec",
] as const;

export function isValidYearMonth(year: number, month: number): boolean {
  return (
    Number.isInteger(year) &&
    Number.isInteger(month) &&
    year >= 2000 &&
    year <= 2100 &&
    month >= 1 &&
    month <= 12
  );
}

export function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

/** Formats an ISO date string for the given day of a month. */
export function toIsoDate(year: number, month: number, day: number): string {
  const mm = String(month).padStart(2, "0");
  const dd = String(day).padStart(2, "0");
  return `${year}-${mm}-${dd}`;
}

export function parseIsoDate(iso: string): {
  year: number;
  month: number;
  day: number;
} {
  const [year, month, day] = iso.split("-").map(Number);
  return { year, month, day };
}

/** ISO weekday: 1 = Monday … 7 = Sunday. */
export function isoWeekday(iso: string): number {
  const { year, month, day } = parseIsoDate(iso);
  const wd = new Date(Date.UTC(year, month - 1, day)).getUTCDay();
  return wd === 0 ? 7 : wd;
}

export function isWeekend(iso: string): boolean {
  return isoWeekday(iso) >= 6;
}

/** All ISO dates of the given month, in order. */
export function listMonthDates(year: number, month: number): string[] {
  const count = daysInMonth(year, month);
  const dates: string[] = [];
  for (let day = 1; day <= count; day++) {
    dates.push(toIsoDate(year, month, day));
  }
  return dates;
}

export function previousMonth({ year, month }: YearMonth): YearMonth {
  return month === 1 ? { year: year - 1, month: 12 } : { year, month: month - 1 };
}

export function nextMonth({ year, month }: YearMonth): YearMonth {
  return month === 12 ? { year: year + 1, month: 1 } : { year, month: month + 1 };
}

export function currentYearMonth(now: Date = new Date()): YearMonth {
  return { year: now.getFullYear(), month: now.getMonth() + 1 };
}

/** "Leden 2026" */
export function formatMonthCzech(year: number, month: number): string {
  return `${CZECH_MONTH_NAMES[month - 1]} ${year}`;
}

/** "6. 7. 2026" */
export function formatDateCzech(iso: string): string {
  const { year, month, day } = parseIsoDate(iso);
  return `${day}. ${month}. ${year}`;
}

/** "Po 6. 7." */
export function formatDayShortCzech(iso: string): string {
  const { month, day } = parseIsoDate(iso);
  return `${CZECH_WEEKDAYS_SHORT[isoWeekday(iso) - 1]} ${day}. ${month}.`;
}

/**
 * Calendar grid for a month: weeks of 7 cells (Monday-first),
 * `null` for cells belonging to adjacent months.
 */
export function monthCalendarGrid(
  year: number,
  month: number,
): (string | null)[][] {
  const dates = listMonthDates(year, month);
  const leading = isoWeekday(dates[0]) - 1;
  const cells: (string | null)[] = [
    ...Array.from({ length: leading }, () => null),
    ...dates,
  ];
  while (cells.length % 7 !== 0) cells.push(null);
  const weeks: (string | null)[][] = [];
  for (let i = 0; i < cells.length; i += 7) {
    weeks.push(cells.slice(i, i + 7));
  }
  return weeks;
}
