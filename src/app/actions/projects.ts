"use server";

import { revalidatePath } from "next/cache";

import { logAudit } from "@/lib/audit";
import { createClient } from "@/lib/supabase/server";
import type { ActionResult } from "@/app/actions/timesheets";

async function requireAdminId(): Promise<string | null> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return null;

  const { data: profile } = await supabase
    .from("profiles")
    .select("role")
    .eq("id", user.id)
    .single();

  return profile?.role === "admin" ? user.id : null;
}

export interface ProjectInput {
  projectCode: string;
  projectName: string;
  clientName: string;
}

function validateProjectInput(input: ProjectInput): string | null {
  if (!input.projectCode.trim()) return "Vyplňte kód projektu.";
  if (!input.projectName.trim()) return "Vyplňte název projektu.";
  return null;
}

export async function createProject(input: ProjectInput): Promise<ActionResult> {
  const adminId = await requireAdminId();
  if (!adminId) return { ok: false, error: "Akce vyžaduje administrátorská práva." };

  const validationError = validateProjectInput(input);
  if (validationError) return { ok: false, error: validationError };

  const supabase = await createClient();
  const { data, error } = await supabase
    .from("projects")
    .insert({
      project_code: input.projectCode.trim(),
      project_name: input.projectName.trim(),
      client_name: input.clientName.trim() || null,
    })
    .select("id")
    .single();

  if (error) {
    if (error.code === "23505") {
      return { ok: false, error: "Projekt s tímto kódem už existuje." };
    }
    return { ok: false, error: "Projekt se nepodařilo vytvořit." };
  }

  await logAudit("project_created", "project", data.id, {
    project_code: input.projectCode.trim(),
  });
  revalidatePath("/projects");
  return { ok: true };
}

export async function updateProject(
  projectId: string,
  input: ProjectInput,
): Promise<ActionResult> {
  const adminId = await requireAdminId();
  if (!adminId) return { ok: false, error: "Akce vyžaduje administrátorská práva." };

  const validationError = validateProjectInput(input);
  if (validationError) return { ok: false, error: validationError };

  const supabase = await createClient();
  const { error } = await supabase
    .from("projects")
    .update({
      project_code: input.projectCode.trim(),
      project_name: input.projectName.trim(),
      client_name: input.clientName.trim() || null,
    })
    .eq("id", projectId);

  if (error) {
    if (error.code === "23505") {
      return { ok: false, error: "Projekt s tímto kódem už existuje." };
    }
    return { ok: false, error: "Projekt se nepodařilo upravit." };
  }

  await logAudit("project_updated", "project", projectId, {
    project_code: input.projectCode.trim(),
  });
  revalidatePath("/projects");
  return { ok: true };
}

export async function setProjectActive(
  projectId: string,
  isActive: boolean,
): Promise<ActionResult> {
  const adminId = await requireAdminId();
  if (!adminId) return { ok: false, error: "Akce vyžaduje administrátorská práva." };

  const supabase = await createClient();
  const { error } = await supabase
    .from("projects")
    .update({ is_active: isActive })
    .eq("id", projectId);

  if (error) return { ok: false, error: "Změna stavu projektu se nezdařila." };

  await logAudit(
    isActive ? "project_activated" : "project_deactivated",
    "project",
    projectId,
  );
  revalidatePath("/projects");
  return { ok: true };
}
