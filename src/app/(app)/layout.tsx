import { CalendarDays, LogOut } from "lucide-react";
import Link from "next/link";

import { signOut } from "@/app/actions/auth";
import { Button } from "@/components/ui/button";
import { currentYearMonth } from "@/lib/dates";
import { requireProfile } from "@/lib/supabase/queries";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const profile = await requireProfile();
  const { year, month } = currentYearMonth();

  const navItems = [
    { href: "/dashboard", label: "Přehled" },
    { href: `/timesheets/${year}/${month}`, label: "Můj výkaz" },
    { href: "/projects", label: "Projekty" },
    ...(profile.role === "admin"
      ? [{ href: "/admin/timesheets", label: "Schvalování" }]
      : []),
  ];

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-14 w-full max-w-6xl items-center gap-6 px-4">
          <Link
            href="/dashboard"
            className="flex items-center gap-2 font-semibold"
          >
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <CalendarDays className="h-4 w-4" />
            </span>
            Výkazy práce
          </Link>
          <nav className="flex items-center gap-1 text-sm">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="rounded-md px-3 py-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <div className="hidden text-right text-sm sm:block">
              <div className="font-medium leading-tight">
                {profile.full_name ?? profile.email}
              </div>
              <div className="text-xs text-muted-foreground">
                {profile.role === "admin" ? "Administrátor" : "Zaměstnanec"}
              </div>
            </div>
            <form action={signOut}>
              <Button
                variant="ghost"
                size="icon"
                type="submit"
                title="Odhlásit se"
              >
                <LogOut className="h-4 w-4" />
                <span className="sr-only">Odhlásit se</span>
              </Button>
            </form>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        {children}
      </main>
    </div>
  );
}
