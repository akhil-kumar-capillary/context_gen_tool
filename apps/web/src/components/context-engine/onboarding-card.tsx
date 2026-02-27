"use client";

import {
  Database,
  Settings2,
  Palette,
  Check,
  GitBranch,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ── Types ──

interface SourceScan {
  id: string;
  name: string;
  icon: "db" | "cfg" | "brand" | string;
  scanned: string;
  findings: string[];
  generated: string[];
}

interface ScanSummary {
  nodes: number;
  rules: number;
  tables: number;
}

export interface OnboardingData {
  orgName: string;
  sources: SourceScan[];
  summary: ScanSummary;
}

// ── Icon map ──

const ICON_MAP: Record<string, typeof Database> = {
  db: Database,
  cfg: Settings2,
  brand: Palette,
};

// ── OnboardingCard ──

export function OnboardingCard({ data }: { data: OnboardingData }) {
  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <GitBranch className="h-5 w-5 text-violet-600" />
        <div>
          <h3 className="text-sm font-bold text-gray-900">
            Context Tree Generated
          </h3>
          <p className="text-[11px] text-gray-500">
            Org: {data.orgName}
          </p>
        </div>
      </div>

      {/* Sources */}
      <div className="space-y-3">
        {data.sources.map((source) => {
          const Icon = ICON_MAP[source.icon] || Database;
          return (
            <div
              key={source.id}
              className="rounded-lg border border-gray-200 p-3"
            >
              <div className="flex items-center gap-2 mb-2">
                <Icon className="h-4 w-4 text-violet-500" />
                <span className="text-xs font-semibold text-gray-800">
                  {source.name}
                </span>
              </div>
              <p className="text-[11px] text-gray-500 mb-2">
                Scanned: {source.scanned}
              </p>

              {/* Findings */}
              {source.findings.length > 0 && (
                <div className="space-y-1 mb-2">
                  {source.findings.map((f, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-1.5 text-[11px] text-gray-600"
                    >
                      <span className="text-gray-400 shrink-0">&bull;</span>
                      <span>{f}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Generated nodes */}
              {source.generated.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {source.generated.map((g) => (
                    <span
                      key={g}
                      className="inline-flex items-center gap-1 rounded bg-green-50 px-2 py-0.5 text-[10px] font-medium text-green-700"
                    >
                      <Check className="h-2.5 w-2.5" />
                      {g}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Summary */}
      <div className="flex items-center gap-4 rounded-lg bg-violet-50 border border-violet-200 px-3 py-2">
        <div className="text-center">
          <p className="text-lg font-bold text-violet-700">
            {data.summary.nodes}
          </p>
          <p className="text-[10px] text-violet-500">nodes</p>
        </div>
        <div className="text-center">
          <p className="text-lg font-bold text-violet-700">
            {data.summary.rules}
          </p>
          <p className="text-[10px] text-violet-500">rules</p>
        </div>
        <div className="text-center">
          <p className="text-lg font-bold text-violet-700">
            {data.summary.tables}
          </p>
          <p className="text-[10px] text-violet-500">tables</p>
        </div>
      </div>
    </div>
  );
}
