"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui";
import { api, waitForRun, type Tone } from "@/lib/api";

/** Saves the job, generates a tailored resume and cover letter, then opens them. */
export function GetDocumentsButton({
  matchId,
  hasDocuments = false,
  tone,
  angle,
  variant = "primary",
  idleLabel = "Get documents",
  busyLabel = "Writing your documents…",
  readyLabel = "View documents",
  onError,
}: {
  matchId: string;
  hasDocuments?: boolean;
  tone?: Tone;
  angle?: string;
  variant?: "primary" | "secondary";
  idleLabel?: string;
  busyLabel?: string;
  readyLabel?: string;
  onError?: (message: string) => void;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  if (hasDocuments && !busy) {
    return (
      <Button variant={variant} onClick={() => router.push(`/matches/${matchId}/documents`)}>
        {readyLabel}
      </Button>
    );
  }

  async function run() {
    setBusy(true);
    try {
      const { run_id } = await api.generateDocuments(matchId, { tone, angle });
      const result = await waitForRun(run_id, 300_000);
      if (result.status === "failed") {
        onError?.(`Could not generate documents: ${result.error}`);
        return;
      }
      router.push(`/matches/${matchId}/documents`);
    } catch (e) {
      onError?.(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button variant={variant} onClick={run} disabled={busy}>
      {busy ? busyLabel : idleLabel}
    </Button>
  );
}
