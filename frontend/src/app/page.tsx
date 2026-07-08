import { Suspense } from "react";

import CommandCenter from "@/components/CommandCenter";

export default function Home() {
  return (
    <main>
      <Suspense fallback={<p className="p-6 text-sm text-slate-500">Loading command center…</p>}>
        <CommandCenter />
      </Suspense>
    </main>
  );
}
