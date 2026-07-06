import { describe, expect, it } from "vitest";

import {
  canTransition,
  isEditableStatus,
  suggestedDayType,
  validateMonth,
  workingDates,
  type DayEntryInput,
} from "@/lib/validation";

describe("workingDates", () => {
  it("excludes weekends and public holidays", () => {
    // July 2026: 31 days, 9 weekend days, 2 holidays (5.7. Sunday overlaps, 6.7. Monday)
    const dates = workingDates(2026, 7);
    expect(dates).not.toContain("2026-07-04"); // Saturday
    expect(dates).not.toContain("2026-07-05"); // Sunday + holiday
    expect(dates).not.toContain("2026-07-06"); // Monday, Jan Hus
    expect(dates).toContain("2026-07-07");
    expect(dates).toHaveLength(22);
  });
});

describe("suggestedDayType", () => {
  it("suggests non_working for weekends, holiday for public holidays", () => {
    expect(suggestedDayType("2026-07-04")).toBe("non_working");
    expect(suggestedDayType("2026-07-06")).toBe("holiday");
    expect(suggestedDayType("2026-07-07")).toBeUndefined();
  });
});

function projectEntries(dates: string[]): DayEntryInput[] {
  return dates.map((date) => ({
    date,
    day_type: "project" as const,
    project_id: "p1",
  }));
}

describe("validateMonth", () => {
  it("reports all working days missing for an empty month", () => {
    const result = validateMonth(2026, 7, []);
    expect(result.isComplete).toBe(false);
    expect(result.missingDates).toHaveLength(22);
    expect(result.workingDayCount).toBe(22);
    expect(result.filledWorkingDayCount).toBe(0);
  });

  it("is complete when every working day has a valid entry", () => {
    const result = validateMonth(2026, 7, projectEntries(workingDates(2026, 7)));
    expect(result.isComplete).toBe(true);
    expect(result.missingDates).toHaveLength(0);
    expect(result.filledWorkingDayCount).toBe(22);
  });

  it("treats project entries without a project as missing", () => {
    const entries = projectEntries(workingDates(2026, 7));
    entries[0] = { ...entries[0], project_id: null };
    const result = validateMonth(2026, 7, entries);
    expect(result.isComplete).toBe(false);
    expect(result.missingDates).toEqual([entries[0].date]);
    expect(result.invalidProjectDates).toEqual([entries[0].date]);
  });

  it("accepts absence day types without a project", () => {
    const dates = workingDates(2026, 7);
    const entries: DayEntryInput[] = dates.map((date, i) => ({
      date,
      day_type: i === 0 ? "vacation" : i === 1 ? "sick" : "project",
      project_id: i <= 1 ? null : "p1",
    }));
    expect(validateMonth(2026, 7, entries).isComplete).toBe(true);
  });
});

describe("canTransition", () => {
  it("allows the documented workflow", () => {
    expect(canTransition("draft", "submitted", "employee")).toBe(true);
    expect(canTransition("returned", "submitted", "employee")).toBe(true);
    expect(canTransition("submitted", "approved", "admin")).toBe(true);
    expect(canTransition("submitted", "returned", "admin")).toBe(true);
  });

  it("rejects everything else", () => {
    expect(canTransition("submitted", "approved", "employee")).toBe(false);
    expect(canTransition("submitted", "returned", "employee")).toBe(false);
    expect(canTransition("approved", "submitted", "employee")).toBe(false);
    expect(canTransition("approved", "returned", "admin")).toBe(false);
    expect(canTransition("draft", "approved", "admin")).toBe(false);
  });
});

describe("isEditableStatus", () => {
  it("only draft and returned are editable", () => {
    expect(isEditableStatus("draft")).toBe(true);
    expect(isEditableStatus("returned")).toBe(true);
    expect(isEditableStatus("submitted")).toBe(false);
    expect(isEditableStatus("approved")).toBe(false);
  });
});
