import Link from "next/link";
import type { ReactNode } from "react";

type Props = {
  title: string;
  subtitle: string;
  children: ReactNode;
};

export default function InfoPageShell({ title, subtitle, children }: Props) {
  return (
    <div className="min-h-[calc(100vh-49px)] bg-gradient-to-b from-emerald-50/80 via-white to-slate-50 dark:from-slate-950 dark:via-slate-950 dark:to-slate-900">
      <header className="border-b border-emerald-100/80 bg-white/70 px-6 py-10 backdrop-blur-md dark:border-slate-800 dark:bg-slate-950/70">
        <div className="mx-auto max-w-3xl">
          <Link href="/" className="text-xs font-medium text-emerald-700 hover:underline">
            ← Back to Command Center
          </Link>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
            {title}
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-7 text-slate-600 dark:text-slate-400">{subtitle}</p>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-6 py-10">{children}</main>
    </div>
  );
}

export function InfoCard({
  title,
  icon,
  children,
}: {
  title: string;
  icon: string;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <div className="mb-3 flex items-center gap-2">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-100 text-base dark:bg-emerald-950">
          {icon}
        </span>
        <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">{title}</h2>
      </div>
      <div className="space-y-3 text-sm leading-7 text-slate-600 dark:text-slate-300">{children}</div>
    </section>
  );
}

export function InfoStep({
  step,
  title,
  children,
}: {
  step: number;
  title: string;
  children: ReactNode;
}) {
  return (
    <li className="panel flex gap-4">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-700 text-sm font-semibold text-white">
        {step}
      </span>
      <div>
        <h3 className="font-semibold text-slate-900 dark:text-slate-100">{title}</h3>
        <div className="mt-1 text-sm leading-7 text-slate-600 dark:text-slate-300">{children}</div>
      </div>
    </li>
  );
}
