"use client";

import { Check, Undo2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { approveMonth, returnMonth } from "@/app/actions/admin";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { MonthStatus } from "@/lib/types";

interface AdminMonthActionsProps {
  monthId: string;
  status: MonthStatus;
}

export function AdminMonthActions({ monthId, status }: AdminMonthActionsProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [returnOpen, setReturnOpen] = useState(false);
  const [reason, setReason] = useState("");

  if (status !== "submitted") return null;

  function handleApprove() {
    startTransition(async () => {
      const result = await approveMonth(monthId);
      if (result.ok) {
        toast.success("Výkaz byl schválen.");
        router.refresh();
      } else {
        toast.error(result.error ?? "Schválení se nezdařilo.");
      }
    });
  }

  function handleReturn() {
    startTransition(async () => {
      const result = await returnMonth(monthId, reason);
      if (result.ok) {
        toast.success("Výkaz byl vrácen k opravě.");
        setReturnOpen(false);
        setReason("");
        router.refresh();
      } else {
        toast.error(result.error ?? "Vrácení se nezdařilo.");
      }
    });
  }

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setReturnOpen(true)}
        disabled={pending}
      >
        <Undo2 /> Vrátit k opravě
      </Button>
      <Button size="sm" onClick={handleApprove} disabled={pending}>
        <Check /> Schválit
      </Button>

      <Dialog open={returnOpen} onOpenChange={(o) => !o && setReturnOpen(false)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Vrátit výkaz k opravě</DialogTitle>
            <DialogDescription>
              Zaměstnanec uvidí důvod vrácení a bude moci výkaz upravit a znovu
              odeslat.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="return-reason">Důvod vrácení</Label>
            <Textarea
              id="return-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Např. 15. 6. má být dovolená, ne projekt."
              rows={3}
            />
          </div>
          <DialogFooter className="gap-2">
            <Button
              variant="ghost"
              onClick={() => setReturnOpen(false)}
              disabled={pending}
            >
              Zrušit
            </Button>
            <Button
              onClick={handleReturn}
              disabled={pending || !reason.trim()}
            >
              {pending ? "Odesílání…" : "Vrátit výkaz"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
