"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { AlignmentLabel, Button, Card, ErrorNote, ImportancePill, ScoreBadge, SectionEyebrow } from "@/components/ui";
import {
  api,
  waitForRun,
  type CoverContent,
  type GeneratedDocument,
  type Match,
  type MatchDocuments,
  type ResumeContent,
  type Tone,
} from "@/lib/api";

type Tab = "resume" | "cover_letter";

const TONES: { value: Tone; label: string }[] = [
  { value: "mirror", label: "Match the posting" },
  { value: "formal", label: "Formal" },
  { value: "direct", label: "Direct" },
  { value: "conversational", label: "Conversational" },
];

const COVERAGE_LABEL = {
  shown: "In your documents",
  could_add: "You have it, not shown",
  not_in_profile: "Not in your profile, not added",
};

export default function DocumentsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [match, setMatch] = useState<Match | null>(null);
  const [docs, setDocs] = useState<MatchDocuments | null>(null);
  const [shown, setShown] = useState<{ resume?: GeneratedDocument; cover_letter?: GeneratedDocument }>({});
  const [tab, setTab] = useState<Tab>("resume");
  const [tone, setTone] = useState<Tone>("mirror");
  const [angle, setAngle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [m, d] = await Promise.all([api.getMatch(id), api.getDocuments(id)]);
      setMatch(m);
      setDocs(d);
      setShown({ resume: d.resume ?? undefined, cover_letter: d.cover_letter ?? undefined });
      const meta = (d.cover_letter ?? d.resume)?.content.meta;
      if (meta) {
        setTone(meta.tone ?? "mirror");
        setAngle(meta.angle ?? "");
      }
    } catch (e) {
      setError(String(e));
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      const { run_id } = await api.generateDocuments(id, { tone, angle: angle.trim() || undefined });
      const run = await waitForRun(run_id, 300_000);
      if (run.status === "failed") setError(`Could not generate documents: ${run.error}`);
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function pickVersion(docId: string) {
    const d = await api.getDocument(docId);
    setShown((s) => ({ ...s, [d.kind]: d }));
    setTab(d.kind);
  }

  if (error && !match) return <ErrorNote error={error} />;
  if (!match || !docs) return <p className="text-slate-500">Loading…</p>;

  const current = shown[tab];
  const versions = docs.history.filter((h) => h.kind === tab);
  const fileBase = [current?.content.header.full_name || "document", match.job.company, tab.replace("_", "-")]
    .join("-")
    .replace(/[^A-Za-z0-9-]+/g, "-");

  return (
    <div className="space-y-6">
      <div className="no-print">
        <Link href={`/matches/${id}`} className="text-sm text-slate-500 hover:text-indigo-600">
          ← Back to match
        </Link>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
          <div>
            <SectionEyebrow>Application documents</SectionEyebrow>
            <h1 className="mt-1 text-3xl font-semibold tracking-tight text-slate-900">{match.job.title}</h1>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-slate-600">
              {match.job.company}
              <ScoreBadge score={match.score} />
              <AlignmentLabel score={match.score} />
              <span className="text-sm text-emerald-700">Saved to My jobs</span>
            </p>
          </div>
        </div>
      </div>

      <div className="no-print">
        <ErrorNote error={error} />
      </div>

      {!docs.resume && !docs.cover_letter ? (
        <Card className="no-print">
          <p className="font-medium text-slate-800">No documents for this job yet.</p>
          <p className="mt-1 text-sm text-slate-500">
            RoleWise rewrites your resume in this job&apos;s language and drafts a cover letter, using only facts you
            have verified.
          </p>
          <div className="mt-4">
            <Button onClick={generate} disabled={busy}>
              {busy ? "Writing your documents…" : "Generate resume and cover letter"}
            </Button>
          </div>
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
          <div className="min-w-0 space-y-3">
            <div className="no-print flex flex-wrap items-center gap-2">
              {(["resume", "cover_letter"] as Tab[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`rounded-lg px-3.5 py-2 text-sm font-medium ${
                    tab === t ? "bg-indigo-600 text-white" : "bg-white text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50"
                  }`}
                >
                  {t === "resume" ? "Tailored resume" : "Cover letter"}
                </button>
              ))}
              <span className="ml-auto flex flex-wrap gap-2">
                {current && (
                  <>
                    <Button variant="secondary" onClick={() => window.print()}>
                      Print / Save as PDF
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => api.downloadDocument(current.id, "docx", fileBase).catch((e) => setError(String(e)))}
                    >
                      Word (.docx)
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => api.downloadDocument(current.id, "md", fileBase).catch((e) => setError(String(e)))}
                    >
                      Markdown
                    </Button>
                  </>
                )}
              </span>
            </div>

            {current?.content.meta.model?.startsWith("stub") && (
              <p className="no-print rounded-xl border border-sky-200 bg-sky-50 px-3.5 py-2 text-xs text-sky-800">
                Generated offline. It only selects and orders your verified facts. Turn on Bedrock to have the AI
                reword them in this job&apos;s language.
              </p>
            )}

            <div className="print-sheet mx-auto max-w-[8.5in] rounded-2xl border border-slate-200 bg-white p-8 shadow-sm sm:p-10">
              {current ? (
                tab === "resume" ? (
                  <ResumeSheet c={current.content as ResumeContent} />
                ) : (
                  <CoverSheet c={current.content as CoverContent} />
                )
              ) : (
                <p className="text-sm text-slate-500">Not generated yet.</p>
              )}
            </div>
          </div>

          <aside className="no-print space-y-4">
            <Card>
              <h2 className="font-semibold text-slate-900">Regenerate</h2>
              <p className="text-xs text-slate-500">Each run saves a new version. Earlier versions stay here.</p>
              <label className="mt-3 flex flex-col gap-1.5 text-sm">
                <span className="text-xs font-medium text-slate-500">Cover letter tone</span>
                <select
                  value={tone}
                  onChange={(e) => setTone(e.target.value as Tone)}
                  className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5"
                >
                  {TONES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="mt-3 flex flex-col gap-1.5 text-sm">
                <span className="text-xs font-medium text-slate-500">Why this role, in your words (optional)</span>
                <textarea
                  value={angle}
                  onChange={(e) => setAngle(e.target.value)}
                  rows={3}
                  maxLength={500}
                  placeholder="e.g. I want to work on healthcare data at scale."
                  className="rounded-lg border border-slate-200 px-2.5 py-1.5"
                />
              </label>
              <Button className="mt-3 w-full" onClick={generate} disabled={busy}>
                {busy ? "Writing…" : "Regenerate both"}
              </Button>
              {versions.length > 1 && (
                <label className="mt-3 flex flex-col gap-1.5 text-sm">
                  <span className="text-xs font-medium text-slate-500">Version</span>
                  <select
                    value={current?.id}
                    onChange={(e) => pickVersion(e.target.value)}
                    className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5"
                  >
                    {versions.map((v) => (
                      <option key={v.id} value={v.id}>
                        v{v.version} · {new Date(v.created_at).toLocaleString()}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </Card>

            {current && current.content.coverage.length > 0 && (
              <Card>
                <h2 className="font-semibold text-slate-900">Job keywords</h2>
                <ul className="mt-2 space-y-1.5 text-sm">
                  {current.content.coverage.map((c) => (
                    <li key={c.text} className="flex items-start justify-between gap-2">
                      <span className="flex items-center gap-1.5">
                        <ImportancePill importance={c.importance} />
                        <span className="text-slate-800">{c.text}</span>
                      </span>
                      <span
                        className={`shrink-0 text-xs ${
                          c.state === "shown" ? "text-emerald-700" : c.state === "could_add" ? "text-amber-700" : "text-slate-400"
                        }`}
                      >
                        {COVERAGE_LABEL[c.state]}
                      </span>
                    </li>
                  ))}
                </ul>
              </Card>
            )}

            {current && (current.content.removed.length > 0 || current.content.warnings.length > 0) && (
              <Card>
                <h2 className="font-semibold text-slate-900">Fact check</h2>
                {current.content.removed.length > 0 && (
                  <>
                    <p className="mt-1 text-xs text-slate-500">
                      Removed because your verified facts don&apos;t support them:
                    </p>
                    <ul className="mt-2 space-y-2 text-xs">
                      {current.content.removed.map((r, i) => (
                        <li key={i} className="rounded-lg bg-rose-50 px-2.5 py-1.5 text-rose-800">
                          <span className="line-through">{r.text}</span>
                          <span className="block text-rose-600">{r.reason}</span>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
                {current.content.warnings.map((w, i) => (
                  <p key={i} className="mt-2 rounded-lg bg-amber-50 px-2.5 py-1.5 text-xs text-amber-800">
                    {w}
                  </p>
                ))}
              </Card>
            )}
            {current && current.content.removed.length === 0 && current.content.warnings.length === 0 && (
              <p className="px-1 text-xs text-emerald-700">Fact check passed. Every line traces to a verified fact.</p>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}

function SheetHeader({ c, subtitle }: { c: { header: ResumeContent["header"] }; subtitle?: string }) {
  return (
    <div className="border-b-2 border-indigo-600 pb-3">
      <h2 className="text-2xl font-bold tracking-tight text-slate-900">{c.header.full_name || "Your name"}</h2>
      {subtitle && <p className="text-sm font-medium text-indigo-700">{subtitle}</p>}
      <p className="mt-1 text-xs text-slate-600">{c.header.contact.join("  |  ")}</p>
      {!c.header.full_name && (
        <p className="no-print mt-1 text-xs text-amber-700">
          Add your name and contact details on your <Link className="underline" href="/">profile</Link>.
        </p>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-5">
      <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-700">{title}</h3>
      <div className="mt-1.5 text-[13px] leading-relaxed text-slate-800">{children}</div>
    </section>
  );
}

function ResumeSheet({ c }: { c: ResumeContent }) {
  return (
    <article>
      <SheetHeader c={c} subtitle={c.header.headline} />
      {c.summary.length > 0 && (
        <Section title="Professional Summary">
          <p>{c.summary.map((s) => s.text).join(" ")}</p>
        </Section>
      )}
      {c.competencies.length > 0 && (
        <Section title="Core Competencies">
          <p>{c.competencies.map((s) => s.text).join("  ·  ")}</p>
        </Section>
      )}
      {c.experience.length > 0 && (
        <Section title="Work Experience">
          {c.experience.map((r) => (
            <div key={r.fact_id} className="mt-2 first:mt-0">
              <p className="flex flex-wrap justify-between gap-2">
                <span>
                  <span className="font-semibold">{r.title}</span>
                  {r.company && <span className="text-indigo-700"> · {r.company}</span>}
                </span>
                <span className="text-xs text-slate-500">{[r.location, r.dates].filter(Boolean).join(" | ")}</span>
              </p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5">
                {r.bullets.map((b, i) => (
                  <li key={i}>{b.text}</li>
                ))}
              </ul>
            </div>
          ))}
        </Section>
      )}
      {c.projects.length > 0 && (
        <Section title="Projects">
          {c.projects.map((p) => (
            <div key={p.fact_id} className="mt-2 first:mt-0">
              <p className="font-semibold">{p.title}</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5">
                {p.bullets.map((b, i) => (
                  <li key={i}>{b.text}</li>
                ))}
              </ul>
            </div>
          ))}
        </Section>
      )}
      {c.achievements.length > 0 && (
        <Section title="Achievements">
          <ul className="list-disc space-y-0.5 pl-5">
            {c.achievements.map((a, i) => (
              <li key={i}>{a.text}</li>
            ))}
          </ul>
        </Section>
      )}
      {c.education.length > 0 && (
        <Section title="Education">
          {c.education.map((e) => (
            <p key={e.fact_id}>{e.text}</p>
          ))}
        </Section>
      )}
      {c.certifications.length > 0 && (
        <Section title="Certifications">
          {c.certifications.map((e) => (
            <p key={e.fact_id}>{e.text}</p>
          ))}
        </Section>
      )}
      {c.skills.length > 0 && (
        <Section title="Skills">
          <p>{c.skills.map((s) => s.text).join(", ")}</p>
        </Section>
      )}
    </article>
  );
}

function CoverSheet({ c }: { c: CoverContent }) {
  return (
    <article className="text-[13px] leading-relaxed text-slate-800">
      <SheetHeader c={c} />
      <p className="mt-5 font-semibold text-slate-900">{c.title}</p>
      <p className="text-slate-500">
        {c.company} · {new Date(`${c.date}T00:00:00`).toLocaleDateString()}
      </p>
      <p className="mt-5">{c.salutation}</p>
      {c.opening && <p className="mt-3">{c.opening.text}</p>}
      {c.profile && <p className="mt-3">{c.profile.text}</p>}
      {c.narrative.map((p, i) => (
        <p key={i} className="mt-3">{p}</p>
      ))}
      {c.problems && <p className="mt-3">{c.problems.text}</p>}
      {c.closing && <p className="mt-3">{c.closing.text}</p>}
      <p className="mt-6">{c.header.full_name}</p>
    </article>
  );
}
