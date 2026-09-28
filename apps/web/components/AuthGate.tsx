"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { hasSession } from "@/lib/auth";
import { IS_LOCAL } from "@/lib/env";

const PUBLIC_PATHS = new Set(["/login", "/callback"]);

/** Gates the app behind sign-in once real auth is configured (NEXT_PUBLIC_APP_ENV != "local").
 * Local dev keeps using the X-Dev-User header (api.ts), unaffected. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(IS_LOCAL);

  useEffect(() => {
    if (IS_LOCAL || PUBLIC_PATHS.has(pathname)) {
      setReady(true);
      return;
    }
    if (!hasSession()) {
      router.replace("/login");
      return;
    }
    setReady(true);
  }, [pathname, router]);

  if (!ready) return null;
  return <>{children}</>;
}
