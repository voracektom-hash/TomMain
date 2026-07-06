"use client";

import {
  CheckSquare,
  ChevronLeft,
  ChevronRight,
  Copy,
  Download,
  Send,
  Square,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";
import { toast } from "sonner";

import {
  bulkFillDays,
  copyPreviousMonth,
  submitMonth,
} from "@/app/actions/timesheets";
import { DayEditDialog } from "@/components/timesheet/day-edit-dialog";
import { StatusBadge } from "@/components/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  CZECH_WEEKDAYS_SHORT,
  formatMonthCzech,
  isWeekend,
  monthCalendarGrid,
  nextMonth,
  previousMonth,
} from "@/lib/dates";
import {
  DAY_TYPE_LABELS,
  type DayType,
  type Project,
  type TimesheetDay,
  type TimesheetMonth,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import { isEditableStatus, validateMonth } from "@/lib/validation";

interface TimesheetCalendarProps {
  month: TimesheetMonth;
  days: TimesheetDay[];
  projects: Project[];
  /** ISO date -> holiday name */
  holidays: Record<string, string>;
}

const ABSENCE_STYLES: Record<string, string> = {
  vacation: "bg-sky-100 text-sky-800",
  sick: "bg-rose-100 text-rose-800",
  holiday: "bg-violet-100 text-violet-800",
  non_working: "bg-muted text-muted-foreground",
};

export function TimesheetCalendar({
  month,
  days,
  projects,
  holidays,
}: TimesheetCalendarProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [editingDate, setEditingDate] = useState<string | null>(null);
  const [bulkProjectId, setBulkProjectId] = useState<string>("");

  const editable = isEditableStatus(month.status);
  const daysByDate = useMemo(
    () => new Map(days.map((d) => [d.date, d])),
    [days],
  );
  const projectsById = useMemo(
    () => new Map(projects.map((p) => [p.id, p])),
    [projects],
  );

  const validation = useMemo(
    () =>
      validateMonth(
        month.year,
        month.month,
        days.map((d) => ({
          date: d.date,
          day_type: d.day_type,
          project_id: d.project_id,
        })),
      ),
    [month.year, month.month, days],
  );
  const missingSet = useMemo(
    () => new Set(validation.missingDates),
    [validation.missingDates],
  );

  const grid = monthCalendarGrid(month.year, month.month);
  const prev = previousMonth({ year: month.year, month: month.month });
  const next = nextMonth({ year: month.year, month: month.month });

  function toggleSelected(date: string) {
    setSelected((current) => {
      const copy = new Set(current);
      if (copy.has(date)) copy.delete(date);
      else copy.add(date);
      return copy;
    });
  }

  function selectMissing() {
    setSelected(new Set(validation.missingDates));
  }

  function runAction(action: () => Promise<{ ok: boolean; error?: string }>) {
    startTransition(async () => {
      const result = await action();
      if (result.ok) {
        router.refresh();
      } else {
        toast.error(result.error ?? "Akce se nezdařila.");
      }
    });
  }

  function handleBulkFill() {
    if (!bulkProjectId) {
      toast.error("Vyberte projekt pro hromadné vyplnění.");
      return;
    }
    const dates = [...selected];
    runAction(async () => {
      const result = await bulkFillDays({
        monthId: month.id,
        dates,
        dayType: "project",
        projectId: bulkProjectId,
      });
      if (result.ok) {
        setSelected(new Set());
        toast.success(`Vyplněno ${dates.length} dnů.`);
      }
      return result;
    });
  }

  function handleCopyPrevious() {
    runAction(async () => {
      const result = await copyPreviousMonth(month.id);
      if (result.ok) toast.success("Dny byly doplněny podle minulého měsíce.");
      return result;
    });
  }

  function handleSubmit() {
    runAction(async () => {
      const result = await submitMonth(month.id);
      if (result.ok) toast.success("Výkaz byl odeslán ke schválení.");
      return result;
    });
  }

  const editingDay = editingDate ? (daysByDate.get(editingDate) ?? null) : null;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1">
          <Button asChild variant="ghost" size="icon">
            <Link
              href={`/timesheets/${prev.year}/${prev.month}`}
              title="Předchozí měsíc"
            >
              <ChevronLeft />
            </Link>
          </Button>
          <h1 className="min-w-44 text-center text-2xl font-semibold tracking-tight">
            {formatMonthCzech(month.year, month.month)}
          </h1>
          <Button asChild variant="ghost" size="icon">
            <Link
              href={`/timesheets/${next.year}/${next.month}`}
              title="Následující měsíc"
            >
              <ChevronRight />
            </Link>
          </Button>
        </div>
        <StatusBadge status={month.status} />
        <div className="text-sm text-muted-foreground">
          Vyplněno {validation.filledWorkingDayCount} z{" "}
          {validation.workingDayCount} pracovních dnů
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Button asChild variant="outline" size="sm">
            <a href={`/api/export/${month.id}`}>
              <Download /> Export XLSX
            </a>
          </Button>
          {editable ? (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={handleCopyPrevious}
                disabled={pending}
              >
                <Copy /> Zkopírovat minulý měsíc
              </Button>
              <Button
                size="sm"
                onClick={handleSubmit}
                disabled={pending || !validation.isComplete}
                title={
                  validation.isComplete
                    ? "Odeslat výkaz ke schválení"
                    : "Nejdříve vyplňte všechny pracovní dny"
                }
              >
                <Send /> Odeslat ke schválení
              </Button>
            </>
          ) : null}
        </div>
      </div>

      {month.status === "returned" && month.returned_reason ? (
        <Alert variant="warning">
          <AlertTitle>Výkaz byl vrácen k opravě</AlertTitle>
          <AlertDescription>{month.returned_reason}</AlertDescription>
        </Alert>
      ) : null}

      {!editable ? (
        <Alert>
          <AlertDescription>
            {month.status === "approved"
              ? "Výkaz je schválený a nelze jej upravovat."
              : "Výkaz čeká na schválení a nelze jej upravovat."}
          </AlertDescription>
        </Alert>
      ) : null}

      {/* Bulk fill toolbar */}
      {editable ? (
        <Card>
          <CardContent className="flex flex-wrap items-center gap-3 p-4">
            <div className="text-sm font-medium">Hromadné vyplnění:</div>
            <Button variant="outline" size="sm" onClick={selectMissing}>
              <CheckSquare /> Vybrat nevyplněné ({validation.missingDates.length})
            </Button>
            {selected.size > 0 ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSelected(new Set())}
              >
                <Square /> Zrušit výběr
              </Button>
            ) : null}
            <div className="w-64">
              <Select value={bulkProjectId} onValueChange={setBulkProjectId}>
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
            <Button
              size="sm"
              onClick={handleBulkFill}
              disabled={pending || selected.size === 0 || !bulkProjectId}
            >
              Vyplnit vybrané dny ({selected.size})
            </Button>
            <p className="w-full text-xs text-muted-foreground">
              Dny vyberete kliknutím na zaškrtávací pole v rohu dne, nebo
              tlačítkem „Vybrat nevyplněné“.
            </p>
          </CardContent>
        </Card>
      ) : null}

      {/* Calendar grid */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Kalendář</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-7 gap-1.5">
            {CZECH_WEEKDAYS_SHORT.map((wd, i) => (
              <div
                key={wd}
                className={cn(
                  "px-2 py-1 text-center text-xs font-medium uppercase tracking-wide text-muted-foreground",
                  i >= 5 && "text-muted-foreground/60",
                )}
              >
                {wd}
              </div>
            ))}
            {grid.flat().map((date, idx) => {
              if (!date) {
                return (
                  <div
                    key={`empty-${idx}`}
                    className="min-h-24 rounded-md bg-muted/30"
                  />
                );
              }

              const entry = daysByDate.get(date);
              const weekend = isWeekend(date);
              const holidayName = holidays[date];
              const missing = missingSet.has(date);
              const dayNumber = Number(date.slice(8, 10));
              const project = entry?.project_id
                ? projectsById.get(entry.project_id)
                : undefined;

              return (
                <div
                  key={date}
                  role={editable ? "button" : undefined}
                  tabIndex={editable ? 0 : undefined}
                  onClick={editable ? () => setEditingDate(date) : undefined}
                  onKeyDown={
                    editable
                      ? (e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            setEditingDate(date);
                          }
                        }
                      : undefined
                  }
                  className={cn(
                    "relative flex min-h-24 flex-col rounded-md border p-1.5 text-left transition-colors",
                    weekend || holidayName
                      ? "bg-muted/60"
                      : "bg-card",
                    editable && "cursor-pointer hover:border-primary/60",
                    missing && "border-destructive/60 border-dashed",
                    selected.has(date) && "ring-2 ring-primary",
                  )}
                >
                  <div className="flex items-start justify-between">
                    <span
                      className={cn(
                        "text-sm font-medium",
                        (weekend || holidayName) && "text-muted-foreground",
                      )}
                    >
                      {dayNumber}
                    </span>
                    {editable ? (
                      <input
                        type="checkbox"
                        aria-label={`Vybrat den ${dayNumber}`}
                        className="h-3.5 w-3.5 cursor-pointer accent-primary"
                        checked={selected.has(date)}
                        onChange={() => toggleSelected(date)}
                        onClick={(e) => e.stopPropagation()}
                      />
                    ) : null}
                  </div>
                  {holidayName ? (
                    <div
                      className="mt-0.5 truncate text-[10px] leading-tight text-violet-700"
                      title={holidayName}
                    >
                      {holidayName}
                    </div>
                  ) : null}
                  <div className="mt-auto">
                    {entry ? (
                      entry.day_type === "project" ? (
                        <div
                          className="truncate rounded bg-primary/10 px-1.5 py-0.5 text-xs font-medium text-primary"
                          title={
                            project
                              ? `${project.project_code} — ${project.project_name}`
                              : undefined
                          }
                        >
                          {project?.project_code ?? "Projekt"}
                        </div>
                      ) : (
                        <div
                          className={cn(
                            "truncate rounded px-1.5 py-0.5 text-xs font-medium",
                            ABSENCE_STYLES[entry.day_type],
                          )}
                        >
                          {DAY_TYPE_LABELS[entry.day_type as DayType]}
                        </div>
                      )
                    ) : missing ? (
                      <div className="truncate px-1 text-xs text-destructive">
                        Chybí projekt
                      </div>
                    ) : null}
                    {entry?.note ? (
                      <div
                        className="mt-0.5 truncate px-1 text-[10px] text-muted-foreground"
                        title={entry.note}
                      >
                        {entry.note}
                      </div>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Legend */}
          <div className="mt-4 flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 rounded bg-primary/10 ring-1 ring-primary/40" />
              Projekt
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 rounded bg-sky-100 ring-1 ring-sky-300" />
              Dovolená
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 rounded bg-rose-100 ring-1 ring-rose-300" />
              Nemoc
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 rounded bg-violet-100 ring-1 ring-violet-300" />
              Svátek
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 rounded border border-dashed border-destructive/60" />
              Nevyplněný pracovní den
            </span>
          </div>
        </CardContent>
      </Card>

      <DayEditDialog
        key={editingDate ?? "closed"}
        monthId={month.id}
        date={editingDate}
        entry={editingDay}
        projects={projects}
        holidayName={editingDate ? holidays[editingDate] : undefined}
        onClose={() => setEditingDate(null)}
      />
    </div>
  );
}
