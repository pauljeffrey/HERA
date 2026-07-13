import Link from "next/link";
import ReactMarkdown from "react-markdown";

import { API_ORIGIN } from "@/lib/api";
import { normalizeAssistantMarkdown } from "@/lib/chat_markdown";

function resolveMediaUrl(src: string | undefined): string {
  if (!src) return "";
  if (src.startsWith("http://") || src.startsWith("https://")) return src;
  if (src.startsWith("/plots/")) return `${API_ORIGIN}${src}`;
  return src;
}

export default function ChatMarkdown({ content }: { content: string }) {
  const markdown = normalizeAssistantMarkdown(content);

  return (
    <ReactMarkdown
      components={{
        a: ({ href, children }) => {
          if (href?.startsWith("/")) {
            return (
              <Link
                href={href}
                className="font-medium text-emerald-700 underline underline-offset-2 hover:text-emerald-900"
              >
                {children}
              </Link>
            );
          }
          return (
            <a href={href} target="_blank" rel="noopener noreferrer" className="text-emerald-700 underline">
              {children}
            </a>
          );
        },
        img: ({ src, alt }) => (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={resolveMediaUrl(typeof src === "string" ? src : undefined)}
            alt={alt ?? "Chart"}
            className="my-3 max-w-full rounded-xl border border-slate-200 bg-white dark:border-slate-700"
          />
        ),
        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
        ul: ({ children }) => <ul className="my-2 list-disc pl-5">{children}</ul>,
        ol: ({ children }) => <ol className="my-2 list-decimal pl-5">{children}</ol>,
        li: ({ children }) => <li className="mb-1">{children}</li>,
        strong: ({ children }) => (
          <strong className="font-semibold text-slate-900 dark:text-slate-100">{children}</strong>
        ),
        table: ({ children }) => (
          <div className="my-3 overflow-x-auto">
            <table className="min-w-full border-collapse text-xs">{children}</table>
          </div>
        ),
        th: ({ children }) => (
          <th className="border border-slate-200 bg-slate-50 px-2 py-1 text-left dark:border-slate-700 dark:bg-slate-800">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="border border-slate-200 px-2 py-1 dark:border-slate-700">{children}</td>
        ),
      }}
    >
      {markdown}
    </ReactMarkdown>
  );
}
