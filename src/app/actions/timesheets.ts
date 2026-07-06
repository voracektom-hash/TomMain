"use server";

import { revalidatePath } from "next/cache";

import { logAudit } from "@/lib/audit";
import {
  isValidYearMonth,
  listMonthDates,
  previousMonth,
} from "@/lib/dates";
import { createClient } from "@/lib/supabase/server";
import type { DayType, TimesheetDay, TimesheetMonth } from "@/lib/types";
import {
  isEditableStatus,
  suggestedDayType,
  validateMonth,
  workingDates,
} from "@/lib/validation";

export interface ActionResult {
  ok: boolean;
  error?: string;
}

function monthPath(year: number, month: number): string {
  return `/timesheets/${year}/${month}`;
}

async function getOwnedMonth(
  monthId: string,
): Promise<{ month: TimesheetMonth | null; userId: string | null }> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { month: null, userId: null };

  const { data } = await supabase
    .from("timesheet_months")
    .select("*")
    .eq("id", monthId)
    .eq("user_id", user.id)
    .maybeSingle();

  return { month: (data as TimesheetMonth | null) ?? null, userId: user.id };
}

/**
 * Creates the timesheet month for the current user if it does not exist yet,
 * pre-filling weekends and public holidays.
 */
export async function ensureMonth(
  year: number,
  month: number,
): Promise<ActionResult & { monthId?: string }> {
  if (!isValidYearMonth(year, month)) {
    return { ok: false, error: "Neplatný měsíc." };
  }

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { ok: false, error: "Nejste přihlášeni." };

  const { data: existing } = await supabase
    .from("timesheet_months")
    .select("id")
    .eq("user_id", user.id)
    .eq("year", year)
    .eq("month", month)
    .maybeSingle();

  if (existing) return { ok: true, monthId: existing.id };

  const { data: created, error } = await supabase
    .from("timesheet_months")
    .insert({ user_id: user.id, year, month, status: "draft" })
    .select("id")
    .single();

  if (error || !created) {
    return { ok: false, error: "Výkaz se nepodařilo vytvořit." };
  }

  // Pre-fill weekends and public holidays.
  const prefill = listMonthDates(year, month)
    .map((date) => ({ date, day_type: suggestedDayType(date) }))
    .filter((d): d is { date: string; day_type: DayType } => !!d.day_type)
    .map((d) => ({
      timesheet_month_id: created.id,
      date: d.date,
      day_type: d.day_type,
      project_id: null,
    }));

  if (prefill.length > 0) {
    await supabase.from("timesheet_days").insert(prefill);
  }

  await logAudit("month_created", "timesheet_month", created.id, {
    year,
    month,
  });
  revalidatePath("/dashboard");
  revalidatePath(monthPath(year, month));
  return { ok: true, monthId: created.id };
}

export interface SaveDayInput {
  monthId: string;
  date: string; // YYYY-MM-DD
  dayType: DayType;
  projectId: string | null;
  note: string | null;
}

export async function saveDay(input: SaveDayInput): Promise<ActionResult> {
  const { month } = await getOwnedMonth(input.monthId);
  if (!month) return { ok: false, error: "Výkaz nebyl nalezen." };
  if (!isEditableStatus(month.status)) {
    return { ok: false, error: "Odeslaný nebo schválený výkaz nelze upravovat." };
  }

  const prefix = `${month.year}-${String(month.month).padStart(2, "0")}-`;
  if (!input.date.startsWith(prefix)) {
    return { ok: false, error: "Datum nepatří do tohoto měsíce." };
  }

  if (input.dayType === "project" && !input.projectId) {
    return { ok: false, error: "Pro projektový den vyberte projekt." };
  }

  const supabase = await createClient();
  const { error } = await supabase.from("timesheet_days").upsert(
    {
      timesheet_month_id: input.monthId,
      date: input.date,
      day_type: input.dayType,
      project_id: input.dayType === "project" ? input.projectId : null,
      note: input.note?.trim() || null,
    },
    { onConflict: "timesheet_month_id,date" },
  );

  if (error) return { ok: false, error: "Uložení dne se nezdařilo." };

  await logAudit("day_saved", "timesheet_month", input.monthId, {
    date: input.date,
    day_type: input.dayType,
    project_id: input.projectId,
  });
  revalidatePath(monthPath(month.year, month.month));
  revalidatePath("/dashboard");
  return { ok: true };
}

export async function clearDay(
  monthId: string,
  date: string,
): Promise<ActionResult> {
  const { month } = await getOwnedMonth(monthId);
  if (!month) return { ok: false, error: "Výkaz nebyl nalezen." };
  if (!isEditableStatus(month.status)) {
    return { ok: false, error: "Odeslaný nebo schválený výkaz nelze upravovat." };
  }

  const supabase = await createClient();
  const { error } = await supabase
    .from("timesheet_days")
    .delete()
    .eq("timesheet_month_id", monthId)
    .eq("date", date);

  if (error) return { ok: false, error: "Smazání záznamu se nezdařilo." };

  await logAudit("day_cleared", "timesheet_month", monthId, { date });
  revalidatePath(monthPath(month.year, month.month));
  revalidatePath("/dashboard");
  return { ok: true };
}

export interface BulkFillInput {
  monthId: string;
  dates: string[];
  dayType: DayType;
  projectId: string | null;
}

/** Fills all selected days with the same project / day type at once. */
export async function bulkFillDays(input: BulkFillInput): Promise<ActionResult> {
  if (input.dates.length === 0) {
    return { ok: false, error: "Nejsou vybrány žádné dny." };
  }
  if (input.dayType === "project" && !input.projectId) {
    return { ok: false, error: "Pro projektové dny vyberte projekt." };
  }

  const { month } = await getOwnedMonth(input.monthId);
  if (!month) return { ok: false, error: "Výkaz nebyl nalezen." };
  if (!isEditableStatus(month.status)) {
    return { ok: false, error: "Odeslaný nebo schválený výkaz nelze upravovat." };
  }

  const prefix = `${month.year}-${String(month.month).padStart(2, "0")}-`;
  if (input.dates.some((d) => !d.startsWith(prefix))) {
    return { ok: false, error: "Některé dny nepatří do tohoto měsíce." };
  }

  const supabase = await createClient();
  const rows = input.dates.map((date) => ({
    timesheet_month_id: input.monthId,
    date,
    day_type: input.dayType,
    project_id: input.dayType === "project" ? input.projectId : null,
  }));

  const { error } = await supabase
    .from("timesheet_days")
    .upsert(rows, { onConflict: "timesheet_month_id,date" });

  if (error) return { ok: false, error: "Hromadné vyplnění se nezdařilo." };

  await logAudit("days_bulk_filled", "timesheet_month", input.monthId, {
    dates: input.dates,
    day_type: input.dayType,
    project_id: input.projectId,
  });
  revalidatePath(monthPath(month.year, month.month));
  revalidatePath("/dashboard");
  return { ok: true };
}

/**
 * Copies the previous month's project assignments into empty working days:
 * a day gets the project of the same day-of-month if that was a project day,
 * otherwise the previous month's most used project.
 */
export async function copyPreviousMonth(monthId: string): Promise<ActionResult> {
  const { month, userId } = await getOwnedMonth(monthId);
  if (!month || !userId) return { ok: false, error: "Výkaz nebyl nalezen." };
  if (!isEditableStatus(month.status)) {
    return { ok: false, error: "Odeslaný nebo schválený výkaz nelze upravovat." };
  }

  const supabase = await createClient();
  const prev = previousMonth({ year: month.year, month: month.month });

  const { data: prevMonth } = await supabase
    .from("timesheet_months")
    .select("id")
    .eq("user_id", userId)
    .eq("year", prev.year)
    .eq("month", prev.month)
    .maybeSingle();

  if (!prevMonth) {
    return { ok: false, error: "Minulý měsíc nemá žádný výkaz." };
  }

  const { data: prevDaysData } = await supabase
    .from("timesheet_days")
    .select("*")
    .eq("timesheet_month_id", prevMonth.id);
  const prevDays = (prevDaysData ?? []) as TimesheetDay[];

  const prevProjectByDay = new Map<number, string>();
  const usage = new Map<string, number>();
  for (const d of prevDays) {
    if (d.day_type === "project" && d.project_id) {
      prevProjectByDay.set(Number(d.date.slice(8, 10)), d.project_id);
      usage.set(d.project_id, (usage.get(d.project_id) ?? 0) + 1);
    }
  }

  if (usage.size === 0) {
    return { ok: false, error: "Minulý měsíc neobsahuje žádné projektové dny." };
  }

  const mostUsedProject = [...usage.entries()].sort((a, b) => b[1] - a[1])[0][0];

  const { data: currentDaysData } = await supabase
    .from("timesheet_days")
    .select("date")
    .eq("timesheet_month_id", monthId);
  const filled = new Set((currentDaysData ?? []).map((d) => d.date as string));

  const rows = workingDates(month.year, month.month)
    .filter((date) => !filled.has(date))
    .map((date) => ({
      timesheet_month_id: monthId,
      date,
      day_type: "project" as const,
      project_id:
        prevProjectByDay.get(Number(date.slice(8, 10))) ?? mostUsedProject,
    }));

  if (rows.length === 0) {
    return { ok: false, error: "Všechny pracovní dny už jsou vyplněné." };
  }

  const { error } = await supabase.from("timesheet_days").insert(rows);
  if (error) return { ok: false, error: "Kopírování se nezdařilo." };

  await logAudit("month_copied_from_previous", "timesheet_month", monthId, {
    source_year: prev.year,
    source_month: prev.month,
    filled_days: rows.length,
  });
  revalidatePath(monthPath(month.year, month.month));
  revalidatePath("/dashboard");
  return { ok: true };
}

/** Submits the month for approval after validating completeness. */
export async function submitMonth(monthId: string): Promise<ActionResult> {
  const { month } = await getOwnedMonth(monthId);
  if (!month) return { ok: false, error: "Výkaz nebyl nalezen." };
  if (!isEditableStatus(month.status)) {
    return { ok: false, error: "Výkaz už byl odeslán nebo schválen." };
  }

  const supabase = await createClient();
  const { data: daysData } = await supabase
    .from("timesheet_days")
    .select("*")
    .eq("timesheet_month_id", monthId);
  const days = (daysData ?? []) as TimesheetDay[];

  const validation = validateMonth(
    month.year,
    month.month,
    days.map((d) => ({
      date: d.date,
      day_type: d.day_type,
      project_id: d.project_id,
    })),
  );

  if (!validation.isComplete) {
    const dates = validation.missingDates
      .map((d) => Number(d.slice(8, 10)))
      .join(". ,");
    return {
      ok: false,
      error: `Výkaz nelze odeslat, chybí vyplnit ${validation.missingDates.length} pracovních dnů (${dates}.).`,
    };
  }

  const { error } = await supabase
    .from("timesheet_months")
    .update({
      status: "submitted",
      submitted_at: new Date().toISOString(),
      returned_reason: null,
    })
    .eq("id", monthId);

  if (error) return { ok: false, error: "Odeslání výkazu se nezdařilo." };

  await logAudit("month_submitted", "timesheet_month", monthId, {
    year: month.year,
    month: month.month,
  });
  revalidatePath(monthPath(month.year, month.month));
  revalidatePath("/dashboard");
  revalidatePath("/admin/timesheets");
  return { ok: true };
}
