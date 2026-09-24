// The only place the web app talks to the backend. Types mirror rolewise/schemas.py.
// Later: generate these types from the API's OpenAPI schema.

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const IS_LOCAL = (process.env.NEXT_PUBLIC_APP_ENV ?? "local") === "local";

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
}

export interface Breakdown {
  score: number;
  filtered_out: string | null;
  components: Record<string, number | null>;
  weights_used: Record<string, number>;
  preference_checks: Record<string, boolean>;
  requirements: RequirementResult[];
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
}

export interface Gaps {
  matched: GapItem[];
  partial: GapItem[];
  missing: GapItem[];
  underrepresented: GapItem[];
  recommendations: { type: string; text: string; supporting_fact_ids: string[] }[];
}

export interface Match {
  id: string;
  job: Job;
  score: number;
  status: string;
  breakdown: Breakdown;
  explanation: Explanation | null;
  created_at: string;
  gaps?: Gaps | null;
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

function authHeaders(): Record<string, string> {
  if (IS_LOCAL) {
    return { "X-Dev-User": "demo@rolewise.local" };
  }
  // TODO(sprint 1): read the Cognito access token from the auth session.
  const token = typeof window !== "undefined" ? window.sessionStorage.getItem("rw_token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const resp = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...authHeaders(), ...(init.headers ?? {}) },
    cache: "no-store",
  });
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(`${resp.status}: ${detail}`);
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

  async uploadResume(file: File): Promise<TaskAccepted> {
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
      body: json({ s3_key, filename: file.name }),
    });
  },
  getRun: (id: string) => request<Run>(`/profile/runs/${id}`),

  listJobs: () => request<Job[]>("/jobs"),
  pasteJob: (j: { company: string; title: string; description: string; location?: string; remote_mode?: string }) =>
    request<TaskAccepted>("/jobs/paste", { method: "POST", body: json(j) }),
  ingestGreenhouse: (board_token: string, company?: string) =>
    request<TaskAccepted>("/jobs/sources/greenhouse", { method: "POST", body: json({ board_token, company }) }),

  listMatches: () => request<Match[]>("/matches"),
  getMatch: (id: string) => request<Match>(`/matches/${id}`),
  setMatchStatus: (id: string, status: string) =>
    request<Match>(`/matches/${id}`, { method: "PATCH", body: json({ status }) }),
  refreshMatches: () => request<TaskAccepted>("/matches/refresh", { method: "POST" }),
  discoverMatches: () => request<TaskAccepted>("/matches/discover", { method: "POST" }),
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
