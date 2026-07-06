import { CalendarDays } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";

import { LoginForm } from "@/app/login/login-form";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export const metadata: Metadata = {
  title: "Přihlášení",
};

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/40 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <div className="mx-auto mb-2 flex h-11 w-11 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <CalendarDays className="h-6 w-6" />
          </div>
          <CardTitle className="text-xl">Výkazy práce</CardTitle>
          <CardDescription>
            Přihlaste se svým firemním e-mailem.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Suspense>
            <LoginForm />
          </Suspense>
        </CardContent>
      </Card>
    </main>
  );
}
