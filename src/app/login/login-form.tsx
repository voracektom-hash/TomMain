"use client";

import { useSearchParams } from "next/navigation";
import { useActionState } from "react";

import { signIn, type AuthState } from "@/app/actions/auth";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function LoginForm() {
  const searchParams = useSearchParams();
  const [state, formAction, pending] = useActionState<AuthState, FormData>(
    signIn,
    {},
  );

  return (
    <form action={formAction} className="space-y-4">
      <input
        type="hidden"
        name="next"
        value={searchParams.get("next") ?? ""}
      />
      <div className="space-y-2">
        <Label htmlFor="email">E-mail</Label>
        <Input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          placeholder="jmeno@firma.cz"
          required
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="password">Heslo</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
        />
      </div>
      {state.error ? (
        <Alert variant="destructive">
          <AlertDescription>{state.error}</AlertDescription>
        </Alert>
      ) : null}
      <Button type="submit" className="w-full" disabled={pending}>
        {pending ? "Přihlašování…" : "Přihlásit se"}
      </Button>
    </form>
  );
}
