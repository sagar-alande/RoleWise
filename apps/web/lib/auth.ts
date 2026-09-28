"use client";

/**
 * Google Sign-In via the Cognito Hosted UI, Authorization Code flow + PKCE. No client secret is
 * ever used or stored here - the Cognito app client is a public SPA client (generateSecret: false
 * in infra/lib/rolewise-stack.ts) and the Google OAuth client secret lives only in Secrets Manager,
 * read by CloudFormation at deploy time. The API never changes: it already verifies any
 * Cognito-issued token (apps/backend/rolewise/auth.py) regardless of which identity provider the
 * user actually signed in with.
 */

const COGNITO_DOMAIN = process.env.NEXT_PUBLIC_COGNITO_DOMAIN ?? "";
const CLIENT_ID = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID ?? "";

const VERIFIER_KEY = "rw_pkce_verifier";
const STATE_KEY = "rw_oauth_state";
const ACCESS_TOKEN_KEY = "rw_access_token";
const ID_TOKEN_KEY = "rw_id_token";
const REFRESH_TOKEN_KEY = "rw_refresh_token";
const EXPIRES_AT_KEY = "rw_token_expires_at";

function redirectUri(): string {
  return `${window.location.origin}/callback`;
}

function randomString(length: number): string {
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  return base64UrlEncode(bytes);
}

function base64UrlEncode(bytes: Uint8Array): string {
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function sha256(text: string): Promise<Uint8Array> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return new Uint8Array(digest);
}

function storeTokens(tokens: { access_token: string; id_token: string; refresh_token?: string; expires_in: number }) {
  sessionStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  sessionStorage.setItem(ID_TOKEN_KEY, tokens.id_token);
  if (tokens.refresh_token) sessionStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
  // Refresh a little early so a request never races an expiry that just landed.
  sessionStorage.setItem(EXPIRES_AT_KEY, String(Date.now() + (tokens.expires_in - 30) * 1000));
}

function clearTokens() {
  for (const k of [ACCESS_TOKEN_KEY, ID_TOKEN_KEY, REFRESH_TOKEN_KEY, EXPIRES_AT_KEY, VERIFIER_KEY, STATE_KEY]) {
    sessionStorage.removeItem(k);
  }
}

async function tokenRequest(body: Record<string, string>): Promise<void> {
  const resp = await fetch(`${COGNITO_DOMAIN}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: CLIENT_ID, ...body }),
  });
  if (!resp.ok) throw new Error(`Token request failed: ${resp.status} ${await resp.text()}`);
  storeTokens(await resp.json());
}

/** Kicks off Google sign-in: generates a PKCE pair, stores the verifier, redirects to the Hosted UI
 * with identity_provider=Google so it skips straight to Google instead of showing a chooser. */
export async function login(): Promise<void> {
  if (!COGNITO_DOMAIN || !CLIENT_ID) {
    throw new Error("Google Sign-In isn't configured (missing NEXT_PUBLIC_COGNITO_DOMAIN / NEXT_PUBLIC_COGNITO_CLIENT_ID).");
  }
  const verifier = randomString(64);
  const challenge = base64UrlEncode(await sha256(verifier));
  const state = randomString(24);
  sessionStorage.setItem(VERIFIER_KEY, verifier);
  sessionStorage.setItem(STATE_KEY, state);

  const url = new URL("/oauth2/authorize", COGNITO_DOMAIN);
  url.searchParams.set("client_id", CLIENT_ID);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("scope", "openid email profile");
  url.searchParams.set("redirect_uri", redirectUri());
  url.searchParams.set("identity_provider", "Google");
  url.searchParams.set("code_challenge", challenge);
  url.searchParams.set("code_challenge_method", "S256");
  url.searchParams.set("state", state);
  window.location.assign(url.toString());
}

/** Completes the flow after Cognito redirects back with ?code=&state=. Throws on a state mismatch
 * (CSRF) or a failed exchange - the caller should send the user back to /login on any error. */
export async function handleCallback(code: string, state: string): Promise<void> {
  const expectedState = sessionStorage.getItem(STATE_KEY);
  const verifier = sessionStorage.getItem(VERIFIER_KEY);
  if (!expectedState || state !== expectedState || !verifier) {
    throw new Error("Sign-in could not be verified. Please try again.");
  }
  await tokenRequest({
    grant_type: "authorization_code",
    code,
    redirect_uri: redirectUri(),
    code_verifier: verifier,
  });
  sessionStorage.removeItem(VERIFIER_KEY);
  sessionStorage.removeItem(STATE_KEY);
}

async function refresh(): Promise<boolean> {
  const refreshToken = sessionStorage.getItem(REFRESH_TOKEN_KEY);
  if (!refreshToken) return false;
  try {
    await tokenRequest({ grant_type: "refresh_token", refresh_token: refreshToken });
    return true;
  } catch {
    clearTokens();
    return false;
  }
}

/** The bearer token for API calls - refreshes it first if it's expired (or close to it). Returns
 * null when there's no valid session, so the caller (api.ts) sends the request unauthenticated and
 * lets the backend's existing 401 handling apply. */
export async function getAccessToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  const expiresAt = Number(sessionStorage.getItem(EXPIRES_AT_KEY) ?? 0);
  if (Date.now() >= expiresAt && !(await refresh())) return null;
  return sessionStorage.getItem(ACCESS_TOKEN_KEY);
}

/** Synchronous, storage-only check for whether a session exists at all - good enough for gating UI
 * visibility. The actual security boundary is the backend verifying the bearer token on every call,
 * not this check. */
export function hasSession(): boolean {
  return typeof window !== "undefined" && !!sessionStorage.getItem(ACCESS_TOKEN_KEY);
}

/** Decodes (does NOT verify - purely for display) the email claim out of the stored id_token. */
export function getSignedInEmail(): string | null {
  if (typeof window === "undefined") return null;
  const idToken = sessionStorage.getItem(ID_TOKEN_KEY);
  if (!idToken) return null;
  try {
    const payload = JSON.parse(atob(idToken.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return payload.email ?? null;
  } catch {
    return null;
  }
}

/** Clears the local session and ends it on Cognito's side too, so a stale Hosted UI cookie can't
 * silently re-authenticate the next login attempt. */
export function logout(): void {
  clearTokens();
  const url = new URL("/logout", COGNITO_DOMAIN);
  url.searchParams.set("client_id", CLIENT_ID);
  url.searchParams.set("logout_uri", window.location.origin);
  window.location.assign(url.toString());
}
