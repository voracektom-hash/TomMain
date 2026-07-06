import { toIsoDate } from "@/lib/dates";

/**
 * Czech public holidays (státní svátky a ostatní svátky).
 * Fixed-date holidays plus the movable Easter holidays
 * (Velký pátek, Velikonoční pondělí).
 */

const FIXED_HOLIDAYS: ReadonlyArray<{
  month: number;
  day: number;
  name: string;
}> = [
  { month: 1, day: 1, name: "Nový rok / Den obnovy samostatného českého státu" },
  { month: 5, day: 1, name: "Svátek práce" },
  { month: 5, day: 8, name: "Den vítězství" },
  { month: 7, day: 5, name: "Den slovanských věrozvěstů Cyrila a Metoděje" },
  { month: 7, day: 6, name: "Den upálení mistra Jana Husa" },
  { month: 9, day: 28, name: "Den české státnosti" },
  { month: 10, day: 28, name: "Den vzniku samostatného československého státu" },
  { month: 11, day: 17, name: "Den boje za svobodu a demokracii" },
  { month: 12, day: 24, name: "Štědrý den" },
  { month: 12, day: 25, name: "1. svátek vánoční" },
  { month: 12, day: 26, name: "2. svátek vánoční" },
];

/**
 * Easter Sunday for a given year (Gregorian calendar,
 * anonymous Meeus/Jones/Butcher algorithm).
 */
export function easterSunday(year: number): { month: number; day: number } {
  const a = year % 19;
  const b = Math.floor(year / 100);
  const c = year % 100;
  const d = Math.floor(b / 4);
  const e = b % 4;
  const f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30;
  const i = Math.floor(c / 4);
  const k = c % 4;
  const l = (32 + 2 * e + 2 * i - h - k) % 7;
  const m = Math.floor((a + 11 * h + 22 * l) / 451);
  const month = Math.floor((h + l - 7 * m + 114) / 31);
  const day = ((h + l - 7 * m + 114) % 31) + 1;
  return { month, day };
}

function shiftFromEaster(year: number, offsetDays: number): string {
  const { month, day } = easterSunday(year);
  const date = new Date(Date.UTC(year, month - 1, day + offsetDays));
  return toIsoDate(
    date.getUTCFullYear(),
    date.getUTCMonth() + 1,
    date.getUTCDate(),
  );
}

/** Map of ISO date -> holiday name for the given year. */
export function czechHolidays(year: number): Map<string, string> {
  const map = new Map<string, string>();
  for (const h of FIXED_HOLIDAYS) {
    map.set(toIsoDate(year, h.month, h.day), h.name);
  }
  map.set(shiftFromEaster(year, -2), "Velký pátek");
  map.set(shiftFromEaster(year, 1), "Velikonoční pondělí");
  return map;
}

export function isCzechHoliday(iso: string): boolean {
  const year = Number(iso.slice(0, 4));
  return czechHolidays(year).has(iso);
}

export function czechHolidayName(iso: string): string | undefined {
  const year = Number(iso.slice(0, 4));
  return czechHolidays(year).get(iso);
}
