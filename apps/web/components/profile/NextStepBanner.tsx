"use client";

import Link from "next/link";
import { Card } from "@/components/ui";

/** The completed-profile state links to /recommendations rather than /jobs: /jobs is for manually
 * adding a specific known posting (paste a JD, a URL, or a board), while /recommendations is where
 * "Search jobs & refresh" (the actual discovery trigger) and match results both live - the natural
 * continuation of "I'm ready, find me jobs" intent. */
function nextStep(hasResume: boolean, pendingCount: number, verifiedCount: number) {
  if (!hasResume) return { text: "Upload your resume", href: "#resume-section" };
  if (pendingCount > 0) {
    return { text: `Review ${pendingCount} extracted fact${pendingCount === 1 ? "" : "s"}`, href: "#verification-section" };
  }
  if (verifiedCount === 0) return { text: "Add a skill or experience", href: "#career-section" };
  return { text: "Find jobs", href: "/recommendations" };
}

export function NextStepBanner({
  hasResume,
  pendingCount,
  verifiedCount,
}: {
  hasResume: boolean;
  pendingCount: number;
  verifiedCount: number;
}) {
  const step = nextStep(hasResume, pendingCount, verifiedCount);
  const isAnchor = step.href.startsWith("#");
  const linkClass = "text-sm font-semibold text-indigo-700 hover:underline";

  return (
    <Card className="flex flex-wrap items-center gap-3 border-indigo-200 bg-indigo-50/60 py-4">
      <span className="text-xs font-semibold uppercase tracking-wide text-indigo-500">Next step</span>
      {isAnchor ? (
        <a href={step.href} className={linkClass}>
          {step.text} →
        </a>
      ) : (
        <Link href={step.href} className={linkClass}>
          {step.text} →
        </Link>
      )}
    </Card>
  );
}
