import "server-only";

import { createClient } from "@/lib/supabase/server";

/**
 * Appends an audit log entry as the current user.
 * Failures are swallowed on purpose: auditing must never break the action.
 */
export async function logAudit(
  action: string,
  entityType: string,
  entityId: string | null,
  metadata?: Record<string, unknown>,
): Promise<void> {
  try {
    const supabase = await createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (!user) return;

    await supabase.from("audit_logs").insert({
      user_id: user.id,
      action,
      entity_type: entityType,
      entity_id: entityId,
      metadata: metadata ?? null,
    });
  } catch {
    // ignore
  }
}
