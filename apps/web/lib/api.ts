// The only place the web app talks to the backend. Types mirror rolewise/schemas.py.
// Later: generate these types from the API's OpenAPI schema.

import { getAccessToken } from "@/lib/auth";
import { IS_LOCAL } from "@/lib/env";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type FactKind = "skill" | "role" | "project" | "education" | "certification" | "achievement";

export interface Fact {
  id: string;
  kind: FactKind;
  title: string;
  details: Record<string, unknown>;
  source: string;
  verified: boolean;
  verified_at: string | null;
}

export type Tier = "intern" | "entry" | "mid" | "senior";
export type ArchetypeFit = "primary" | "secondary" | "adjacent";
export type Importance = "critical" | "high" | "meaningful" | "preferred" | "low_signal";
export type Verdict = "apply_now" | "worth_applying" | "only_with_reason" | "not_recommended" | "hard_stop";

export interface Archetype {
  name: string;
  fit: ArchetypeFit;
}

export interface Preferences {
  target_titles: string[];
  locations: string[];
  remote_modes: ("onsite" | "hybrid" | "remote")[];
  salary_min: number | null;
  currency: string;
  seniority: string | null;
  employment_types: string[];
  industries: string[];
  dealbreakers: string[];
  excluded_title_keywords: string[];
  skip_tiers: Tier[];
  authorized_in: string[];
  needs_sponsorship: boolean | null;
  archetypes: Archetype[];
}

export interface Job {
  id: string;
  company: string;
  title: string;
  location: string | null;
  remote_mode: string | null;
  salary_min: number | null;
  salary_max: number | null;
  url: string | null;
  created_at: string;
  listing_status: "active" | "possibly_stale" | "closed" | "unknown";
  last_checked_at: string | null;
}

export interface RequirementResult {
  requirement_id: string;
  kind: string;
  text: string;
  status: "matched" | "partial" | "missing";
  credit: number;
  similarity: number;
  fact_id: string | null;
  fact_title: string | null;
  fact_source: string | null;
  importance: Importance;
  evidence_tier: "stated" | "structural" | "inferred";
  jd_signal: string | null;
  years_evidence: "known" | "unknown" | "none" | null;
  known_years: number | null;
}

export interface Signal {
  code: string;
  message: string;
  quote: string | null;
}

export interface Breakdown {
  score: number;
  filtered_out: string | null;
  components: Record<string, number | null>;
  weights_used: Record<string, number>;
  preference_checks: Record<string, boolean>;
  requirements: RequirementResult[];
  global_score?: number;
  verdict?: Verdict | "filtered";
  hard_stops?: Signal[];
  flags?: Signal[];
  archetype?: { name: string | null; fit: ArchetypeFit | null; strength: number } | null;
  level?: { job_tier: Tier; candidate_tier: Tier; gap: number; fit: number } | null;
  work_auth?: { tier: "sponsors" | "not_needed" | "unstated" | "no_sponsorship"; quote: string | null; country: string | null } | null;
}

export interface Explanation {
  summary: string;
  strengths: string[];
  gaps: string[];
  resume_tips: string[];
}

export interface GapItem {
  requirement_id: string;
  kind: string;
  text: string;
  fact_id: string | null;
  fact_title: string | null;
}

export interface Gaps {
  matched: GapItem[];
  partial: GapItem[];
  missing: GapItem[];
  underrepresented: GapItem[];
  recommendations: {
    type: string;
    text: string;
    supporting_fact_ids: string[];
    requirement?: string;
    importance?: Importance;
    risk?: string;
    mitigation?: string;
  }[];
}

export interface Match {
  id: string;
  job: Job;
  score: number;
  global_score: number | null;
  verdict: Verdict | null;
  has_documents: boolean;
  status: string;
  breakdown: Breakdown;
  explanation: Explanation | null;
  created_at: string;
  gaps?: Gaps | null;
}

export interface Contact {
  full_name: string;
  email: string;
  phone: string;
  location: string;
  links: string[];
}

export type Tone = "mirror" | "formal" | "direct" | "conversational";

export interface Line {
  text: string;
  fact_ids: string[];
}

export interface Block {
  fact_id: string;
  title: string;
  company: string | null;
  location: string | null;
  dates: string;
  bullets: Line[];
}

export interface Coverage {
  text: string;
  importance: Importance;
  status: string;
  state: "shown" | "could_add" | "not_in_profile";
}

interface DocCommon {
  header: { full_name: string; headline?: string; contact: string[] };
  coverage: Coverage[];
  removed: { section: string; text: string; reason: string }[];
  warnings: string[];
  meta: { model: string; tone: Tone; angle: string | null; job_title: string; company: string; prompt_version: string };
}

export interface ResumeContent extends DocCommon {
  summary: Line[];
  competencies: Line[];
  experience: Block[];
  projects: Block[];
  achievements: Line[];
  education: { fact_id: string; text: string }[];
  certifications: { fact_id: string; text: string }[];
  skills: Line[];
}

export interface CoverContent extends DocCommon {
  title: string;
  company: string;
  date: string;
  salutation: string;
  opening: Line | null;
  profile: Line | null;
  narrative: string[];
  problems: Line | null;
  closing: Line | null;
  jd_quotes: string[];
  word_count: number;
}

export interface GeneratedDocument<C = ResumeContent | CoverContent> {
  id: string;
  match_id: string;
  kind: "resume" | "cover_letter";
  version: number;
  content: C;
  status: string;
  created_at: string;
}

export interface MatchDocuments {
  resume: GeneratedDocument<ResumeContent> | null;
  cover_letter: GeneratedDocument<CoverContent> | null;
  history: { id: string; kind: "resume" | "cover_letter"; version: number; created_at: string }[];
}

export interface TaskAccepted {
  run_id: string;
  status: string;
}

export interface Run {
  id: string;
  task: string;
  status: "queued" | "running" | "waiting_user" | "done" | "failed";
  error: string | null;
}

export interface Resume {
  filename: string;
  uploaded_at: string;
  download_url: string;
}

async function authHeaders(): Promise<Record<string, string>> {
  if (IS_LOCAL) {
    return { "X-Dev-User": "demo@rolewise.local" };
  }
  const token = await getAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Turns a FastAPI error response into a message safe to show a user - never the raw JSON, a
 * pydantic validation blob, or a bare status code. The original response body is still logged to
 * the console (a log, not the UI) for debugging. */
function humanizeApiError(status: number, rawBody: string): string {
  try {
    const detail = JSON.parse(rawBody)?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      const messages = detail.map((d) => (typeof d?.msg === "string" ? d.msg : null)).filter(Boolean);
      if (messages.length > 0) return messages.join(" ");
    }
  } catch {
    // Not JSON (or not the shape we expect) - fall through to a generic message below.
  }
  return status >= 500
    ? "Something went wrong on our end. Please try again."
    : "That didn't work. Please check your input and try again.";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const resp = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(await authHeaders()), ...(init.headers ?? {}) },
    cache: "no-store",
  });
  if (!resp.ok) {
    const rawBody = await resp.text();
    console.error(`API error ${resp.status} on ${path}:`, rawBody);
    throw new Error(humanizeApiError(resp.status, rawBody));
  }
  return resp.status === 204 ? (undefined as T) : ((await resp.json()) as T);
}

const json = (body: unknown) => JSON.stringify(body);

export const api = {
  listFacts: () => request<Fact[]>("/profile/facts"),
  createFact: (f: { kind: FactKind; title: string; details?: Record<string, unknown> }) =>
    request<Fact>("/profile/facts", { method: "POST", body: json(f) }),
  verifyFact: (id: string) => request<Fact>(`/profile/facts/${id}/verify`, { method: "POST" }),
  deleteFact: (id: string) => request<void>(`/profile/facts/${id}`, { method: "DELETE" }),

  updateFact: (id: string, patch: { title?: string; details?: Record<string, unknown> }) =>
    request<Fact>(`/profile/facts/${id}`, { method: "PATCH", body: json(patch) }),

  getPreferences: () => request<Preferences>("/profile/preferences"),
  putPreferences: (p: Preferences) => request<Preferences>("/profile/preferences", { method: "PUT", body: json(p) }),

  getResume: () => request<Resume | null>("/profile/resume"),
  resetProfile: () => request<void>("/profile/reset", { method: "POST" }),

  async uploadResume(file: File, replaceExisting = false): Promise<TaskAccepted> {
    const { upload_url, s3_key } = await request<{ upload_url: string; s3_key: string }>(
      "/profile/resume/upload-url",
      { method: "POST", body: json({ filename: file.name, content_type: file.type || "application/octet-stream" }) },
    );
    const put = await fetch(upload_url, {
      method: "PUT",
      body: file,
      headers: { "Content-Type": file.type || "application/octet-stream" },
    });
    if (!put.ok) throw new Error(`Upload failed: ${put.status}`);
    return request<TaskAccepted>("/profile/resume/parse", {
      method: "POST",
      body: json({ s3_key, filename: file.name, replace_existing: replaceExisting }),
    });
  },
  getRun: (id: string) => request<Run>(`/profile/runs/${id}`),

  listJobs: () => request<Job[]>("/jobs"),
  pasteJob: (j: { company: string; title: string; description: string; location?: string; remote_mode?: string }) =>
    request<TaskAccepted>("/jobs/paste", { method: "POST", body: json(j) }),
  ingestGreenhouse: (board_token: string, company?: string) =>
    request<TaskAccepted>("/jobs/sources/greenhouse", { method: "POST", body: json({ board_token, company }) }),
  ingestFromUrl: (url: string) => request<TaskAccepted>("/jobs/from-url", { method: "POST", body: json({ url }) }),

  listMatches: () => request<Match[]>("/matches"),
  getMatch: (id: string) => request<Match>(`/matches/${id}`),
  setMatchStatus: (id: string, status: string) =>
    request<Match>(`/matches/${id}`, { method: "PATCH", body: json({ status }) }),
  refreshMatches: () => request<TaskAccepted>("/matches/refresh", { method: "POST" }),
  discoverMatches: () => request<TaskAccepted>("/matches/discover", { method: "POST" }),
  listMyJobs: () => request<Match[]>("/matches?scope=mine"),

  getContact: () => request<Contact>("/profile/contact"),
  putContact: (c: Contact) => request<Contact>("/profile/contact", { method: "PUT", body: json(c) }),

  generateDocuments: (matchId: string, opts: { tone?: Tone; angle?: string } = {}) =>
    request<TaskAccepted>(`/matches/${matchId}/documents`, { method: "POST", body: json(opts) }),
  getDocuments: (matchId: string) => request<MatchDocuments>(`/matches/${matchId}/documents`),
  getDocument: (docId: string) => request<GeneratedDocument>(`/documents/${docId}`),

  /** Download a generated document as a file (DOCX for Word, or Markdown). */
  async downloadDocument(docId: string, format: "docx" | "md", filename: string): Promise<void> {
    const resp = await fetch(`${API_URL}/documents/${docId}/download?format=${format}`, {
      headers: await authHeaders(),
      cache: "no-store",
    });
    if (!resp.ok) {
      const rawBody = await resp.text();
      console.error(`API error ${resp.status} on /documents/${docId}/download:`, rawBody);
      throw new Error(humanizeApiError(resp.status, rawBody));
    }
    const url = URL.createObjectURL(await resp.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = `${filename}.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  },
};

/** Poll a background run until it finishes. */
export async function waitForRun(runId: string, timeoutMs = 120_000): Promise<Run> {
  const start = Date.now();
  for (;;) {
    const run = await api.getRun(runId);
    if (run.status === "done" || run.status === "failed") return run;
    if (Date.now() - start > timeoutMs) throw new Error("Timed out waiting for the task");
    await new Promise((r) => setTimeout(r, 1500));
  }
}
