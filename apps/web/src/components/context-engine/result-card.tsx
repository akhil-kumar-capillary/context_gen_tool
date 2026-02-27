"use client";

import { Check, X, AlertTriangle, Key, FileText } from "lucide-react";
import { cn } from "@/lib/utils";

// ── Types ──

interface CheckItem {
  label: string;
  value: string;
  ok: boolean | null;
}

interface SecretInfo {
  key: string;
  type: string;
  scope: string;
}

export interface ResultData {
  status:
    | "merged"
    | "secret_detected"
    | "doc_scanned"
    | "redundancy_detected"
    | "restructure"
    | "conflict";
  checks?: CheckItem[];
  summary?: string;
  preview?: string;
  sanitized?: string;
  secret?: SecretInfo;
  trimmed?: string;
  existing?: string;
  kept?: string;
  before?: string;
  after?: string;
  needsApproval?: boolean;
  incoming?: string;
  options?: string[];
}

// ── CheckRow ──

function CheckRow({ c }: { c: CheckItem }) {
  return (
    <div className="flex items-start gap-2 text-[13px] text-gray-600 leading-relaxed">
      <span
        className={cn(
          "shrink-0 mt-0.5",
          c.ok === true
            ? "text-green-600"
            : c.ok === false
              ? "text-red-600"
              : "text-gray-400"
        )}
      >
        {c.ok === true ? (
          <Check className="h-3.5 w-3.5" />
        ) : c.ok === false ? (
          <AlertTriangle className="h-3.5 w-3.5" />
        ) : (
          <span className="text-sm">&bull;</span>
        )}
      </span>
      <span>
        <strong className="text-gray-800">{c.label}:</strong> {c.value}
      </span>
    </div>
  );
}

// ── ResultCard ──

export function ResultCard({ result }: { result: ResultData }) {
  const s = result.status;

  return (
    <div className="text-[13px] leading-relaxed">
      {/* Checks */}
      {result.checks && (
        <div className="space-y-1 mb-3">
          {result.checks.map((c, i) => (
            <CheckRow key={i} c={c} />
          ))}
        </div>
      )}

      {/* Merged */}
      {s === "merged" && (
        <div>
          {result.summary && (
            <p className="text-[13px] font-semibold text-gray-800 mb-1.5">
              {result.summary}
            </p>
          )}
          {result.preview && (
            <div className="rounded-lg bg-green-50 border border-green-200 p-2.5 text-xs text-green-800">
              {result.preview}
            </div>
          )}
        </div>
      )}

      {/* Secret detected */}
      {s === "secret_detected" && (
        <div className="space-y-2">
          {result.summary && (
            <p className="text-[13px] font-semibold text-gray-800">
              {result.summary}
            </p>
          )}
          {result.sanitized && (
            <div className="rounded-lg bg-amber-50 border border-amber-200 p-2.5 text-xs text-amber-800">
              {result.sanitized}
            </div>
          )}
          {result.secret && (
            <div className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-2.5 py-2">
              <Key className="h-3.5 w-3.5 text-amber-600 shrink-0" />
              <span className="font-mono text-xs text-amber-800">
                {`{{${result.secret.key}}}`}
              </span>
              <span className="text-[10px] text-amber-600 ml-auto">
                {result.secret.type} &middot; {result.secret.scope}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Doc scanned */}
      {s === "doc_scanned" && (
        <div>
          {result.summary && (
            <p className="text-[13px] font-semibold text-gray-800 mb-1.5">
              {result.summary}
            </p>
          )}
          {result.preview && (
            <div className="flex items-center gap-2 rounded-lg bg-indigo-50 border border-indigo-200 p-2.5 text-xs text-indigo-800">
              <FileText className="h-3.5 w-3.5 shrink-0" />
              {result.preview}
            </div>
          )}
        </div>
      )}

      {/* Redundancy detected */}
      {s === "redundancy_detected" && (
        <div className="space-y-2">
          {result.summary && (
            <p className="text-[13px] font-semibold text-gray-800">
              {result.summary}
            </p>
          )}
          {result.existing && (
            <div className="rounded-lg bg-gray-50 border border-gray-200 p-2.5 text-xs text-gray-600">
              <span className="font-medium text-gray-700">Existing: </span>
              {result.existing}
            </div>
          )}
          {result.trimmed && (
            <div className="rounded-lg bg-red-50 border border-red-200 p-2.5 text-xs text-red-700 line-through">
              {result.trimmed}
            </div>
          )}
          {result.kept && (
            <div className="rounded-lg bg-green-50 border border-green-200 p-2.5 text-xs text-green-800">
              <span className="font-medium">Kept: </span>
              {result.kept}
            </div>
          )}
        </div>
      )}

      {/* Restructure */}
      {s === "restructure" && (
        <div className="space-y-2">
          {result.summary && (
            <p className="text-[13px] font-semibold text-gray-800">
              {result.summary}
            </p>
          )}
          {result.before && (
            <div className="rounded-lg bg-gray-50 border border-gray-200 p-2.5 text-xs text-gray-600">
              <span className="font-medium text-gray-700">Before: </span>
              {result.before}
            </div>
          )}
          {result.after && (
            <div className="rounded-lg bg-violet-50 border border-violet-200 p-2.5 text-xs text-violet-800">
              <span className="font-medium">After: </span>
              {result.after}
            </div>
          )}
          {result.needsApproval && (
            <div className="flex items-center gap-2 mt-2">
              <button className="rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-700">
                Approve
              </button>
              <button className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50">
                Reject
              </button>
            </div>
          )}
        </div>
      )}

      {/* Conflict */}
      {s === "conflict" && (
        <div className="space-y-2">
          {result.existing && (
            <div className="rounded-lg bg-gray-50 border border-gray-200 p-2.5 text-xs text-gray-700">
              <span className="font-medium">Existing rule: </span>
              {result.existing}
            </div>
          )}
          {result.incoming && (
            <div className="rounded-lg bg-red-50 border border-red-200 p-2.5 text-xs text-red-700">
              <span className="font-medium">Incoming: </span>
              {result.incoming}
            </div>
          )}
          {result.options && result.options.length > 0 && (
            <div className="space-y-1 mt-2">
              <p className="text-xs font-medium text-gray-600">
                Resolution options:
              </p>
              {result.options.map((opt, i) => (
                <button
                  key={i}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-left text-xs text-gray-700 hover:bg-violet-50 hover:border-violet-200 transition-colors"
                >
                  {i + 1}. {opt}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
