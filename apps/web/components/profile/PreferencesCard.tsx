"use client";

import { useState } from "react";
import { Button, Card, Field, StepBadge } from "@/components/ui";
import type { Preferences } from "@/lib/api";
import { archetypeNames, FITS, TIERS } from "./constants";

/** How many Advanced preferences are actively narrowing or ranking results right now - shown even
 * while the section is collapsed, since these can silently remove jobs from consideration otherwise. */
function activeAdvancedCount(prefs: Preferences): number {
  return [
    (prefs.archetypes ?? []).length > 0,
    (prefs.excluded_title_keywords ?? []).length > 0,
    prefs.dealbreakers.length > 0,
    (prefs.skip_tiers ?? []).length > 0,
    prefs.salary_min != null,
  ].filter(Boolean).length;
}

export function PreferencesCard({
  prefs,
  busy,
  onSave,
}: {
  prefs: Preferences;
  busy: string | null;
  onSave: (e: React.FormEvent<HTMLFormElement>) => void;
}) {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const initialSponsorship = prefs.needs_sponsorship === true ? "required" : prefs.needs_sponsorship === false ? "not_required" : "";
  const [sponsorship, setSponsorship] = useState(initialSponsorship);
  const advancedCount = activeAdvancedCount(prefs);

  return (
    <Card id="preferences-section" className="scroll-mt-24">
      <div className="flex items-start gap-3">
        <StepBadge n={4} />
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold text-slate-900">Job Preferences</h2>
          <p className="text-sm text-slate-500">
            Saving preferences automatically searches allow-listed job boards and scores your matches.
          </p>

          <form onSubmit={onSave} className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
            <div className="sm:col-span-2">
              <Field
                label="Desired roles (comma separated, leave empty for all)"
                name="target_titles"
                value={prefs.target_titles.join(", ")}
              />
              <p className="mt-1 text-xs text-slate-400">RoleWise uses these titles to focus the jobs it evaluates.</p>
            </div>

            <Field label="Preferred locations" name="locations" value={prefs.locations.join(", ")} />

            <fieldset className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-slate-500">Work arrangement</span>
              <div className="flex gap-4 pt-1.5">
                {(["onsite", "hybrid", "remote"] as const).map((m) => (
                  <label key={m} className="flex items-center gap-1.5 text-slate-600">
                    <input type="checkbox" name="remote_modes" value={m} defaultChecked={prefs.remote_modes.includes(m)} />
                    {m === "onsite" ? "On-site" : m === "hybrid" ? "Hybrid" : "Remote"}
                  </label>
                ))}
              </div>
            </fieldset>

            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-slate-500">Seniority</span>
              <select
                name="seniority"
                defaultValue={prefs.seniority ?? ""}
                className="rounded-lg border border-slate-200 bg-white px-3 py-1.5"
              >
                <option value="">Work it out from my experience</option>
                {TIERS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-slate-500">Visa sponsorship</span>
              <select
                name="sponsorship"
                value={sponsorship}
                onChange={(e) => setSponsorship(e.target.value)}
                className="rounded-lg border border-slate-200 bg-white px-3 py-1.5"
              >
                <option value="">No preference</option>
                <option value="required">Sponsorship required</option>
                <option value="not_required">Sponsorship not required</option>
              </select>
            </label>

            <div className={sponsorship === "required" ? "" : "hidden"}>
              <Field
                label="Countries where you can work without sponsorship"
                name="authorized_in"
                value={(prefs.authorized_in ?? []).join(", ")}
              />
            </div>

            {/* ---------------------------------------------------------------- Advanced */}
            <div className="sm:col-span-2 border-t border-slate-100 pt-4">
              <div className="flex w-full items-center justify-between gap-3">
                <span className="flex items-center">
                  <button
                    type="button"
                    onClick={() => setAdvancedOpen((o) => !o)}
                    className="text-sm font-medium text-slate-700 hover:underline"
                  >
                    Advanced
                  </button>
                  {advancedCount > 0 && (
                    <button
                      type="button"
                      onClick={() => setAdvancedOpen(true)}
                      className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 hover:bg-amber-200"
                    >
                      {advancedCount} advanced preference{advancedCount === 1 ? "" : "s"} active
                    </button>
                  )}
                </span>
                <button
                  type="button"
                  onClick={() => setAdvancedOpen((o) => !o)}
                  className="text-sm text-slate-400 hover:text-slate-600"
                >
                  {advancedOpen ? "Hide" : "Show"}
                </button>
              </div>
              <p className="mt-1 text-xs text-slate-500">These settings can further filter or rank job results.</p>

              <div className={advancedOpen ? "mt-4 grid gap-4 sm:grid-cols-2" : "hidden"}>
                <div className="grid gap-4 sm:col-span-2 sm:grid-cols-3">
                  {FITS.map(({ fit, label, hint }) => (
                    <label key={fit} className="flex flex-col gap-1.5">
                      <span className="text-xs font-medium text-slate-500">{label}</span>
                      <input
                        name={`archetype_${fit}`}
                        defaultValue={archetypeNames(prefs.archetypes ?? [], fit)}
                        placeholder={hint}
                        className="rounded-lg border border-slate-200 px-3 py-1.5 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                      />
                    </label>
                  ))}
                </div>

                <div>
                  <Field label="Excluded titles" name="excluded_title_keywords" value={(prefs.excluded_title_keywords ?? []).join(", ")} />
                  <p className="mt-1 text-xs text-slate-400">Jobs with these words in the title will not be shown.</p>
                </div>

                <div>
                  <Field label="Dealbreakers" name="dealbreakers" value={prefs.dealbreakers.join(", ")} />
                  <p className="mt-1 text-xs text-slate-400">Jobs containing these terms may be filtered out.</p>
                </div>

                <fieldset className="flex flex-col gap-1.5 sm:col-span-2">
                  <span className="text-xs font-medium text-slate-500">Hidden levels</span>
                  <div className="flex flex-wrap gap-4 pt-1.5">
                    {TIERS.map((t) => (
                      <label key={t} className="flex items-center gap-1.5 text-slate-600">
                        <input type="checkbox" name="skip_tiers" value={t} defaultChecked={(prefs.skip_tiers ?? []).includes(t)} />
                        {t}
                      </label>
                    ))}
                  </div>
                  <p className="text-xs text-slate-400">Jobs at these levels will not be shown.</p>
                </fieldset>

                <div>
                  <Field label="Minimum salary" name="salary_min" value={prefs.salary_min?.toString() ?? ""} type="number" />
                  <p className="mt-1 text-xs text-slate-400">Used only when salary information is available in the job posting.</p>
                </div>
              </div>
            </div>

            <div className="sm:col-span-2">
              <Button type="submit" disabled={!!busy}>
                {busy ?? "Save preferences & find my matches"}
              </Button>
            </div>
          </form>
        </div>
      </div>
    </Card>
  );
}
