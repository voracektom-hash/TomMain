"use client";

import { Pencil, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { setProjectActive } from "@/app/actions/projects";
import { ProjectDialog } from "@/components/projects/project-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Project } from "@/lib/types";

interface ProjectsTableProps {
  projects: Project[];
  isAdmin: boolean;
}

export function ProjectsTable({ projects, isAdmin }: ProjectsTableProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Project | null>(null);

  function handleToggleActive(project: Project) {
    startTransition(async () => {
      const result = await setProjectActive(project.id, !project.is_active);
      if (result.ok) {
        toast.success(
          project.is_active
            ? `Projekt ${project.project_code} byl deaktivován.`
            : `Projekt ${project.project_code} byl aktivován.`,
        );
        router.refresh();
      } else {
        toast.error(result.error ?? "Akce se nezdařila.");
      }
    });
  }

  return (
    <div className="space-y-4">
      {isAdmin ? (
        <Button
          size="sm"
          onClick={() => {
            setEditing(null);
            setDialogOpen(true);
          }}
        >
          <Plus /> Nový projekt
        </Button>
      ) : null}

      {projects.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Zatím nejsou založeny žádné projekty.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Kód</TableHead>
              <TableHead>Název</TableHead>
              <TableHead>Klient</TableHead>
              <TableHead>Stav</TableHead>
              {isAdmin ? (
                <TableHead className="text-right">Akce</TableHead>
              ) : null}
            </TableRow>
          </TableHeader>
          <TableBody>
            {projects.map((p) => (
              <TableRow key={p.id}>
                <TableCell className="font-mono font-medium">
                  {p.project_code}
                </TableCell>
                <TableCell>{p.project_name}</TableCell>
                <TableCell className="text-muted-foreground">
                  {p.client_name ?? "—"}
                </TableCell>
                <TableCell>
                  {p.is_active ? (
                    <Badge variant="success">Aktivní</Badge>
                  ) : (
                    <Badge variant="secondary">Neaktivní</Badge>
                  )}
                </TableCell>
                {isAdmin ? (
                  <TableCell className="space-x-1 text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setEditing(p);
                        setDialogOpen(true);
                      }}
                    >
                      <Pencil /> Upravit
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={pending}
                      onClick={() => handleToggleActive(p)}
                    >
                      {p.is_active ? "Deaktivovat" : "Aktivovat"}
                    </Button>
                  </TableCell>
                ) : null}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {isAdmin && dialogOpen ? (
        <ProjectDialog
          key={editing?.id ?? "new"}
          project={editing}
          onClose={() => setDialogOpen(false)}
        />
      ) : null}
    </div>
  );
}
