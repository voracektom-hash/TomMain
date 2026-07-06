import ExcelJS from "exceljs";
import { NextResponse } from "next/server";

import {
  formatMonthCzech,
  isWeekend,
  isoWeekday,
  CZECH_WEEKDAYS_SHORT,
} from "@/lib/dates";
import { czechHolidayName } from "@/lib/holidays";
import { createClient } from "@/lib/supabase/server";
import {
  DAY_TYPE_LABELS,
  MONTH_STATUS_LABELS,
  type Profile,
  type Project,
  type TimesheetDay,
  type TimesheetMonth,
} from "@/lib/types";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ monthId: string }> },
) {
  const { monthId } = await params;
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Nepřihlášený uživatel." }, { status: 401 });
  }

  // RLS restricts visibility to the owner or an admin.
  const { data: monthData } = await supabase
    .from("timesheet_months")
    .select("*")
    .eq("id", monthId)
    .maybeSingle();
  const month = monthData as TimesheetMonth | null;

  if (!month) {
    return NextResponse.json({ error: "Výkaz nebyl nalezen." }, { status: 404 });
  }

  const [{ data: daysData }, { data: projectsData }, { data: ownerData }] =
    await Promise.all([
      supabase
        .from("timesheet_days")
        .select("*")
        .eq("timesheet_month_id", month.id)
        .order("date"),
      supabase.from("projects").select("*"),
      supabase
        .from("profiles")
        .select("*")
        .eq("id", month.user_id)
        .maybeSingle(),
    ]);

  const days = (daysData ?? []) as TimesheetDay[];
  const projectsById = new Map(
    ((projectsData ?? []) as Project[]).map((p) => [p.id, p]),
  );
  const owner = ownerData as Profile | null;

  const workbook = new ExcelJS.Workbook();
  workbook.creator = "Výkazy práce";
  workbook.created = new Date();

  const sheet = workbook.addWorksheet(
    `${month.year}-${String(month.month).padStart(2, "0")}`,
    { properties: { defaultRowHeight: 16 } },
  );

  sheet.columns = [
    { header: "", key: "date", width: 12 },
    { header: "", key: "weekday", width: 6 },
    { header: "", key: "type", width: 18 },
    { header: "", key: "code", width: 12 },
    { header: "", key: "project", width: 32 },
    { header: "", key: "note", width: 36 },
  ];

  // Header block
  sheet.getCell("A1").value = "Měsíční výkaz práce";
  sheet.getCell("A1").font = { bold: true, size: 14 };
  sheet.getCell("A2").value = "Zaměstnanec:";
  sheet.getCell("B2").value = owner?.full_name ?? owner?.email ?? "";
  sheet.getCell("A3").value = "Měsíc:";
  sheet.getCell("B3").value = formatMonthCzech(month.year, month.month);
  sheet.getCell("A4").value = "Stav:";
  sheet.getCell("B4").value = MONTH_STATUS_LABELS[month.status];

  // Table header
  const headerRow = sheet.getRow(6);
  headerRow.values = ["Datum", "Den", "Typ dne", "Kód projektu", "Projekt", "Poznámka"];
  headerRow.font = { bold: true };
  headerRow.eachCell((cell) => {
    cell.fill = {
      type: "pattern",
      pattern: "solid",
      fgColor: { argb: "FFE8EDF5" },
    };
    cell.border = { bottom: { style: "thin" } };
  });

  let rowIndex = 7;
  for (const day of days) {
    const project = day.project_id ? projectsById.get(day.project_id) : null;
    const holiday = czechHolidayName(day.date);
    const row = sheet.getRow(rowIndex++);
    const [y, m, d] = day.date.split("-").map(Number);
    row.values = [
      `${d}. ${m}. ${y}`,
      CZECH_WEEKDAYS_SHORT[isoWeekday(day.date) - 1],
      DAY_TYPE_LABELS[day.day_type],
      project?.project_code ?? "",
      project?.project_name ?? (holiday ?? ""),
      day.note ?? "",
    ];
    if (isWeekend(day.date)) {
      row.eachCell({ includeEmpty: false }, (cell) => {
        cell.fill = {
          type: "pattern",
          pattern: "solid",
          fgColor: { argb: "FFF2F2F2" },
        };
      });
    }
  }

  // Summary
  rowIndex += 1;
  const summaryTitle = sheet.getRow(rowIndex++);
  summaryTitle.values = ["Souhrn"];
  summaryTitle.font = { bold: true };

  const typeCounts = new Map<string, number>();
  const projectCounts = new Map<string, number>();
  for (const day of days) {
    typeCounts.set(day.day_type, (typeCounts.get(day.day_type) ?? 0) + 1);
    if (day.day_type === "project" && day.project_id) {
      projectCounts.set(
        day.project_id,
        (projectCounts.get(day.project_id) ?? 0) + 1,
      );
    }
  }

  for (const [type, count] of typeCounts) {
    sheet.getRow(rowIndex++).values = [
      DAY_TYPE_LABELS[type as keyof typeof DAY_TYPE_LABELS],
      count,
    ];
  }

  rowIndex += 1;
  const projectsTitle = sheet.getRow(rowIndex++);
  projectsTitle.values = ["Dny podle projektů"];
  projectsTitle.font = { bold: true };
  for (const [projectId, count] of projectCounts) {
    const project = projectsById.get(projectId);
    sheet.getRow(rowIndex++).values = [
      project?.project_code ?? "?",
      project?.project_name ?? "",
      count,
    ];
  }

  const buffer = await workbook.xlsx.writeBuffer();

  const slug = (owner?.full_name ?? owner?.email ?? "vykaz")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
  const filename = `vykaz-${month.year}-${String(month.month).padStart(2, "0")}-${slug}.xlsx`;

  return new NextResponse(buffer as ArrayBuffer, {
    headers: {
      "Content-Type":
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "Content-Disposition": `attachment; filename="${filename}"`,
    },
  });
}
