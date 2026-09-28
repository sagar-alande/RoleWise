/** True only when NEXT_PUBLIC_APP_ENV is explicitly "local" - unset, misconfigured, or anything else
 * means the app treats itself as a real, non-local environment (fail closed). The X-Dev-User bypass
 * (api.ts) and the sign-in gate skip (AuthGate.tsx, Nav.tsx) must never accidentally activate just
 * because this env var wasn't set - a missing config value must default to "require real auth", not
 * to "skip it". Single source of truth so all three call sites can't drift out of sync with each other. */
export const IS_LOCAL = process.env.NEXT_PUBLIC_APP_ENV === "local";
