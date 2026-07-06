import { describe, expect, it } from "vitest";

import {
  daysInMonth,
  formatDateCzech,
  formatMonthCzech,
  isoWeekday,
  isWeekend,
  listMonthDates,
  monthCalendarGrid,
  nextMonth,
  previousMonth,
  toIsoDate,
  isValidYearMonth,
} from "@/lib/dates";

describe("daysInMonth", () => {
  it("handles standard months", () => {
    expect(daysInMonth(2026, 1)).toBe(31);
    expect(daysInMonth(2026, 4)).toBe(30);
  });

  it("handles February and leap years", () => {
    expect(daysInMonth(2026, 2)).toBe(28);
    expect(daysInMonth(2024, 2)).toBe(29);
    expect(daysInMonth(2000, 2)).toBe(29);
    expect(daysInMonth(2100, 2)).toBe(28);
  });
});

describe("isoWeekday / isWeekend", () => {
  it("returns Monday=1 ... Sunday=7", () => {
    // 2026-07-06 is a Monday
    expect(isoWeekday("2026-07-06")).toBe(1);
    expect(isoWeekday("2026-07-11")).toBe(6);
    expect(isoWeekday("2026-07-12")).toBe(7);
  });

  it("detects weekends", () => {
    expect(isWeekend("2026-07-06")).toBe(false);
    expect(isWeekend("2026-07-11")).toBe(true);
    expect(isWeekend("2026-07-12")).toBe(true);
  });
});

describe("listMonthDates", () => {
  it("lists all dates of a month in order", () => {
    const dates = listMonthDates(2026, 2);
    expect(dates).toHaveLength(28);
    expect(dates[0]).toBe("2026-02-01");
    expect(dates[27]).toBe("2026-02-28");
  });
});

describe("previousMonth / nextMonth", () => {
  it("wraps across year boundaries", () => {
    expect(previousMonth({ year: 2026, month: 1 })).toEqual({
      year: 2025,
      month: 12,
    });
    expect(nextMonth({ year: 2026, month: 12 })).toEqual({
      year: 2027,
      month: 1,
    });
  });

  it("stays within the year otherwise", () => {
    expect(previousMonth({ year: 2026, month: 7 })).toEqual({
      year: 2026,
      month: 6,
    });
    expect(nextMonth({ year: 2026, month: 7 })).toEqual({
      year: 2026,
      month: 8,
    });
  });
});

describe("formatting", () => {
  it("formats Czech month and date", () => {
    expect(formatMonthCzech(2026, 7)).toBe("Červenec 2026");
    expect(formatDateCzech("2026-07-06")).toBe("6. 7. 2026");
    expect(toIsoDate(2026, 7, 6)).toBe("2026-07-06");
  });
});

describe("isValidYearMonth", () => {
  it("accepts valid and rejects invalid values", () => {
    expect(isValidYearMonth(2026, 7)).toBe(true);
    expect(isValidYearMonth(2026, 0)).toBe(false);
    expect(isValidYearMonth(2026, 13)).toBe(false);
    expect(isValidYearMonth(1999, 5)).toBe(false);
    expect(isValidYearMonth(2026.5, 5)).toBe(false);
  });
});

describe("monthCalendarGrid", () => {
  it("builds Monday-first weeks with padding", () => {
    // July 2026 starts on Wednesday
    const grid = monthCalendarGrid(2026, 7);
    expect(grid[0][0]).toBeNull();
    expect(grid[0][1]).toBeNull();
    expect(grid[0][2]).toBe("2026-07-01");
    for (const week of grid) expect(week).toHaveLength(7);
    const cells = grid.flat().filter(Boolean);
    expect(cells).toHaveLength(31);
    expect(cells.at(-1)).toBe("2026-07-31");
  });
});
