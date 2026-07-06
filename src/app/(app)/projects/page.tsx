import type { Metadata } from "next";

import { ProjectsTable } from "@/components/projects/projects-table";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { listAllProjects, requireProfile } from "@/lib/supabase/queries";

export const metadata: Metadata = {
  title: "Projekty",
};

export default async function ProjectsPage() {
  const profile = await requireProfile();
  const projects = await listAllProjects();
  const isAdmin = profile.role === "admin";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Projekty</h1>
        <p className="text-sm text-muted-foreground">
          {isAdmin
            ? "Správa projektů, ke kterým zaměstnanci vykazují práci."
            : "Seznam projektů, ke kterým lze vykazovat práci."}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Seznam projektů</CardTitle>
          <CardDescription>
            Neaktivní projekty nelze vybírat ve výkazech.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ProjectsTable projects={projects} isAdmin={isAdmin} />
        </CardContent>
      </Card>
    </div>
  );
}
