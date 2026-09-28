"use client";

import { useState } from "react";
import { Button, Card, StepBadge } from "@/components/ui";
import type { Fact, FactKind } from "@/lib/api";
import { KINDS, KIND_LABELS, YEARS_KINDS } from "./constants";
import { FactYears, RoleDetails } from "./FactEditors";

export function CareerInformationCard({
  verifiedByKind,
  onAdd,
  onUpdateYears,
  onUpdateField,
  onUpdateHighlights,
  onRemove,
}: {
  verifiedByKind: { kind: FactKind; items: Fact[] }[];
  onAdd: (kind: FactKind, title: string, details: Record<string, unknown>) => Promise<void>;
  onUpdateYears: (id: string, years: string) => void;
  onUpdateField: (id: string, field: string, value: string) => void;
  onUpdateHighlights: (id: string, highlights: string[]) => void;
  onRemove: (id: string) => void;
}) {
  const [addOpen, setAddOpen] = useState(false);
  const [kind, setKind] = useState<FactKind>("skill");
  const [title, setTitle] = useState("");
  const [years, setYears] = useState("");
  const [company, setCompany] = useState("");

  async function submitAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    const details: Record<string, unknown> = {};
    if (YEARS_KINDS.includes(kind) && years) details.years = Number(years);
    if (kind === "role" && company.trim()) details.company = company.trim();
    await onAdd(kind, title, details);
    setTitle("");
    setYears("");
    setCompany("");
  }

  const verifiedCount = verifiedByKind.reduce((n, g) => n + g.items.length, 0);

  return (
    <Card id="career-section" className="scroll-mt-24">
      <div className="flex items-start gap-3">
        <StepBadge n={3} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold text-slate-900">Career Information ({verifiedCount})</h2>
            <button
              type="button"
              onClick={() => setAddOpen((o) => !o)}
              className="text-sm font-medium text-indigo-600 hover:underline"
            >
              {addOpen ? "Cancel" : "+ Add career information"}
            </button>
          </div>

          {addOpen && (
            <form onSubmit={submitAdd} className="mt-3 flex flex-wrap gap-2 rounded-xl bg-slate-50 p-3">
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
              {kind === "role" && (
                <input
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                  placeholder="Company"
                  className="min-w-40 rounded-lg border border-slate-200 px-3 py-1.5 text-sm placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                />
              )}
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
              {kind === "role" && (
                <p className="w-full text-xs text-slate-400">
                  Add years, company and — once added — bullet points and dates. Shown on your resume exactly as
                  entered, never invented.
                </p>
              )}
            </form>
          )}

          {verifiedByKind.length === 0 ? (
            <p className="mt-4 text-sm text-slate-500">
              Nothing verified yet — add a skill above or confirm facts from your resume.
            </p>
          ) : (
            <div className="mt-5 space-y-5">
              {verifiedByKind.map(({ kind: k, items }) => (
                <div key={k}>
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    {KIND_LABELS[k]}
                  </h3>
                  <ul className="divide-y divide-slate-100 rounded-xl border border-slate-100">
                    {items.map((f) => (
                      <li key={f.id} className="px-3.5 py-2.5 text-sm">
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-slate-800">
                            {f.title}
                            {f.kind === "role" && typeof f.details.company === "string" && f.details.company && (
                              <span className="text-slate-400"> · {f.details.company}</span>
                            )}
                          </span>
                          <span className="flex items-center gap-3">
                            {YEARS_KINDS.includes(f.kind) && (
                              <span className="flex items-center gap-1 text-xs text-slate-400">
                                <FactYears fact={f} onSave={(v) => onUpdateYears(f.id, v)} /> yrs
                              </span>
                            )}
                            <button
                              className="text-slate-300 transition-colors hover:text-rose-600"
                              onClick={() => onRemove(f.id)}
                              aria-label={`Remove ${f.title}`}
                            >
                              ×
                            </button>
                          </span>
                        </div>
                        {f.kind === "role" && (
                          <RoleDetails
                            fact={f}
                            onSaveField={(field, v) => onUpdateField(f.id, field, v)}
                            onSaveHighlights={(hs) => onUpdateHighlights(f.id, hs)}
                          />
                        )}
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
  );
}
