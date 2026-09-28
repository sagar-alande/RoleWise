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

export function Card({
  children,
  className = "",
  id,
}: {
  children: React.ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <div
      id={id}
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

export function Field({ label, name, value, type = "text" }: { label: string; name: string; value: string; type?: string }) {
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

// ---------------------------------------------------------------- verdicts and signals (career-ops style)

const VERDICT_STYLE: Record<string, { label: string; tone: string }> = {
  apply_now: { label: "Apply now", tone: "bg-emerald-50 text-emerald-700 ring-emerald-200" },
  worth_applying: { label: "Worth applying", tone: "bg-sky-50 text-sky-700 ring-sky-200" },
  only_with_reason: { label: "Only with a specific reason", tone: "bg-amber-50 text-amber-700 ring-amber-200" },
  not_recommended: { label: "Not recommended", tone: "bg-slate-100 text-slate-600 ring-slate-200" },
  hard_stop: { label: "Blocked", tone: "bg-rose-50 text-rose-700 ring-rose-200" },
};

export function VerdictBadge({ verdict, globalScore }: { verdict: string | null; globalScore: number | null }) {
  if (!verdict || globalScore == null) return null;
  const v = VERDICT_STYLE[verdict] ?? VERDICT_STYLE.not_recommended;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ${v.tone}`}>
      <span className="tabular-nums">{globalScore.toFixed(1)}/5</span>
      <span aria-hidden>·</span>
      {v.label}
    </span>
  );
}

// The percentage score is the one primary match signal shown in the UI; this label adds a neutral,
// non-prescriptive read of it (no "worth applying" / "not recommended" framing - the user decides).
const ALIGNMENT_STYLE: { min: number; label: string; tone: string }[] = [
  { min: 75, label: "Strong alignment", tone: "bg-emerald-50 text-emerald-700 ring-emerald-200" },
  { min: 50, label: "Moderate alignment", tone: "bg-amber-50 text-amber-700 ring-amber-200" },
  { min: 0, label: "Limited alignment", tone: "bg-slate-100 text-slate-600 ring-slate-200" },
];

export function AlignmentLabel({ score }: { score: number }) {
  const s = ALIGNMENT_STYLE.find((tier) => score >= tier.min) ?? ALIGNMENT_STYLE[ALIGNMENT_STYLE.length - 1];
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ${s.tone}`}>
      {s.label}
    </span>
  );
}

type SignalLike = { code: string; message: string; quote: string | null };

export function SignalList({ hardStops = [], flags = [] }: { hardStops?: SignalLike[]; flags?: SignalLike[] }) {
  if (hardStops.length === 0 && flags.length === 0) return null;
  return (
    <ul className="space-y-2">
      {hardStops.map((s, i) => (
        <li key={`h${i}`} className="rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-sm text-rose-800">
          <span className="font-semibold">Blocker: </span>
          {s.message}
          {s.quote && <blockquote className="mt-1 border-l-2 border-rose-300 pl-2 italic">“{s.quote}”</blockquote>}
        </li>
      ))}
      {flags.map((s, i) => (
        <li key={`f${i}`} className="rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-2.5 text-sm text-amber-800">
          <span className="font-semibold">Heads up: </span>
          {s.message}
          {s.quote && <blockquote className="mt-1 border-l-2 border-amber-300 pl-2 italic">“{s.quote}”</blockquote>}
        </li>
      ))}
    </ul>
  );
}

export function ImportancePill({ importance }: { importance: string }) {
  const tone: Record<string, string> = {
    critical: "bg-rose-600 text-white",
    high: "bg-indigo-600 text-white",
    meaningful: "bg-slate-200 text-slate-700",
    preferred: "bg-slate-100 text-slate-500",
    low_signal: "bg-slate-50 text-slate-400",
  };
  return (
    <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${tone[importance] ?? tone.meaningful}`}>
      {importance.replace("_", " ")}
    </span>
  );
}

/** Freshness stays secondary by design: nothing renders for "active"/"unknown" (the common case,
 * especially right after this feature ships when almost nothing has been checked yet) - only
 * possibly_stale and closed are worth a label. */
export function ListingStatusLabel({ status }: { status: "active" | "possibly_stale" | "closed" | "unknown" }) {
  if (status === "possibly_stale") {
    return (
      <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 ring-1 ring-amber-200">
        Possibly stale
      </span>
    );
  }
  if (status === "closed") {
    return (
      <span className="rounded-full bg-rose-50 px-2 py-0.5 text-xs font-medium text-rose-700 ring-1 ring-rose-200">
        Closed
      </span>
    );
  }
  return null;
}
