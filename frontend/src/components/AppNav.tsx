"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const links = [
  { href: "/", label: "Command Center" },
  { href: "/patients", label: "Patients" },
  { href: "/about", label: "About" },
  { href: "/how-to-use", label: "How to Use" },
];

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

export default function AppNav() {
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (pathname.startsWith("/embed")) return null;

  return (
    <nav className="sticky top-0 z-50 border-b border-slate-200/60 bg-white/90 backdrop-blur-md dark:border-slate-800 dark:bg-slate-950/90">
      <div className="mx-auto flex max-w-7xl items-center gap-1 overflow-x-auto px-4 py-2">
        <Link href="/" className="mr-3 shrink-0 text-sm font-semibold text-emerald-700">
          HERA
        </Link>
        {links.map((link) => {
          const active = mounted && isActive(pathname, link.href);
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`shrink-0 rounded-lg px-3 py-1.5 text-sm transition-colors ${
                active
                  ? "bg-emerald-700 text-white"
                  : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
              }`}
            >
              {link.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
