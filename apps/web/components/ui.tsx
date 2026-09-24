export function ScoreBadge({ score }: { score: number }) {
  const tone =
    score >= 75
      ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
      : score >= 50
        ? "bg-amber-50 text-amber-700 ring-1 ring-amber-200"
        : "bg-slate-100 text-slate-600 ring-1 ring-slate-200";
  return (
    <span className={`flex h-14 w-14 shrink-0 flex-col items-center justify-center rounded-full text-base font-semibold tabular-nums ${tone}`}>
      {Math.round(score)}
      <span className="text-[10px] font-medium opacity-70">%</span>
    </span>
  );
}

type RequirementLike = { requirement_id: string; text: string; status: "matched" | "partial" | "missing" };

export function RequirementTags({ requirements, max = 8 }: { requirements: RequirementLike[]; max?: number }) {
  if (requirements.length === 0) return null;
  const shown = requirements.slice(0, max);
  const rest = requirements.length - shown.length;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {shown.map((r) => {
        const ok = r.status === "matched";
        const partial = r.status === "partial";
        const tone = ok
          ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
          : partial
            ? "bg-amber-50 text-amber-700 ring-amber-200"
            : "bg-rose-50 text-rose-700 ring-rose-200";
        return (
          <span
            key={r.requirement_id}
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${tone}`}
          >
            <span aria-hidden>{ok ? "✓" : partial ? "±" : "✕"}</span>
            {r.text}
          </span>
        );
      })}
      {rest > 0 && <span className="px-1 py-0.5 text-xs text-slate-400">+{rest} more</span>}
    </div>
  );
}

export function StatusPill({ status }: { status: "matched" | "partial" | "missing" }) {
  const tone = {
    matched: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    partial: "bg-amber-50 text-amber-700 ring-amber-200",
    missing: "bg-rose-50 text-rose-700 ring-rose-200",
  }[status];
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${tone}`}>{status}</span>;
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-2xl border border-slate-200/70 bg-white/90 p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_8px_24px_-12px_rgba(15,23,42,0.08)] backdrop-blur-sm sm:p-6 ${className}`}
    >
      {children}
    </div>
  );
}

export function Button({
  children,
  variant = "primary",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" }) {
  const style = {
    primary:
      "bg-indigo-600 text-white shadow-sm shadow-indigo-600/20 hover:bg-indigo-700 disabled:hover:bg-indigo-600",
    secondary:
      "border border-slate-200 bg-white text-slate-700 shadow-sm hover:border-slate-300 hover:bg-slate-50",
    ghost: "text-slate-600 hover:bg-slate-100",
  }[variant];
  return (
    <button
      {...props}
      className={`rounded-lg px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${style} ${props.className ?? ""}`}
    >
      {children}
    </button>
  );
}

export function ErrorNote({ error }: { error: string | null }) {
  return error ? (
    <p className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p>
  ) : null;
}

export function SectionEyebrow({ children }: { children: React.ReactNode }) {
  return <p className="text-xs font-semibold uppercase tracking-wider text-indigo-600">{children}</p>;
}

export function StepBadge({ n }: { n: number }) {
  return (
    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-xs font-semibold text-white">
      {n}
    </span>
  );
}
