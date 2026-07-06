import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { ensureMonth } from "@/app/actions/timesheets";
import { TimesheetCalendar } from "@/components/timesheet/timesheet-calendar";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatMonthCzech, isValidYearMonth } from "@/lib/dates";
import { czechHolidays } from "@/lib/holidays";
import {
  getMonth,
  getMonthDays,
  listActiveProjects,
  requireProfile,
} from "@/lib/supabase/queries";

interface PageProps {
  params: Promise<{ year: string; month: string }>;
}

export async function generateMetadata({
  params,
}: PageProps): Promise<Metadata> {
  const { year, month } = await params;
  const y = Number(year);
  const m = Number(month);
  return {
    title: isValidYearMonth(y, m) ? `Výkaz ${formatMonthCzech(y, m)}` : "Výkaz",
  };
}

export default async function TimesheetMonthPage({ params }: PageProps) {
  const { year: yearParam, month: monthParam } = await params;
  const year = Number(yearParam);
  const month = Number(monthParam);
  if (!isValidYearMonth(year, month)) notFound();

  const profile = await requireProfile();
  const timesheetMonth = await getMonth(profile.id, year, month);

  if (!timesheetMonth) {
    async function createMonth() {
      "use server";
      const result = await ensureMonth(year, month);
      if (result.ok) redirect(`/timesheets/${year}/${month}`);
    }

    return (
      <div className="mx-auto max-w-lg pt-16">
        <Card>
          <CardHeader>
            <CardTitle>Výkaz {formatMonthCzech(year, month)}</CardTitle>
            <CardDescription>
              Výkaz za tento měsíc zatím neexistuje. Po založení se víkendy a
              státní svátky předvyplní automaticky.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form action={createMonth}>
              <Button type="submit">Založit výkaz</Button>
            </form>
          </CardContent>
        </Card>
      </div>
    );
  }

  const [days, projects] = await Promise.all([
    getMonthDays(timesheetMonth.id),
    listActiveProjects(),
  ]);

  return (
    <TimesheetCalendar
      month={timesheetMonth}
      days={days}
      projects={projects}
      holidays={Object.fromEntries(czechHolidays(year))}
    />
  );
}
