import { Download } from "lucide-react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { AdminMonthActions } from "@/components/admin/admin-month-actions";
import { StatusBadge } from "@/components/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  formatDateCzech,
  formatDayShortCzech,
  formatMonthCzech,
  isWeekend,
} from "@/lib/dates";
import { czechHolidayName } from "@/lib/holidays";
import {
  getMonthById,
  getMonthDays,
  listAllProjects,
  requireAdmin,
} from "@/lib/supabase/queries";
import { DAY_TYPE_LABELS } from "@/lib/types";
import { cn } from "@/lib/utils";
import { validateMonth } from "@/lib/validation";

export const metadata: Metadata = {
  title: "Detail výkazu",
};

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function AdminTimesheetDetailPage({ params }: PageProps) {
  await requireAdmin();
  const { id } = await params;

  const month = await getMonthById(id);
  if (!month) notFound();

  const [days, projects] = await Promise.all([
    getMonthDays(month.id),
    listAllProjects(),
  ]);
  const projectsById = new Map(projects.map((p) => [p.id, p]));

  const validation = validateMonth(
    month.year,
    month.month,
    days.map((d) => ({
      date: d.date,
      day_type: d.day_type,
      project_id: d.project_id,
    })),
  );

  const projectDayCounts = new Map<string, number>();
  for (const d of days) {
    if (d.day_type === "project" && d.project_id) {
      projectDayCounts.set(
        d.project_id,
        (projectDayCounts.get(d.project_id) ?? 0) + 1,
      );
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {formatMonthCzech(month.year, month.month)} —{" "}
            {month.profiles?.full_name ?? month.profiles?.email ?? "—"}
          </h1>
          <p className="text-sm text-muted-foreground">
            {month.profiles?.email}
          </p>
        </div>
        <StatusBadge status={month.status} />
        <div className="ml-auto flex items-center gap-2">
          <Button asChild variant="outline" size="sm">
            <a href={`/api/export/${month.id}`}>
              <Download /> Export XLSX
            </a>
          </Button>
          <AdminMonthActions monthId={month.id} status={month.status} />
        </div>
      </div>

      {month.status === "returned" && month.returned_reason ? (
        <Alert variant="warning">
          <AlertTitle>Vráceno k opravě</AlertTitle>
          <AlertDescription>{month.returned_reason}</AlertDescription>
        </Alert>
      ) : null}

      {!validation.isComplete ? (
        <Alert variant="destructive">
          <AlertDescription>
            Výkaz není kompletní — chybí {validation.missingDates.length}{" "}
            pracovních dnů (
            {validation.missingDates.map(formatDateCzech).join(", ")}).
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Souhrn</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Pracovních dnů</span>
              <span className="font-medium">{validation.workingDayCount}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Vyplněno</span>
              <span className="font-medium">
                {validation.filledWorkingDayCount}
              </span>
            </div>
            {month.submitted_at ? (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Odesláno</span>
                <span className="font-medium">
                  {new Date(month.submitted_at).toLocaleDateString("cs-CZ")}
                </span>
              </div>
            ) : null}
            {month.approved_at ? (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Schváleno</span>
                <span className="font-medium">
                  {new Date(month.approved_at).toLocaleDateString("cs-CZ")}
                </span>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Dny podle projektů</CardTitle>
          </CardHeader>
          <CardContent>
            {projectDayCounts.size === 0 ? (
              <p className="text-sm text-muted-foreground">
                Žádné projektové dny.
              </p>
            ) : (
              <div className="space-y-1 text-sm">
                {[...projectDayCounts.entries()].map(([projectId, count]) => {
                  const project = projectsById.get(projectId);
                  return (
                    <div key={projectId} className="flex justify-between">
                      <span>
                        <span className="font-mono font-medium">
                          {project?.project_code ?? "?"}
                        </span>{" "}
                        <span className="text-muted-foreground">
                          {project?.project_name}
                        </span>
                      </span>
                      <span className="font-medium">{count} dnů</span>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Jednotlivé dny</CardTitle>
          <CardDescription>
            Kompletní záznam měsíce, víkendy jsou podbarvené.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Den</TableHead>
                <TableHead>Typ</TableHead>
                <TableHead>Projekt</TableHead>
                <TableHead>Poznámka</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {days.map((d) => {
                const project = d.project_id
                  ? projectsById.get(d.project_id)
                  : undefined;
                const holiday = czechHolidayName(d.date);
                return (
                  <TableRow
                    key={d.id}
                    className={cn(isWeekend(d.date) && "bg-muted/50")}
                  >
                    <TableCell className="font-medium">
                      {formatDayShortCzech(d.date)}
                      {holiday ? (
                        <span className="ml-2 text-xs text-violet-700">
                          {holiday}
                        </span>
                      ) : null}
                    </TableCell>
                    <TableCell>{DAY_TYPE_LABELS[d.day_type]}</TableCell>
                    <TableCell>
                      {project ? (
                        <>
                          <span className="font-mono">
                            {project.project_code}
                          </span>{" "}
                          <span className="text-muted-foreground">
                            {project.project_name}
                          </span>
                        </>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {d.note ?? "—"}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
