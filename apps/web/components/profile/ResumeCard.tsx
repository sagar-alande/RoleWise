"use client";

import { useState } from "react";
import { Button, Card, StepBadge } from "@/components/ui";
import type { Resume } from "@/lib/api";

export function ResumeCard({
  resume,
  busy,
  pendingUpload,
  onChooseFile,
  onResolvePendingUpload,
  onCancelPendingUpload,
  onResetProfile,
}: {
  resume: Resume | null;
  busy: string | null;
  pendingUpload: File | null;
  onChooseFile: (file: File) => void;
  onResolvePendingUpload: (replaceExisting: boolean) => void;
  onCancelPendingUpload: () => void;
  onResetProfile: () => void;
}) {
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);

  return (
    <Card id="resume-section" className="scroll-mt-24">
      <div className="flex items-start gap-3">
        <StepBadge n={1} />
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold text-slate-900">Resume</h2>
          <p className="text-sm text-slate-500">PDF, DOCX or TXT.</p>
          {resume && (
            <p className="mt-3 rounded-xl bg-slate-50 px-3.5 py-2.5 text-sm text-slate-700">
              Current resume:{" "}
              <a className="break-all font-medium text-indigo-600 hover:underline" href={resume.download_url}>
                {resume.filename}
              </a>{" "}
              <span className="text-slate-400">(parsed {new Date(resume.uploaded_at).toLocaleDateString()})</span>
            </p>
          )}
          <label className="mt-3 flex w-fit cursor-pointer items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50 has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-50">
            {resume ? "Replace resume" : "Upload resume"}
            <input
              type="file"
              accept=".pdf,.docx,.txt"
              className="hidden"
              disabled={!!busy}
              onChange={(e) => e.target.files?.[0] && onChooseFile(e.target.files[0])}
            />
          </label>
          {pendingUpload && (
            <div className="mt-3 rounded-xl border border-indigo-200 bg-indigo-50/60 px-3.5 py-3 text-sm">
              <p className="font-medium text-slate-800">
                You already have a resume on file. What should {pendingUpload.name} do with your existing
                profile data?
              </p>
              <div className="mt-2.5 flex flex-col gap-2.5">
                <div className="flex flex-wrap items-center gap-2.5">
                  <Button onClick={() => onResolvePendingUpload(false)}>Merge with existing profile</Button>
                  <span className="text-xs text-slate-500">
                    Keep your current career information and add new facts found in this resume. Likely
                    duplicates will be skipped.
                  </span>
                </div>
                <div className="flex flex-wrap items-center gap-2.5">
                  <Button variant="secondary" onClick={() => onResolvePendingUpload(true)}>
                    Replace resume data
                  </Button>
                  <span className="text-xs text-slate-500">
                    Remove career information extracted from your previous resume and analyze the new
                    resume. Information you manually added or edited will be preserved.
                  </span>
                </div>
                <Button variant="secondary" onClick={onCancelPendingUpload} className="w-fit">
                  Cancel
                </Button>
              </div>
            </div>
          )}
          {busy && <p className="mt-2 text-sm text-indigo-600">{busy}</p>}

          <div className="mt-4 border-t border-slate-100 pt-3">
            {!resetConfirmOpen ? (
              <button
                type="button"
                onClick={() => setResetConfirmOpen(true)}
                className="text-xs font-medium text-rose-600 hover:underline"
              >
                Reset career profile
              </button>
            ) : (
              <div className="rounded-xl border border-rose-200 bg-rose-50/60 px-3.5 py-3 text-sm">
                <p className="font-medium text-rose-800">
                  Remove your current resume and all career facts. Job preferences, contact information,
                  and saved job history will remain.
                </p>
                <div className="mt-2.5 flex flex-wrap gap-2">
                  <Button
                    onClick={() => {
                      setResetConfirmOpen(false);
                      onResetProfile();
                    }}
                    className="!bg-rose-600 hover:!bg-rose-700"
                  >
                    Yes, reset my career profile
                  </Button>
                  <Button variant="secondary" onClick={() => setResetConfirmOpen(false)}>
                    Cancel
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
