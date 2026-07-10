import { Suspense } from "react";

import CommandCenter from "@/components/CommandCenter";

export default function EmbedPage() {
  return (
    <main className="flex-1">
      <Suspense fallback={<p className="p-4 text-sm text-slate-500">Loading…</p>}>
        <CommandCenter />
      </Suspense>
    </main>
  );
}
