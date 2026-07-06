"use server";

import { revalidatePath } from "next/cache";

import { logAudit } from "@/lib/audit";
import { createClient } from "@/lib/supabase/server";
import type { TimesheetMonth } from "@/lib/types";
import { canTransition } from "@/lib/validation";
import type { ActionResult } from "@/app/actions/timesheets";

async function getAdminContext(): Promise<{
  userId: string | null;
  isAdmin: boolean;
}> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { userId: null, isAdmin: false };

  const { data: profile } = await supabase
    .from("profiles")
    .select("role")
    .eq("id", user.id)
    .single();

  return { userId: user.id, isAdmin: profile?.role === "admin" };
}

async function loadMonth(monthId: string): Promise<TimesheetMonth | null> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("timesheet_months")
    .select("*")
    .eq("id", monthId)
    .maybeSingle();
  return (data as TimesheetMonth | null) ?? null;
}

export async function approveMonth(monthId: string): Promise<ActionResult> {
  const { userId, isAdmin } = await getAdminContext();
  if (!userId || !isAdmin) {
    return { ok: false, error: "Akce vyžaduje administrátorská práva." };
  }

  const month = await loadMonth(monthId);
  if (!month) return { ok: false, error: "Výkaz nebyl nalezen." };
  if (!canTransition(month.status, "approved", "admin")) {
    return { ok: false, error: "Schválit lze pouze odeslaný výkaz." };
  }

  const supabase = await createClient();
  const { error } = await supabase
    .from("timesheet_months")
    .update({
      status: "approved",
      approved_at: new Date().toISOString(),
      approved_by: userId,
    })
    .eq("id", monthId);

  if (error) return { ok: false, error: "Schválení se nezdařilo." };

  await logAudit("month_approved", "timesheet_month", monthId, {
    year: month.year,
    month: month.month,
    user_id: month.user_id,
  });
  revalidatePath("/admin/timesheets");
  revalidatePath(`/admin/timesheets/${monthId}`);
  revalidatePath("/dashboard");
  return { ok: true };
}

export async function returnMonth(
  monthId: string,
  reason: string,
): Promise<ActionResult> {
  const trimmed = reason.trim();
  if (!trimmed) {
    return { ok: false, error: "Uveďte důvod vrácení." };
  }

  const { userId, isAdmin } = await getAdminContext();
  if (!userId || !isAdmin) {
    return { ok: false, error: "Akce vyžaduje administrátorská práva." };
  }

  const month = await loadMonth(monthId);
  if (!month) return { ok: false, error: "Výkaz nebyl nalezen." };
  if (!canTransition(month.status, "returned", "admin")) {
    return { ok: false, error: "Vrátit lze pouze odeslaný výkaz." };
  }

  const supabase = await createClient();
  const { error } = await supabase
    .from("timesheet_months")
    .update({
      status: "returned",
      returned_reason: trimmed,
      approved_at: null,
      approved_by: null,
    })
    .eq("id", monthId);

  if (error) return { ok: false, error: "Vrácení se nezdařilo." };

  await logAudit("month_returned", "timesheet_month", monthId, {
    year: month.year,
    month: month.month,
    user_id: month.user_id,
    reason: trimmed,
  });
  revalidatePath("/admin/timesheets");
  revalidatePath(`/admin/timesheets/${monthId}`);
  revalidatePath("/dashboard");
  return { ok: true };
}
