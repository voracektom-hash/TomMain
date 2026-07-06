import { describe, expect, it } from "vitest";

import {
  czechHolidayName,
  czechHolidays,
  easterSunday,
  isCzechHoliday,
} from "@/lib/holidays";

describe("easterSunday", () => {
  it("computes known Easter Sundays", () => {
    expect(easterSunday(2024)).toEqual({ month: 3, day: 31 });
    expect(easterSunday(2025)).toEqual({ month: 4, day: 20 });
    expect(easterSunday(2026)).toEqual({ month: 4, day: 5 });
    expect(easterSunday(2027)).toEqual({ month: 3, day: 28 });
  });
});

describe("czechHolidays", () => {
  it("contains all fixed holidays", () => {
    const h = czechHolidays(2026);
    for (const iso of [
      "2026-01-01",
      "2026-05-01",
      "2026-05-08",
      "2026-07-05",
      "2026-07-06",
      "2026-09-28",
      "2026-10-28",
      "2026-11-17",
      "2026-12-24",
      "2026-12-25",
      "2026-12-26",
    ]) {
      expect(h.has(iso), iso).toBe(true);
    }
  });

  it("contains movable Easter holidays", () => {
    const h = czechHolidays(2026);
    expect(h.get("2026-04-03")).toBe("Velký pátek");
    expect(h.get("2026-04-06")).toBe("Velikonoční pondělí");
  });

  it("has 13 holidays in total", () => {
    expect(czechHolidays(2026).size).toBe(13);
  });
});

describe("isCzechHoliday / czechHolidayName", () => {
  it("detects holidays across years", () => {
    expect(isCzechHoliday("2025-04-18")).toBe(true); // Velký pátek 2025
    expect(isCzechHoliday("2025-04-21")).toBe(true); // Velikonoční pondělí 2025
    expect(isCzechHoliday("2025-04-22")).toBe(false);
    expect(czechHolidayName("2026-07-06")).toBe(
      "Den upálení mistra Jana Husa",
    );
  });
});
