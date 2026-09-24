"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { Card, ErrorNote, ScoreBadge, SectionEyebrow, StatusPill } from "@/components/ui";
import { api, type Match } from "@/lib/api";

const COMPONENT_LABELS: Record<string, string> = {
  required: "Required skills",
  experience: "Experience",
  preferred: "Preferred skills",
  domain: "Domain",
  education: "Education",
  preferences: "Your preferences",
};

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
            <a className="text-sm text-indigo-600 underline" href={job.url} target="_blank" rel="noreferrer">
              View posting
            </a>
          )}
        </div>
        <ScoreBadge score={match.score} />
      </div>

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
        <ul className="mt-2 divide-y divide-slate-100 text-sm">
          {breakdown.requirements.map((r) => (
            <li key={r.requirement_id} className="flex items-center justify-between gap-3 py-2">
              <div>
                <span className="text-slate-800">{r.text}</span>
                <span className="ml-2 text-xs text-slate-500">{r.kind.replace("_", " ")}</span>
                {r.fact_title && <p className="text-xs text-slate-500">Supported by: {r.fact_title}</p>}
              </div>
              <StatusPill status={r.status} />
            </li>
          ))}
        </ul>
      </Card>

      {gaps && gaps.recommendations.length > 0 && (
        <Card>
          <h2 className="font-semibold text-slate-900">Gap analysis</h2>
          <List title="" items={gaps.recommendations.map((r) => r.text)} />
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
