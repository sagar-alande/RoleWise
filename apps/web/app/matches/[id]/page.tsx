"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { AlignmentLabel, Card, ErrorNote, ImportancePill, ListingStatusLabel, ScoreBadge, SectionEyebrow, SignalList, StatusPill } from "@/components/ui";
import { GetDocumentsButton } from "@/components/GetDocumentsButton";
import { api, type Match, type RequirementResult } from "@/lib/api";

const COMPONENT_LABELS: Record<string, string> = {
  required: "Required skills",
  experience: "Experience",
  preferred: "Preferred skills",
  domain: "Domain",
  education: "Education",
  preferences: "Your preferences",
  north_star: "Target role fit",
  level: "Seniority fit",
};

const WORK_AUTH_LABELS: Record<string, string> = {
  sponsors: "Offers sponsorship",
  not_needed: "Not needed",
  unstated: "Not stated (neutral)",
  no_sponsorship: "Will not sponsor",
};

const ROW_BUDGET = 12;

/** career-ops Block B budget: at most 12 rows, but never hide a critical or high requirement. */
function budgetRows(rows: RequirementResult[]): { shown: RequirementResult[]; hidden: number } {
  const must = rows.filter((r) => r.importance === "critical" || r.importance === "high");
  const rest = rows.filter((r) => r.importance !== "critical" && r.importance !== "high");
  const shown = [...must, ...rest.slice(0, Math.max(0, ROW_BUDGET - must.length))];
  return { shown, hidden: rows.length - shown.length };
}

export default function MatchDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [match, setMatch] = useState<Match | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getMatch(id).then(setMatch).catch((e) => setError(String(e)));
  }, [id]);

  if (error) return <ErrorNote error={error} />;
  if (!match) return <p className="text-slate-500">Loading…</p>;

  const { job, breakdown, explanation, gaps } = match;

  return (
    <div className="space-y-6">
      <Link href="/recommendations" className="text-sm text-slate-500 hover:text-indigo-600">
        ← Back to recommendations
      </Link>

      <div className="flex items-start justify-between gap-4">
        <div>
          <SectionEyebrow>{job.company}</SectionEyebrow>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-slate-900">{job.title}</h1>
          <p className="mt-1 text-slate-600">{job.location}</p>
          {job.url && (
            <a
              className={job.listing_status === "closed"
                ? "text-sm text-slate-500 underline"
                : "text-sm text-indigo-600 underline"}
              href={job.url}
              target="_blank"
              rel="noreferrer"
            >
              {job.listing_status === "closed" ? "View original posting (may no longer be available)" : "View posting"}
            </a>
          )}
          {job.last_checked_at && (
            <p className="mt-1 text-xs text-slate-400">
              Last verified {new Date(job.last_checked_at).toLocaleDateString()}
            </p>
          )}
          {job.listing_status === "closed" && (
            <p className="mt-2 max-w-md rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-800 ring-1 ring-rose-200">
              This job posting appears to be closed. Your previous match analysis is preserved for reference.
            </p>
          )}
        </div>
        <div className="flex flex-col items-end gap-2">
          <ScoreBadge score={match.score} />
          <AlignmentLabel score={match.score} />
          <ListingStatusLabel status={job.listing_status} />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {match.status !== "saved" && !match.has_documents && (
          <button
            className="rounded-lg bg-indigo-600 px-3.5 py-2 text-sm font-medium text-white shadow-sm shadow-indigo-600/20 hover:bg-indigo-700"
            onClick={() => api.setMatchStatus(match.id, "saved").then(() => api.getMatch(id).then(setMatch))}
          >
            Save to my jobs
          </button>
        )}
        {match.status === "saved" && <span className="text-sm text-emerald-700">Saved to My jobs</span>}
        <GetDocumentsButton
          matchId={match.id}
          hasDocuments={match.has_documents}
          variant="secondary"
          idleLabel="Prepare application materials"
          readyLabel="View application materials"
          onError={setError}
        />
      </div>

      <SignalList hardStops={breakdown.hard_stops} flags={breakdown.flags} />

      {(breakdown.archetype || breakdown.level || breakdown.work_auth) && (
        <Card>
          <h2 className="font-semibold text-slate-900">Role summary</h2>
          <dl className="mt-2 grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-3">
            {breakdown.archetype && (
              <div>
                <dt className="text-xs text-slate-500">Target role fit</dt>
                <dd className="text-slate-800">
                  {breakdown.archetype.name ? `${breakdown.archetype.name} (${breakdown.archetype.fit})` : "None of your target roles"}
                </dd>
              </div>
            )}
            {breakdown.level && (
              <div>
                <dt className="text-xs text-slate-500">Seniority</dt>
                <dd className="text-slate-800">
                  Role is {breakdown.level.job_tier}, you are {breakdown.level.candidate_tier}
                </dd>
              </div>
            )}
            {breakdown.work_auth && (
              <div>
                <dt className="text-xs text-slate-500">Visa sponsorship</dt>
                <dd className="text-slate-800">{WORK_AUTH_LABELS[breakdown.work_auth.tier] ?? breakdown.work_auth.tier}</dd>
              </div>
            )}
          </dl>
        </Card>
      )}

      {explanation && (
        <Card>
          <h2 className="font-semibold text-slate-900">Why this matches</h2>
          <p className="mt-1 text-sm text-slate-700">{explanation.summary}</p>
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            <List title="Strengths" items={explanation.strengths} />
            <List title="Gaps" items={explanation.gaps} />
          </div>
          {explanation.resume_tips.length > 0 && <List title="Resume tips" items={explanation.resume_tips} />}
        </Card>
      )}

      <Card>
        <h2 className="font-semibold text-slate-900">Score breakdown</h2>
        <table className="mt-2 w-full text-sm">
          <thead className="text-left text-slate-500">
            <tr>
              <th className="py-1 font-normal">Component</th>
              <th className="py-1 font-normal">Fit</th>
              <th className="py-1 font-normal">Weight</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(breakdown.weights_used).map(([key, weight]) => (
              <tr key={key} className="border-t border-slate-100">
                <td className="py-1.5">{COMPONENT_LABELS[key] ?? key}</td>
                <td className="py-1.5 tabular-nums">{Math.round((breakdown.components[key] ?? 0) * 100)}%</td>
                <td className="py-1.5 tabular-nums">{Math.round(weight * 100)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card>
        <h2 className="font-semibold text-slate-900">Requirements</h2>
        <p className="text-xs text-slate-500">
          Most important first, gaps before matches. Importance comes from the posting alone, never from your profile.
        </p>
        <ul className="mt-2 divide-y divide-slate-100 text-sm">
          {budgetRows(breakdown.requirements).shown.map((r) => (
            <li key={r.requirement_id} className="flex items-start justify-between gap-3 py-2.5">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <ImportancePill importance={r.importance ?? "meaningful"} />
                  <span className="font-medium text-slate-800">{r.text}</span>
                  <span className="text-xs text-slate-400">{r.evidence_tier}</span>
                </div>
                {r.jd_signal && r.evidence_tier === "stated" && (
                  <p className="mt-1 text-xs italic text-slate-500">Posting: “{r.jd_signal}”</p>
                )}
                {r.fact_title && <p className="mt-0.5 text-xs text-emerald-700">Your evidence: {r.fact_title}</p>}
                {r.years_evidence === "known" && (
                  <p className="mt-0.5 text-xs text-emerald-700">
                    Verified profile supports approximately {r.known_years} years of relevant experience.
                  </p>
                )}
                {r.years_evidence === "unknown" && (
                  <p className="mt-0.5 text-xs text-amber-700">
                    Relevant experience is verified, but the exact duration could not be established
                    from the available profile information.
                  </p>
                )}
                {r.status === "missing" && (
                  <p className="mt-0.5 text-xs text-rose-600">
                    This requirement does not appear in your verified career profile.
                  </p>
                )}
              </div>
              <StatusPill status={r.status} />
            </li>
          ))}
        </ul>
        {budgetRows(breakdown.requirements).hidden > 0 && (
          <p className="mt-2 text-xs text-slate-400">
            +{budgetRows(breakdown.requirements).hidden} lower-importance requirements not listed
          </p>
        )}
      </Card>

      {gaps && gaps.underrepresented.length > 0 && (
        <Card>
          <h2 className="font-semibold text-slate-900">Resume visibility opportunities</h2>
          <p className="text-xs text-slate-500">
            Verified experience that doesn't clearly show up in your uploaded resume yet.
          </p>
          <ul className="mt-2 divide-y divide-slate-100 text-sm">
            {gaps.underrepresented.map((g) => (
              <li key={g.requirement_id} className="py-2.5">
                <p className="font-medium text-slate-800">{g.fact_title ?? g.text}</p>
                <p className="mt-0.5 text-slate-600">
                  You have verified this experience, but it is not clearly represented in your uploaded resume.
                </p>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {gaps && gaps.recommendations.length > 0 && (
        <Card>
          <h2 className="font-semibold text-slate-900">Gap analysis</h2>
          <ul className="mt-2 space-y-3 text-sm">
            {gaps.recommendations.map((r, i) =>
              r.type === "interview_risk" ? (
                <li key={i} className="rounded-xl border border-slate-200 px-3.5 py-2.5">
                  <div className="flex items-center gap-2">
                    {r.importance && <ImportancePill importance={r.importance} />}
                    <span className="font-medium text-slate-800">{r.requirement}</span>
                  </div>
                  <p className="mt-1 text-slate-700"><span className="font-medium">Risk: </span>{r.risk}</p>
                  <p className="mt-0.5 text-slate-700"><span className="font-medium">Plan: </span>{r.mitigation}</p>
                </li>
              ) : (
                <li key={i} className="px-1 text-slate-700">• {r.text}</li>
              ),
            )}
          </ul>
        </Card>
      )}
    </div>
  );
}

function List({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="mt-2">
      {title && <h3 className="text-sm font-medium text-slate-700">{title}</h3>}
      <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-700">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
