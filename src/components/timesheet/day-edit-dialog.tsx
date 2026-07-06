"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { clearDay, saveDay } from "@/app/actions/timesheets";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { formatDateCzech, formatDayShortCzech } from "@/lib/dates";
import {
  DAY_TYPE_LABELS,
  type DayType,
  type Project,
  type TimesheetDay,
} from "@/lib/types";

interface DayEditDialogProps {
  monthId: string;
  date: string | null;
  entry: TimesheetDay | null;
  projects: Project[];
  holidayName?: string;
  onClose: () => void;
}

const DAY_TYPES: DayType[] = [
  "project",
  "vacation",
  "sick",
  "holiday",
  "non_working",
];

export function DayEditDialog({
  monthId,
  date,
  entry,
  projects,
  holidayName,
  onClose,
}: DayEditDialogProps) {
  // The parent renders this component with `key={date}`, so state
  // re-initializes from the entry whenever a different day is opened.
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [dayType, setDayType] = useState<DayType>(
    entry?.day_type ?? "project",
  );
  const [projectId, setProjectId] = useState<string>(entry?.project_id ?? "");
  const [note, setNote] = useState<string>(entry?.note ?? "");

  if (!date) return null;

  function handleSave() {
    if (dayType === "project" && !projectId) {
      toast.error("Vyberte projekt.");
      return;
    }
    startTransition(async () => {
      const result = await saveDay({
        monthId,
        date: date!,
        dayType,
        projectId: dayType === "project" ? projectId : null,
        note: note || null,
      });
      if (result.ok) {
        toast.success(`Den ${formatDateCzech(date!)} uložen.`);
        onClose();
        router.refresh();
      } else {
        toast.error(result.error ?? "Uložení se nezdařilo.");
      }
    });
  }

  function handleClear() {
    startTransition(async () => {
      const result = await clearDay(monthId, date!);
      if (result.ok) {
        toast.success("Záznam byl smazán.");
        onClose();
        router.refresh();
      } else {
        toast.error(result.error ?? "Smazání se nezdařilo.");
      }
    });
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{formatDayShortCzech(date)}</DialogTitle>
          <DialogDescription>
            {holidayName
              ? `Státní svátek: ${holidayName}`
              : "Nastavte typ dne a projekt."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Typ dne</Label>
            <Select
              value={dayType}
              onValueChange={(v) => setDayType(v as DayType)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DAY_TYPES.map((t) => (
                  <SelectItem key={t} value={t}>
                    {DAY_TYPE_LABELS[t]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {dayType === "project" ? (
            <div className="space-y-2">
              <Label>Projekt</Label>
              <Select value={projectId} onValueChange={setProjectId}>
                <SelectTrigger>
                  <SelectValue placeholder="Vyberte projekt…" />
                </SelectTrigger>
                <SelectContent>
                  {projects.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.project_code} — {p.project_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="day-note">Poznámka (nepovinné)</Label>
            <Textarea
              id="day-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Např. práce z domova"
              rows={2}
            />
          </div>
        </div>

        <DialogFooter className="gap-2">
          {entry ? (
            <Button
              variant="outline"
              onClick={handleClear}
              disabled={pending}
              className="sm:mr-auto"
            >
              Smazat záznam
            </Button>
          ) : null}
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            Zrušit
          </Button>
          <Button onClick={handleSave} disabled={pending}>
            {pending ? "Ukládání…" : "Uložit"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
