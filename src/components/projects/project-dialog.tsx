"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { createProject, updateProject } from "@/app/actions/projects";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Project } from "@/lib/types";

interface ProjectDialogProps {
  project: Project | null;
  onClose: () => void;
}

export function ProjectDialog({ project, onClose }: ProjectDialogProps) {
  // Rendered only while open (and keyed by the edited project), so state
  // initializes freshly on every open.
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [projectCode, setProjectCode] = useState(project?.project_code ?? "");
  const [projectName, setProjectName] = useState(project?.project_name ?? "");
  const [clientName, setClientName] = useState(project?.client_name ?? "");

  function handleSave() {
    startTransition(async () => {
      const input = { projectCode, projectName, clientName };
      const result = project
        ? await updateProject(project.id, input)
        : await createProject(input);
      if (result.ok) {
        toast.success(
          project ? "Projekt byl upraven." : "Projekt byl vytvořen.",
        );
        onClose();
        router.refresh();
      } else {
        toast.error(result.error ?? "Uložení se nezdařilo.");
      }
    });
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {project ? "Upravit projekt" : "Nový projekt"}
          </DialogTitle>
          <DialogDescription>
            Kód projektu se zobrazuje ve výkazech i v XLSX exportu.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="project-code">Kód projektu</Label>
            <Input
              id="project-code"
              value={projectCode}
              onChange={(e) => setProjectCode(e.target.value)}
              placeholder="P-1001"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="project-name">Název projektu</Label>
            <Input
              id="project-name"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              placeholder="Název projektu"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="client-name">Klient (nepovinné)</Label>
            <Input
              id="client-name"
              value={clientName}
              onChange={(e) => setClientName(e.target.value)}
              placeholder="Název klienta"
            />
          </div>
        </div>

        <DialogFooter className="gap-2">
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
