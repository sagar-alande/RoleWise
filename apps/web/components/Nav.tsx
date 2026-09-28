"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getSignedInEmail, hasSession, logout } from "@/lib/auth";
import { IS_LOCAL } from "@/lib/env";

const LINKS = [
  { href: "/", label: "Profile" },
  { href: "/recommendations", label: "Recommendations" },
  { href: "/my-jobs", label: "My jobs" },
  { href: "/jobs", label: "Add jobs" },
];

export function Nav() {
  const pathname = usePathname();
  const [signedInEmail, setSignedInEmail] = useState<string | null>(null);

  useEffect(() => {
    if (!IS_LOCAL && hasSession()) setSignedInEmail(getSignedInEmail());
  }, [pathname]);

  if (pathname === "/login" || pathname === "/callback") return null;
  return (
    <header className="sticky top-0 z-10 border-b border-slate-200/70 bg-white/80 backdrop-blur-md">
      <nav className="mx-auto flex max-w-5xl flex-wrap items-center gap-1 px-4 py-3 text-sm sm:gap-2">
        <Link href="/" className="mr-4 flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-600 text-sm font-bold text-white">
            R
          </span>
          <span className="text-base font-semibold tracking-tight text-slate-900">RoleWise</span>
        </Link>
        {LINKS.map((l) => {
          const active = pathname === l.href || (l.href !== "/" && pathname.startsWith(l.href));
          return (
            <Link
              key={l.href}
              href={l.href}
              className={`rounded-lg px-3 py-1.5 font-medium transition-colors ${
                active ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              }`}
            >
              {l.label}
            </Link>
          );
        })}
        {signedInEmail && (
          <span className="ml-auto flex items-center gap-3 text-xs text-slate-500">
            <span className="hidden sm:inline">{signedInEmail}</span>
            <button onClick={logout} className="rounded-lg px-2.5 py-1.5 font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900">
              Sign out
            </button>
          </span>
        )}
      </nav>
    </header>
  );
}
