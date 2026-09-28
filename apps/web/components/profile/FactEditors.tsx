"use client";

import { useState } from "react";
import { Button } from "@/components/ui";
import type { Fact } from "@/lib/api";

export function RoleDetails({
  fact,
  onSaveField,
  onSaveHighlights,
  defaultOpen = false,
}: {
  fact: Fact;
  onSaveField: (field: string, value: string) => void;
  onSaveHighlights: (highlights: string[]) => void;
  defaultOpen?: boolean;
}) {
  const highlights: string[] = Array.isArray(fact.details.highlights) ? fact.details.highlights : [];
  const company = typeof fact.details.company === "string" ? fact.details.company : "";
  const start = typeof fact.details.start === "string" ? fact.details.start : "";
  const end = typeof fact.details.end === "string" ? fact.details.end : "";
  const hasDetail = highlights.length > 0 || !!company || !!start || !!end;
  const [open, setOpen] = useState(hasDetail || defaultOpen);
  const [draft, setDraft] = useState("");

  function addBullet() {
    const v = draft.trim();
    if (!v) return;
    onSaveHighlights([...highlights, v]);
    setDraft("");
  }

  return (
    <div className="mt-1.5">
      <button type="button" onClick={() => setOpen((o) => !o)} className="text-xs font-medium text-indigo-600 hover:underline">
        {hasDetail
          ? `${company ? "Company set" : "No company"} · ${highlights.length} bullet${highlights.length === 1 ? "" : "s"}`
          : "+ Add company, dates & bullet points"}
      </button>
      {open && (
        <div className="mt-2 space-y-2.5 rounded-lg bg-slate-50 p-2.5">
          <div className="grid grid-cols-3 gap-1.5">
            <input
              defaultValue={company}
              onBlur={(e) => e.target.value !== company && onSaveField("company", e.target.value)}
              placeholder="Company"
              className="col-span-1 rounded border border-slate-200 px-2 py-1 text-xs focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
            />
            <input
              defaultValue={start}
              onBlur={(e) => e.target.value !== start && onSaveField("start", e.target.value)}
              placeholder="Start (2021 or 2021-03)"
              className="rounded border border-slate-200 px-2 py-1 text-xs focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
            />
            <input
              defaultValue={end}
              onBlur={(e) => e.target.value !== end && onSaveField("end", e.target.value)}
              placeholder="End (or Present)"
              className="rounded border border-slate-200 px-2 py-1 text-xs focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
            />
          </div>
          {highlights.map((h, i) => (
            <div key={i} className="flex items-start gap-1.5 text-xs text-slate-600">
              <span className="mt-0.5 text-slate-400">•</span>
              <span className="flex-1">{h}</span>
              <button
                type="button"
                onClick={() => onSaveHighlights(highlights.filter((_, idx) => idx !== i))}
                className="text-slate-300 hover:text-rose-600"
                aria-label="Remove bullet"
              >
                ×
              </button>
            </div>
          ))}
          <div className="flex gap-1.5">
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addBullet();
                }
              }}
              placeholder="e.g. Built ETL pipelines processing 50M records daily"
              className="flex-1 rounded border border-slate-200 px-2 py-1 text-xs focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
            />
            <Button type="button" variant="secondary" onClick={addBullet} className="px-2 py-1 text-xs">
              Add
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export function FactYears({ fact, onSave }: { fact: Fact; onSave: (years: string) => void }) {
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
