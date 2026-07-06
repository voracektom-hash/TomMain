import "server-only";

import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import type {
  Profile,
  Project,
  TimesheetDay,
  TimesheetMonth,
} from "@/lib/types";

/** Current auth user + profile; redirects to /login when unauthenticated. */
export async function requireProfile(): Promise<Profile> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: profile } = await supabase
    .from("profiles")
    .select("*")
    .eq("id", user.id)
    .single();

  if (!profile) redirect("/login");
  return profile as Profile;
}

export async function requireAdmin(): Promise<Profile> {
  const profile = await requireProfile();
  if (profile.role !== "admin") redirect("/dashboard");
  return profile;
}

export async function listActiveProjects(): Promise<Project[]> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("projects")
    .select("*")
    .eq("is_active", true)
    .order("project_code");
  return (data ?? []) as Project[];
}

export async function listAllProjects(): Promise<Project[]> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("projects")
    .select("*")
    .order("project_code");
  return (data ?? []) as Project[];
}

export async function getMonth(
  userId: string,
  year: number,
  month: number,
): Promise<TimesheetMonth | null> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("timesheet_months")
    .select("*")
    .eq("user_id", userId)
    .eq("year", year)
    .eq("month", month)
    .maybeSingle();
  return (data as TimesheetMonth | null) ?? null;
}

export async function getMonthDays(
  timesheetMonthId: string,
): Promise<TimesheetDay[]> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("timesheet_days")
    .select("*")
    .eq("timesheet_month_id", timesheetMonthId)
    .order("date");
  return (data ?? []) as TimesheetDay[];
}

export async function listMyMonths(userId: string): Promise<TimesheetMonth[]> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("timesheet_months")
    .select("*")
    .eq("user_id", userId)
    .order("year", { ascending: false })
    .order("month", { ascending: false });
  return (data ?? []) as TimesheetMonth[];
}

export interface AdminMonthRow extends TimesheetMonth {
  profiles: Pick<Profile, "id" | "full_name" | "email"> | null;
}

export async function listAllMonths(): Promise<AdminMonthRow[]> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("timesheet_months")
    .select("*, profiles:user_id (id, full_name, email)")
    .order("year", { ascending: false })
    .order("month", { ascending: false });
  return (data ?? []) as AdminMonthRow[];
}

export async function getMonthById(
  id: string,
): Promise<AdminMonthRow | null> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("timesheet_months")
    .select("*, profiles:user_id (id, full_name, email)")
    .eq("id", id)
    .maybeSingle();
  return (data as AdminMonthRow | null) ?? null;
}
