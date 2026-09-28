"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ErrorNote } from "@/components/ui";
import { handleCallback } from "@/lib/auth";

function CallbackInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = params.get("code");
    const state = params.get("state");
    const oauthError = params.get("error_description") ?? params.get("error");
    if (oauthError) {
      setError(oauthError);
      return;
    }
    if (!code || !state) {
      setError("Missing sign-in code. Please try again.");
      return;
    }
    handleCallback(code, state)
      .then(() => router.replace("/"))
      .catch((e) => setError(String(e)));
    // handleCallback is idempotent-unsafe (single-use code) - run exactly once per mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) {
    return (
      <div className="mx-auto mt-16 max-w-sm space-y-4 text-center">
        <ErrorNote error={error} />
        <a href="/login" className="text-sm text-indigo-600 underline">
          Try signing in again
        </a>
      </div>
    );
  }
  return <p className="mt-16 text-center text-sm text-slate-500">Signing you in…</p>;
}

export default function CallbackPage() {
  return (
    <Suspense fallback={<p className="mt-16 text-center text-sm text-slate-500">Signing you in…</p>}>
      <CallbackInner />
    </Suspense>
  );
}
