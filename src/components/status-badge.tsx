import { Badge } from "@/components/ui/badge";
import { MONTH_STATUS_LABELS, type MonthStatus } from "@/lib/types";

const STATUS_VARIANTS: Record<
  MonthStatus,
  "secondary" | "info" | "success" | "warning"
> = {
  draft: "secondary",
  submitted: "info",
  approved: "success",
  returned: "warning",
};

export function StatusBadge({ status }: { status: MonthStatus }) {
  return (
    <Badge variant={STATUS_VARIANTS[status]}>
      {MONTH_STATUS_LABELS[status]}
    </Badge>
  );
}
