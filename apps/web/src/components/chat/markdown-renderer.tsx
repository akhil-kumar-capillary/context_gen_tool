"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Style code blocks
          code({ className, children, ...props }) {
            const isInline = !className;
            if (isInline) {
              return (
                <code
                  className="rounded bg-gray-100 px-1.5 py-0.5 text-sm font-mono text-pink-600"
                  {...props}
                >
                  {children}
                </code>
              );
            }
            return (
              <code
                className={`block overflow-x-auto rounded-lg bg-gray-900 p-4 text-sm font-mono text-gray-100 ${className || ""}`}
                {...props}
              >
                {children}
              </code>
            );
          },
          pre({ children }) {
            return <pre className="my-3 overflow-x-auto">{children}</pre>;
          },
          // Style tables
          table({ children }) {
            return (
              <div className="my-3 overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 border border-gray-200 text-sm">
                  {children}
                </table>
              </div>
            );
          },
          thead({ children }) {
            return <thead className="bg-gray-50">{children}</thead>;
          },
          th({ children }) {
            return (
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                {children}
              </th>
            );
          },
          td({ children }) {
            return <td className="whitespace-nowrap px-3 py-2 text-gray-700">{children}</td>;
          },
          // Style other elements
          p({ children }) {
            return <p className="mb-2 leading-relaxed">{children}</p>;
          },
          ul({ children }) {
            return <ul className="mb-2 list-disc pl-6 space-y-1">{children}</ul>;
          },
          ol({ children }) {
            return <ol className="mb-2 list-decimal pl-6 space-y-1">{children}</ol>;
          },
          li({ children }) {
            return <li className="text-gray-700">{children}</li>;
          },
          h1({ children }) {
            return <h1 className="mb-3 text-xl font-bold text-gray-900">{children}</h1>;
          },
          h2({ children }) {
            return <h2 className="mb-2 text-lg font-semibold text-gray-900">{children}</h2>;
          },
          h3({ children }) {
            return <h3 className="mb-2 text-base font-semibold text-gray-800">{children}</h3>;
          },
          blockquote({ children }) {
            return (
              <blockquote className="my-2 border-l-4 border-blue-300 bg-blue-50 py-2 pl-4 italic text-gray-700">
                {children}
              </blockquote>
            );
          },
          a({ href, children }) {
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 underline hover:text-blue-800"
              >
                {children}
              </a>
            );
          },
          strong({ children }) {
            return <strong className="font-semibold text-gray-900">{children}</strong>;
          },
          hr() {
            return <hr className="my-4 border-gray-200" />;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
