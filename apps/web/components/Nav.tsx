"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Profile" },
  { href: "/recommendations", label: "Recommendations" },
  { href: "/jobs", label: "Add jobs" },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-10 border-b border-slate-200/70 bg-white/80 backdrop-blur-md">
      <nav className="mx-auto flex max-w-5xl items-center gap-1 px-4 py-3 text-sm sm:gap-2">
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
      </nav>
    </header>
  );
}
