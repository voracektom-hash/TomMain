import type { Metadata } from "next";
import Link from "next/link";

import { StatusBadge } from "@/components/status-badge";
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
import { formatMonthCzech } from "@/lib/dates";
import { listAllMonths, requireAdmin } from "@/lib/supabase/queries";

export const metadata: Metadata = {
  title: "Schvalování výkazů",
};

export default async function AdminTimesheetsPage() {
  await requireAdmin();
  const months = await listAllMonths();

  const waiting = months.filter((m) => m.status === "submitted");
  const others = months.filter((m) => m.status !== "submitted");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Schvalování výkazů
        </h1>
        <p className="text-sm text-muted-foreground">
          Přehled výkazů všech zaměstnanců.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Čeká na schválení ({waiting.length})</CardTitle>
          <CardDescription>
            Odeslané výkazy, které je potřeba schválit nebo vrátit.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <MonthsTable rows={waiting} emptyText="Žádné výkazy nečekají na schválení." />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Ostatní výkazy</CardTitle>
        </CardHeader>
        <CardContent>
          <MonthsTable rows={others} emptyText="Žádné další výkazy." />
        </CardContent>
      </Card>
    </div>
  );
}

function MonthsTable({
  rows,
  emptyText,
}: {
  rows: Awaited<ReturnType<typeof listAllMonths>>;
  emptyText: string;
}) {
  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground">{emptyText}</p>;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Zaměstnanec</TableHead>
          <TableHead>Měsíc</TableHead>
          <TableHead>Stav</TableHead>
          <TableHead className="text-right">Akce</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((m) => (
          <TableRow key={m.id}>
            <TableCell>
              <div className="font-medium">
                {m.profiles?.full_name ?? m.profiles?.email ?? "—"}
              </div>
              <div className="text-xs text-muted-foreground">
                {m.profiles?.email}
              </div>
            </TableCell>
            <TableCell>{formatMonthCzech(m.year, m.month)}</TableCell>
            <TableCell>
              <StatusBadge status={m.status} />
            </TableCell>
            <TableCell className="text-right">
              <Button asChild variant="ghost" size="sm">
                <Link href={`/admin/timesheets/${m.id}`}>Otevřít</Link>
              </Button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
