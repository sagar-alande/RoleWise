import type { Archetype, ArchetypeFit, FactKind, Tier } from "@/lib/api";

export const KINDS: FactKind[] = ["skill", "role", "project", "education", "certification", "achievement"];
export const YEARS_KINDS: FactKind[] = ["skill", "role"];
export const KIND_LABELS: Record<FactKind, string> = {
  skill: "Skills",
  role: "Experience",
  project: "Projects",
  education: "Education",
  certification: "Certifications",
  achievement: "Achievements",
};
export const TIERS: Tier[] = ["intern", "entry", "mid", "senior"];
export const FITS: { fit: ArchetypeFit; label: string; hint: string }[] = [
  { fit: "primary", label: "Dream roles", hint: "e.g. Data Engineer" },
  { fit: "secondary", label: "Good fit roles", hint: "e.g. Analytics Engineer" },
  { fit: "adjacent", label: "Stretch roles", hint: "e.g. ML Engineer" },
];

export const split = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
export const archetypeNames = (list: Archetype[], fit: ArchetypeFit) =>
  list.filter((a) => a.fit === fit).map((a) => a.name).join(", ");
