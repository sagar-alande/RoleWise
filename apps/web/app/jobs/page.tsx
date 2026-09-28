"use client";

import { useEffect, useState } from "react";
import { Button, Card, ErrorNote, SectionEyebrow } from "@/components/ui";
import { api, waitForRun, type Job } from "@/lib/api";

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const load = () => api.listJobs().then(setJobs).catch((e) => setError(String(e)));
  useEffect(() => {
    void load();
  }, []);

  /** Returns whether the task completed successfully, so a caller can decide whether it's safe to
   * clear the form - a validation or task failure must never wipe out what the user typed. */
  async function run(label: string, start: () => Promise<{ run_id: string }>): Promise<boolean> {
    setStatus(label);
    setError(null);
    try {
      const r = await waitForRun((await start()).run_id, 300_000);
      if (r.status === "failed") {
        setError(`Task failed: ${r.error}`);
        return false;
      }
      await load();
      return true;
    } catch (e) {
      setError(String(e));
      return false;
    } finally {
      setStatus(null);
    }
  }

  async function paste(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const form = e.currentTarget;
    const ok = await run("Analyzing job requirements…", () =>
      api.pasteJob({
        company: String(f.get("company")),
        title: String(f.get("title")),
        location: String(f.get("location")) || undefined,
        remote_mode: String(f.get("remote_mode")) || undefined,
        description: String(f.get("description")),
      }),
    );
    if (ok) form.reset();
  }

  async function greenhouse(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    await run("Importing jobs from Greenhouse…", () =>
      api.ingestGreenhouse(String(f.get("board")).trim().toLowerCase(), String(f.get("company")) || undefined),
    );
  }

  async function fromUrl(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const form = e.currentTarget;
    const ok = await run("Fetching the posting…", () => api.ingestFromUrl(String(f.get("url")).trim()));
    if (ok) form.reset();
  }

  return (
    <div className="space-y-6">
      <div>
        <SectionEyebrow>Sources</SectionEyebrow>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight text-slate-900">Add jobs</h1>
        <p className="mt-1 text-sm text-slate-600">
          RoleWise only uses permitted sources: jobs you paste and public employer job boards.
        </p>
      </div>

      <ErrorNote error={error} />
      {status && <p className="text-sm text-indigo-600">{status}</p>}

      <Card>
        <h2 className="font-semibold text-slate-900">Paste a job URL</h2>
        <p className="text-sm text-slate-500">
          Fastest option when it works. Fetches the posting directly from Greenhouse, Lever or Ashby's
          own public listing — no copy-pasting the description. Any other site isn't supported; paste
          the description below instead.
        </p>
        <form onSubmit={fromUrl} className="mt-3 flex gap-2 text-sm">
          <input name="url" type="url" required placeholder="https://job-boards.greenhouse.io/acme/jobs/12345"
            className="flex-1 rounded-lg border border-slate-200 px-3 py-1.5 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100" />
          <Button type="submit" disabled={!!status}>Fetch job</Button>
        </form>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <h2 className="font-semibold text-slate-900">Paste a job description</h2>
          <form onSubmit={paste} className="mt-3 space-y-2 text-sm">
            <input name="company" required placeholder="Company"
              className="w-full rounded-lg border border-slate-200 px-3 py-1.5 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100" />
            <input name="title" required placeholder="Job title"
              className="w-full rounded-lg border border-slate-200 px-3 py-1.5 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100" />
            <div className="flex gap-2">
              <input name="location" placeholder="Location"
                className="flex-1 rounded-lg border border-slate-200 px-3 py-1.5 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100" />
              <select name="remote_mode" className="rounded-lg border border-slate-200 px-2 text-slate-700">
                <option value="">Work mode</option>
                <option value="onsite">onsite</option>
                <option value="hybrid">hybrid</option>
                <option value="remote">remote</option>
              </select>
            </div>
            <textarea name="description" required minLength={50} rows={8} placeholder="Full job description"
              className="w-full rounded-lg border border-slate-200 px-3 py-1.5 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100" />
            <Button type="submit" disabled={!!status}>Add job</Button>
          </form>
        </Card>

        <Card>
          <h2 className="font-semibold text-slate-900">Import a Greenhouse job board</h2>
          <p className="text-sm text-slate-500">
            Use the board token from a company careers URL, for example boards.greenhouse.io/<b>token</b>.
          </p>
          <form onSubmit={greenhouse} className="mt-3 space-y-2 text-sm">
            <input name="board" required placeholder="Board token"
              className="w-full rounded-lg border border-slate-200 px-3 py-1.5 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100" />
            <input name="company" placeholder="Company name (optional)"
              className="w-full rounded-lg border border-slate-200 px-3 py-1.5 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100" />
            <Button type="submit" disabled={!!status}>Import jobs</Button>
          </form>
        </Card>
      </div>

      <Card>
        <h2 className="font-semibold text-slate-900">Jobs in RoleWise ({jobs.length})</h2>
        <ul className="mt-2 max-h-96 divide-y divide-slate-100 overflow-y-auto text-sm">
          {jobs.map((j) => (
            <li key={j.id} className="py-2">
              <span className="font-medium text-slate-800">{j.title}</span>
              <span className="text-slate-500"> · {j.company}{j.location ? ` · ${j.location}` : ""}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
