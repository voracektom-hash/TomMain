import { ArrowRight, CalendarPlus } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

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
import { currentYearMonth, formatMonthCzech } from "@/lib/dates";
import {
  getMonth,
  getMonthDays,
  listMyMonths,
  requireProfile,
} from "@/lib/supabase/queries";
import { validateMonth } from "@/lib/validation";

export const metadata: Metadata = {
  title: "Přehled",
};

export default async function DashboardPage() {
  const profile = await requireProfile();
  const { year, month } = currentYearMonth();

  const currentMonth = await getMonth(profile.id, year, month);
  const days = currentMonth ? await getMonthDays(currentMonth.id) : [];
  const validation = validateMonth(
    year,
    month,
    days.map((d) => ({
      date: d.date,
      day_type: d.day_type,
      project_id: d.project_id,
    })),
  );

  const history = (await listMyMonths(profile.id)).filter(
    (m) => !(m.year === year && m.month === month),
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Dobrý den{profile.full_name ? `, ${profile.full_name}` : ""}
        </h1>
        <p className="text-sm text-muted-foreground">
          Přehled vašich měsíčních výkazů práce.
        </p>
      </div>

      {currentMonth?.status === "returned" && currentMonth.returned_reason ? (
        <Alert variant="warning">
          <AlertTitle>Výkaz byl vrácen k opravě</AlertTitle>
          <AlertDescription>{currentMonth.returned_reason}</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="md:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Aktuální měsíc — {formatMonthCzech(year, month)}</CardTitle>
                <CardDescription>
                  {currentMonth
                    ? "Stav vašeho výkazu za tento měsíc."
                    : "Výkaz za tento měsíc zatím nebyl založen."}
                </CardDescription>
              </div>
              {currentMonth ? <StatusBadge status={currentMonth.status} /> : null}
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-end gap-6">
              <div>
                <div className="text-3xl font-semibold">
                  {validation.filledWorkingDayCount}
                  <span className="text-lg font-normal text-muted-foreground">
                    {" "}/ {validation.workingDayCount}
                  </span>
                </div>
                <div className="text-sm text-muted-foreground">
                  vyplněných pracovních dnů
                </div>
              </div>
              {validation.missingDates.length > 0 ? (
                <div className="text-sm text-amber-700">
                  Chybí vyplnit {validation.missingDates.length}{" "}
                  {validation.missingDates.length === 1
                    ? "den"
                    : validation.missingDates.length <= 4
                      ? "dny"
                      : "dnů"}
                  .
                </div>
              ) : (
                <div className="text-sm text-emerald-700">
                  Všechny pracovní dny jsou vyplněné.
                </div>
              )}
            </div>
            <Button asChild>
              <Link href={`/timesheets/${year}/${month}`}>
                {currentMonth ? (
                  <>
                    Otevřít výkaz <ArrowRight />
                  </>
                ) : (
                  <>
                    <CalendarPlus /> Založit výkaz
                  </>
                )}
              </Link>
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Jak vyplnit výkaz</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>1. Otevřete aktuální měsíc.</p>
            <p>2. Přiřaďte projekt každému pracovnímu dni — jednotlivě, hromadně, nebo zkopírujte minulý měsíc.</p>
            <p>3. Odešlete výkaz ke schválení.</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Historie výkazů</CardTitle>
          <CardDescription>Vaše výkazy za předchozí měsíce.</CardDescription>
        </CardHeader>
        <CardContent>
          {history.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Zatím nemáte žádné starší výkazy.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Měsíc</TableHead>
                  <TableHead>Stav</TableHead>
                  <TableHead className="text-right">Akce</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell className="font-medium">
                      {formatMonthCzech(m.year, m.month)}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={m.status} />
                    </TableCell>
                    <TableCell className="text-right">
                      <Button asChild variant="ghost" size="sm">
                        <Link href={`/timesheets/${m.year}/${m.month}`}>
                          Zobrazit
                        </Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
