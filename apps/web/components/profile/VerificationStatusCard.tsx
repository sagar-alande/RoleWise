"use client";

import { Button, Card, StepBadge } from "@/components/ui";
import type { Fact, FactKind } from "@/lib/api";
import { KIND_LABELS, YEARS_KINDS } from "./constants";
import { FactYears, RoleDetails } from "./FactEditors";

export function VerificationStatusCard({
  pendingByKind,
  pendingCount,
  verifiedCount,
  onConfirm,
  onConfirmYears,
  onConfirmField,
  onConfirmHighlights,
  onRemove,
}: {
  pendingByKind: { kind: FactKind; items: Fact[] }[];
  pendingCount: number;
  verifiedCount: number;
  onConfirm: (id: string) => void;
  onConfirmYears: (id: string, years: string) => void;
  onConfirmField: (id: string, field: string, value: string) => void;
  onConfirmHighlights: (id: string, highlights: string[]) => void;
  onRemove: (id: string) => void;
}) {
  return (
    <Card id="verification-section" className="scroll-mt-24">
      <div className="flex items-start gap-3">
        <StepBadge n={2} />
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold text-slate-900">Verification Status</h2>
          <p className="mt-1 text-sm text-slate-600">
            {verifiedCount} verified fact{verifiedCount === 1 ? "" : "s"}
            {pendingCount > 0 && (
              <span className="font-medium text-amber-700"> · {pendingCount} need{pendingCount === 1 ? "s" : ""} review</span>
            )}
          </p>

          {pendingCount > 0 ? (
            <div className="mt-4 space-y-5 rounded-xl border border-amber-200 bg-amber-50/40 p-4">
              <p className="text-sm text-slate-500">
                Add years of experience where it applies — that confirms it automatically. For experience, fill in
                company, dates or bullet points if your resume was thin on detail; that confirms it too. Otherwise,
                confirm manually.
              </p>
              {pendingByKind.map(({ kind: k, items }) => (
                <div key={k}>
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-amber-700/70">
                    {KIND_LABELS[k]}
                  </h3>
                  <ul className="divide-y divide-slate-200/70">
                    {items.map((f) => (
                      <li key={f.id} className="py-2.5 text-sm">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-medium text-slate-800">{f.title}</span>
                          <span className="flex items-center gap-2">
                            {YEARS_KINDS.includes(f.kind) && (
                              <FactYears fact={f} onSave={(v) => onConfirmYears(f.id, v)} />
                            )}
                            <Button onClick={() => onConfirm(f.id)}>Confirm</Button>
                            <Button variant="secondary" onClick={() => onRemove(f.id)}>
                              Remove
                            </Button>
                          </span>
                        </div>
                        {f.kind === "role" && (
                          <RoleDetails
                            fact={f}
                            defaultOpen
                            onSaveField={(field, v) => onConfirmField(f.id, field, v)}
                            onSaveHighlights={(hs) => onConfirmHighlights(f.id, hs)}
                          />
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          ) : verifiedCount > 0 ? (
            <p className="mt-4 text-sm text-emerald-700">All extracted information has been reviewed.</p>
          ) : (
            <p className="mt-4 text-sm text-slate-500">
              Nothing to review yet — upload a resume or add a skill to get started.
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}
