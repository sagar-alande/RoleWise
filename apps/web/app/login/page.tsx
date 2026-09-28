"use client";

import { useState } from "react";
import { Button, Card, ErrorNote, SectionEyebrow } from "@/components/ui";
import { login } from "@/lib/auth";

export default function LoginPage() {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      await login();
    } catch (e) {
      setError(String(e));
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto mt-16 max-w-sm space-y-6 text-center">
      <div>
        <SectionEyebrow>Sign in</SectionEyebrow>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-slate-900">Welcome to RoleWise</h1>
        <p className="mt-2 text-sm text-slate-600">
          Sign in to see your own profile, matches and saved jobs - separate from anyone else's.
        </p>
      </div>
      <Card>
        <ErrorNote error={error} />
        <Button onClick={start} disabled={busy} className="w-full justify-center">
          {busy ? "Redirecting…" : "Continue with Google"}
        </Button>
      </Card>
    </div>
  );
}
