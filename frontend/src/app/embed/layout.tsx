import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "HERA",
  description: "Clinical trial matching demo",
};

export default function EmbedLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex h-9 shrink-0 items-center justify-between border-b border-slate-200 px-3 text-xs dark:border-slate-800">
        <span className="font-semibold text-emerald-700">HERA</span>
        <Link href="/" target="_blank" rel="noopener noreferrer" className="text-slate-500 hover:text-emerald-700">
          Open full app ↗
        </Link>
      </header>
      {children}
    </div>
  );
}
