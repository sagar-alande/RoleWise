"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { GetDocumentsButton } from "@/components/GetDocumentsButton";
import { AlignmentLabel, Card, ErrorNote, ListingStatusLabel, ScoreBadge, SectionEyebrow } from "@/components/ui";
import { api, type Match } from "@/lib/api";

const STATUSES = ["saved", "pursuing", "applied", "interview", "offer", "rejected"] as const;
const STATUS_LABELS: Record<string, string> = {
  saved: "Saved",
  pursuing: "Preparing",
  applied: "Applied",
  interview: "Interviewing",
  offer: "Offer",
  rejected: "Closed",
  new: "Saved",
  dismissed: "Dismissed",
};

export default function MyJobsPage() {
  const [jobs, setJobs] = useState<Match[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("all");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setJobs(await api.listMyJobs());
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

  async function setStatus(id: string, status: string) {
    await api.setMatchStatus(id, status);
    await load();
  }

  const counts = Object.fromEntries(STATUSES.map((s) => [s, jobs.filter((j) => j.status === s).length]));
  const visible = filter === "all" ? jobs : jobs.filter((j) => j.status === filter);

  return (
    <div className="space-y-6">
      <div>
        <SectionEyebrow>My jobs</SectionEyebrow>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight text-slate-900">Saved jobs and applications</h1>
        <p className="mt-1 text-sm text-slate-600">
          Every job you save or generate documents for stays here with its tailored resume and cover letter.
        </p>
      </div>

      <ErrorNote error={error} />

      <div className="flex flex-wrap gap-2 text-sm">
        {["all", ...STATUSES].map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`rounded-full px-3 py-1 font-medium ${
              filter === s ? "bg-indigo-600 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"
            }`}
          >
            {s === "all" ? `All (${jobs.length})` : `${STATUS_LABELS[s]} (${counts[s] ?? 0})`}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-slate-500">Loading…</p>
      ) : visible.length === 0 ? (
        <Card>
          <p className="font-medium text-slate-800">Nothing here yet.</p>
          <p className="mt-1 text-sm text-slate-500">
            Save a job or click <b>Get documents</b> on your{" "}
            <Link className="text-indigo-600 underline" href="/recommendations">
              recommendations
            </Link>
            .
          </p>
        </Card>
      ) : (
        <ul className="space-y-3">
          {visible.map((m) => (
            <li key={m.id}>
              <Card className="flex flex-wrap items-center gap-4">
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
                    {m.job.url && (
                      <>
                        {" · "}
                        <a className="text-indigo-600 hover:underline" href={m.job.url} target="_blank" rel="noreferrer">
                          Posting
                        </a>
                      </>
                    )}
                  </p>
                  <p className="mt-1 text-xs text-slate-400">
                    {m.has_documents ? "Tailored resume and cover letter saved" : "No documents yet"}
                  </p>
                </div>
                <select
                  value={STATUSES.includes(m.status as (typeof STATUSES)[number]) ? m.status : "saved"}
                  onChange={(e) => setStatus(m.id, e.target.value)}
                  className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-700"
                  aria-label="Application status"
                >
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {STATUS_LABELS[s]}
                    </option>
                  ))}
                </select>
                <GetDocumentsButton
                  matchId={m.id}
                  hasDocuments={m.has_documents}
                  variant="secondary"
                  idleLabel="Prepare application materials"
                  readyLabel="View application materials"
                  onError={setError}
                />
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
