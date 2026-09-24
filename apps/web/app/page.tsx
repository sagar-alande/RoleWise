"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Button, Card, ErrorNote, SectionEyebrow, StepBadge } from "@/components/ui";
import { api, waitForRun, type Fact, type FactKind, type Preferences, type Resume } from "@/lib/api";

const KINDS: FactKind[] = ["skill", "role", "project", "education", "certification", "achievement"];
const YEARS_KINDS: FactKind[] = ["skill", "role"];
const KIND_LABELS: Record<FactKind, string> = {
  skill: "Skills",
  role: "Experience",
  project: "Projects",
  education: "Education",
  certification: "Certifications",
  achievement: "Achievements",
};
const split = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

export default function OnboardingPage() {
  const router = useRouter();
  const [facts, setFacts] = useState<Fact[]>([]);
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [resume, setResume] = useState<Resume | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [kind, setKind] = useState<FactKind>("skill");
  const [title, setTitle] = useState("");
  const [years, setYears] = useState("");

  const load = useCallback(async () => {
    try {
      const [f, p, r] = await Promise.all([api.listFacts(), api.getPreferences(), api.getResume()]);
      setFacts(f);
      setPrefs(p);
      setResume(r);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function upload(file: File) {
    setBusy("Reading your resume…");
    setError(null);
    try {
      const { run_id } = await api.uploadResume(file);
      const run = await waitForRun(run_id);
      if (run.status === "failed") setError(`Parsing failed: ${run.error}`);
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  async function addFact(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setError(null);
    try {
      await api.createFact({
        kind,
        title,
        details: YEARS_KINDS.includes(kind) && years ? { years: Number(years) } : {},
      });
      setTitle("");
      setYears("");
      await load();
    } catch (e) {
      setError(String(e));
    }
  }

  async function updateFactYears(id: string, nextYears: string) {
    setError(null);
    try {
      const n = nextYears.trim();
      await api.updateFact(id, { details: n ? { years: Number(n) } : {} });
      await load();
    } catch (e) {
      setError(String(e));
    }
  }

  /** Entering years on an extracted-but-unconfirmed fact is treated as confirming it. */
  async function confirmPendingWithYears(id: string, nextYears: string) {
    const n = nextYears.trim();
    if (!n) return;
    setError(null);
    try {
      await api.updateFact(id, { details: { years: Number(n) } });
      await api.verifyFact(id);
      await load();
    } catch (e) {
      setError(String(e));
    }
  }

  async function savePrefsAndSearch(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!prefs) return;
    setError(null);
    const form = new FormData(e.currentTarget);
    const next: Preferences = {
      ...prefs,
      target_titles: split(String(form.get("target_titles"))),
      locations: split(String(form.get("locations"))),
      remote_modes: form.getAll("remote_modes") as Preferences["remote_modes"],
      salary_min: form.get("salary_min") ? Number(form.get("salary_min")) : null,
      dealbreakers: split(String(form.get("dealbreakers"))),
    };
    setBusy("Saving preferences…");
    try {
      setPrefs(await api.putPreferences(next));
      await findMatches();
    } catch (e) {
      setError(String(e));
      setBusy(null);
    }
  }

  async function findMatches() {
    setError(null);
    setBusy("Searching job boards and scoring matches…");
    try {
      const { run_id } = await api.discoverMatches();
      const run = await waitForRun(run_id, 300_000);
      if (run.status === "failed") {
        setError(`Search failed: ${run.error}`);
        return;
      }
      router.push("/recommendations");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  const pending = facts.filter((f) => !f.verified);
  const verified = facts.filter((f) => f.verified);
  const verifiedByKind = KINDS.map((k) => ({ kind: k, items: verified.filter((f) => f.kind === k) })).filter(
    (g) => g.items.length > 0,
  );

  return (
    <div className="space-y-10">
      <div>
        <SectionEyebrow>Your profile</SectionEyebrow>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight text-slate-900">Let's build your profile</h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-600">
          Upload your resume, confirm what's true, and set your preferences. RoleWise only uses facts you have
          verified — nothing unverified appears in matches or documents.
        </p>
      </div>

      <ErrorNote error={error} />

      <Card>
        <div className="flex items-start gap-3">
          <StepBadge n={1} />
          <div className="min-w-0 flex-1">
            <h2 className="font-semibold text-slate-900">Resume</h2>
            <p className="text-sm text-slate-500">PDF, DOCX or TXT. You will confirm each extracted fact below.</p>
            {resume && (
              <p className="mt-3 rounded-xl bg-slate-50 px-3.5 py-2.5 text-sm text-slate-700">
                Current resume:{" "}
                <a className="font-medium text-indigo-600 hover:underline" href={resume.download_url}>
                  {resume.filename}
                </a>{" "}
                <span className="text-slate-400">(uploaded {new Date(resume.uploaded_at).toLocaleDateString()})</span>
              </p>
            )}
            <label className="mt-3 flex w-fit cursor-pointer items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50 has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-50">
              Choose file
              <input
                type="file"
                accept=".pdf,.docx,.txt"
                className="hidden"
                disabled={!!busy}
                onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
              />
            </label>
            {busy && <p className="mt-2 text-sm text-indigo-600">{busy}</p>}
          </div>
        </div>
      </Card>

      {pending.length > 0 && (
        <Card className="border-amber-200 bg-amber-50/40">
          <h2 className="font-semibold text-slate-900">Confirm extracted facts ({pending.length})</h2>
          <p className="text-sm text-slate-500">
            Add years of experience where it applies — that confirms it automatically. Otherwise, confirm manually.
          </p>
          <ul className="mt-3 divide-y divide-slate-200/70">
            {pending.map((f) => (
              <li key={f.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
                <span className="flex items-center gap-2">
                  <span className="rounded-full bg-white px-2 py-0.5 text-xs font-medium uppercase tracking-wide text-slate-500 ring-1 ring-slate-200">
                    {f.kind}
                  </span>
                  <span className="font-medium text-slate-800">{f.title}</span>
                </span>
                <span className="flex items-center gap-2">
                  {YEARS_KINDS.includes(f.kind) && (
                    <FactYears fact={f} onSave={(v) => confirmPendingWithYears(f.id, v)} />
                  )}
                  <Button onClick={() => api.verifyFact(f.id).then(load)}>Confirm</Button>
                  <Button variant="secondary" onClick={() => api.deleteFact(f.id).then(load)}>
                    Remove
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card>
        <div className="flex items-start gap-3">
          <StepBadge n={2} />
          <div className="min-w-0 flex-1">
            <h2 className="font-semibold text-slate-900">Verified career knowledge base ({verified.length})</h2>
            <form onSubmit={addFact} className="mt-3 flex flex-wrap gap-2">
              <select
                value={kind}
                onChange={(e) => setKind(e.target.value as FactKind)}
                className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-700"
              >
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {KIND_LABELS[k]}
                  </option>
                ))}
              </select>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={kind === "role" ? "Data Analyst at Acme" : "e.g. Python"}
                className="min-w-60 flex-1 rounded-lg border border-slate-200 px-3 py-1.5 text-sm placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
              />
              {YEARS_KINDS.includes(kind) && (
                <input
                  value={years}
                  onChange={(e) => setYears(e.target.value)}
                  placeholder="years"
                  type="number"
                  step="0.5"
                  min="0"
                  className="w-20 rounded-lg border border-slate-200 px-2.5 py-1.5 text-sm placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                />
              )}
              <Button type="submit">Add</Button>
            </form>

            {verifiedByKind.length === 0 ? (
              <p className="mt-4 text-sm text-slate-500">Nothing verified yet — add a skill above or confirm facts from your resume.</p>
            ) : (
              <div className="mt-5 space-y-5">
                {verifiedByKind.map(({ kind: k, items }) => (
                  <div key={k}>
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                      {KIND_LABELS[k]}
                    </h3>
                    <ul className="mt-2 divide-y divide-slate-100 rounded-xl border border-slate-100">
                      {items.map((f) => (
                        <li key={f.id} className="flex items-center justify-between gap-3 px-3.5 py-2.5 text-sm">
                          <span className="text-slate-800">{f.title}</span>
                          <span className="flex items-center gap-3">
                            {YEARS_KINDS.includes(f.kind) && (
                              <span className="flex items-center gap-1 text-xs text-slate-400">
                                <FactYears fact={f} onSave={(v) => updateFactYears(f.id, v)} /> yrs
                              </span>
                            )}
                            <button
                              className="text-slate-300 transition-colors hover:text-rose-600"
                              onClick={() => api.deleteFact(f.id).then(load)}
                              aria-label={`Remove ${f.title}`}
                            >
                              ×
                            </button>
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </Card>

      {prefs && (
        <Card>
          <div className="flex items-start gap-3">
            <StepBadge n={3} />
            <div className="min-w-0 flex-1">
              <h2 className="font-semibold text-slate-900">Job preferences</h2>
              <p className="text-sm text-slate-500">
                Saving preferences automatically searches allow-listed job boards and scores your matches.
              </p>
              <form onSubmit={savePrefsAndSearch} className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
                <Field label="Target roles (comma separated)" name="target_titles" value={prefs.target_titles.join(", ")} />
                <Field label="Locations" name="locations" value={prefs.locations.join(", ")} />
                <Field label="Minimum salary" name="salary_min" value={prefs.salary_min?.toString() ?? ""} type="number" />
                <Field label="Dealbreakers" name="dealbreakers" value={prefs.dealbreakers.join(", ")} />
                <fieldset className="flex gap-4 sm:col-span-2">
                  {(["onsite", "hybrid", "remote"] as const).map((m) => (
                    <label key={m} className="flex items-center gap-1.5 text-slate-600">
                      <input type="checkbox" name="remote_modes" value={m} defaultChecked={prefs.remote_modes.includes(m)} />
                      {m}
                    </label>
                  ))}
                </fieldset>
                <div className="sm:col-span-2">
                  <Button type="submit" disabled={!!busy}>
                    {busy ?? "Save preferences & find my matches"}
                  </Button>
                </div>
              </form>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

function Field({ label, name, value, type = "text" }: { label: string; name: string; value: string; type?: string }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-slate-500">{label}</span>
      <input
        name={name}
        defaultValue={value}
        type={type}
        className="rounded-lg border border-slate-200 px-3 py-1.5 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
      />
    </label>
  );
}

function FactYears({ fact, onSave }: { fact: Fact; onSave: (years: string) => void }) {
  const initial = typeof fact.details.years === "number" ? String(fact.details.years) : "";
  const [value, setValue] = useState(initial);
  return (
    <input
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => value !== initial && onSave(value)}
      type="number"
      step="0.5"
      min="0"
      placeholder="yrs"
      title="Years of experience"
      className="w-14 rounded-md border border-slate-200 px-1.5 py-1 text-center text-xs focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
    />
  );
}
