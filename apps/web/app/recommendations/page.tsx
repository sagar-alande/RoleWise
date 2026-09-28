"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AlignmentLabel, Button, Card, ErrorNote, ListingStatusLabel, RequirementTags, ScoreBadge, SectionEyebrow } from "@/components/ui";
import { api, waitForRun, type Match } from "@/lib/api";

const FLAG_LABELS: Record<string, string> = {
  geo_mismatch: "remote listing asks for office days",
  level_stretch: "level is a stretch",
  level_down: "level is below yours",
  critical_gap: "missing a critical requirement",
};

export default function RecommendationsPage() {
  const router = useRouter();
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setMatches(await api.listMatches());
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function refresh() {
    setRefreshing(true);
    try {
      const { run_id } = await api.discoverMatches();
      const run = await waitForRun(run_id, 300_000);
      if (run.status === "failed") setError(`Scoring failed: ${run.error}`);
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setRefreshing(false);
    }
  }

  async function setStatus(id: string, status: string) {
    await api.setMatchStatus(id, status);
    await load();
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <SectionEyebrow>Matches</SectionEyebrow>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-slate-900">Recommended jobs</h1>
          <p className="mt-1 text-sm text-slate-600">
            Ranked by fit with your verified profile and preferences. 75% and above is strong alignment.
          </p>
        </div>
        <Button onClick={refresh} disabled={refreshing}>
          {refreshing ? "Searching…" : "Search jobs & refresh"}
        </Button>
      </div>

      <ErrorNote error={error} />

      {loading ? (
        <p className="text-slate-500">Loading…</p>
      ) : matches.length === 0 ? (
        <Card>
          <p className="font-medium text-slate-800">No matches yet.</p>
          <p className="mt-1 text-sm text-slate-500">
            Add and verify facts on your <Link className="text-indigo-600 underline" href="/">profile</Link>, then
            set your preferences there to search automatically — or add jobs yourself on the{" "}
            <Link className="text-indigo-600 underline" href="/jobs">jobs</Link> page.
          </p>
        </Card>
      ) : (
        <ul className="space-y-3">
          {matches.map((m) => {
            const reqs = m.breakdown.requirements ?? [];
            const matched = reqs.filter((r) => r.status === "matched").length;
            return (
              <li key={m.id}>
                <Card className="flex items-start gap-4 transition-shadow hover:shadow-[0_1px_2px_rgba(15,23,42,0.04),0_12px_28px_-12px_rgba(15,23,42,0.14)]">
                  <ScoreBadge score={m.score} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link href={`/matches/${m.id}`} className="font-semibold text-slate-900 hover:text-indigo-600">
                        {m.job.title}
                      </Link>
                      <AlignmentLabel score={m.score} />
                      <ListingStatusLabel status={m.job.listing_status} />
                    </div>
                    <p className="text-sm text-slate-500">
                      {m.job.company}
                      {m.job.location ? ` · ${m.job.location}` : ""}
                      {m.job.remote_mode ? ` · ${m.job.remote_mode}` : ""}
                    </p>
                    <p className="mt-2 text-sm text-slate-700">
                      {m.explanation?.summary ?? `Matches ${matched} of ${reqs.length} requirements.`}
                    </p>
                    {(m.breakdown.hard_stops ?? []).map((h, i) => (
                      <p key={i} className="mt-2 text-sm font-medium text-rose-700">Blocker: {h.message}</p>
                    ))}
                    {(m.breakdown.flags ?? []).length > 0 && (
                      <p className="mt-1 text-xs text-amber-700">
                        Heads up: {(m.breakdown.flags ?? []).map((f) => FLAG_LABELS[f.code] ?? f.code).join(" · ")}
                      </p>
                    )}
                    <RequirementTags requirements={reqs} />
                  </div>
                  <div className="flex shrink-0 flex-col gap-2">
                    <Button onClick={() => router.push(`/matches/${m.id}`)}>View match</Button>
                    <Button variant="secondary" onClick={() => setStatus(m.id, m.status === "saved" ? "new" : "saved")}>
                      {m.status === "saved" ? "Saved" : "Save"}
                    </Button>
                    <Button variant="secondary" onClick={() => setStatus(m.id, "dismissed")}>
                      Dismiss
                    </Button>
                  </div>
                </Card>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
