"use client";

import { SafeHtml } from "@/components/shared/safe-html";

import { useEffect, useState, useMemo, useCallback } from "react";
import { toast } from "sonner";
import {
  X,
  Loader2,
  RotateCcw,
  ChevronDown,
  Columns2,
  Rows2,
  History,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn, formatDate } from "@/lib/utils";
import { useContextStore } from "@/stores/context-store";
import { useVersionHistory } from "@/hooks/use-version-history";
import { SplitDiffViewer, UnifiedDiffViewer } from "@/components/shared/split-diff-viewer";
import type { VersionSummary, VersionDetail } from "@/types";

function looksLikeHtml(text: string): boolean {
  return /^\s*<[a-z][\s\S]*>/i.test(text.trim());
}

function stripHtml(html: string): string {
  return html
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/p>/gi, "\n\n")
    .replace(/<\/div>/gi, "\n")
    .replace(/<\/li>/gi, "\n")
    .replace(/<\/h[1-6]>/gi, "\n\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

const BADGE_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  create: { bg: "bg-green-100", text: "text-green-700", label: "Created" },
  update: { bg: "bg-blue-100", text: "text-blue-700", label: "Updated" },
  add_node: { bg: "bg-green-100", text: "text-green-700", label: "Node Added" },
  update_node: { bg: "bg-blue-100", text: "text-blue-700", label: "Node Updated" },
  delete_node: { bg: "bg-red-100", text: "text-red-700", label: "Node Deleted" },
  restructure: { bg: "bg-purple-100", text: "text-purple-700", label: "Restructured" },
  archive: { bg: "bg-amber-100", text: "text-amber-700", label: "Archived" },
  restore: { bg: "bg-primary/10", text: "text-primary", label: "Restored" },
  version_restore: { bg: "bg-primary/10", text: "text-primary", label: "Restored" },
};

function ChangeBadge({ type }: { type: string }) {
  const b = BADGE_STYLES[type] || { bg: "bg-muted", text: "text-muted-foreground", label: type };
  return (
    <span className={cn("rounded px-1.5 py-0.5 text-xs font-medium leading-none", b.bg, b.text)}>
      {b.label}
    </span>
  );
}

function VersionSelector({
  versions,
  selected,
  onChange,
  label,
}: {
  versions: VersionSummary[];
  selected: number | null;
  onChange: (v: number) => void;
  label: string;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
        {label}
      </span>
      <div className="relative">
        <select
          value={selected ?? ""}
          onChange={(e) => onChange(Number(e.target.value))}
          className="appearance-none rounded-lg border border-input bg-background pl-2.5 pr-7 py-1 text-xs font-medium text-foreground cursor-pointer max-w-[200px] truncate"
        >
          <option value="" disabled>Select</option>
          {versions.map((v) => (
            <option key={v.version_number} value={v.version_number}>
              v{v.version_number} &middot; {v.change_summary || v.change_type}
            </option>
          ))}
        </select>
        <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground pointer-events-none" />
      </div>
    </div>
  );
}

const fadeVariants = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
};

export function ContextVersionDialog() {
  const { versionHistoryContextId, setVersionHistoryContextId, fetchContexts } =
    useContextStore();

  const {
    versions,
    isLoading,
    isRestoring,
    fetchHistory,
    fetchVersionDetail,
    restoreVersion,
  } = useVersionHistory("aira_context", versionHistoryContextId);

  const [mode, setMode] = useState<"browse" | "compare">("browse");
  const [expandAll, setExpandAll] = useState(false);
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<VersionDetail | null>(null);
  const [loadingSelected, setLoadingSelected] = useState(false);
  const [compareLeft, setCompareLeft] = useState<number | null>(null);
  const [compareRight, setCompareRight] = useState<number | null>(null);
  const [compareLeftDetail, setCompareLeftDetail] = useState<VersionDetail | null>(null);
  const [compareRightDetail, setCompareRightDetail] = useState<VersionDetail | null>(null);
  const [loadingCompareLeft, setLoadingCompareLeft] = useState(false);
  const [loadingCompareRight, setLoadingCompareRight] = useState(false);
  const [splitView, setSplitView] = useState(true);

  useEffect(() => {
    if (versionHistoryContextId) {
      fetchHistory(true);
      setMode("browse");
      setSelectedVersion(null);
      setSelectedDetail(null);
      setCompareLeft(null);
      setCompareRight(null);
      setCompareLeftDetail(null);
      setCompareRightDetail(null);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [versionHistoryContextId]);

  // Backfill is now handled BEFORE the drawer opens (in context-store.openVersionHistory)

  useEffect(() => {
    if (mode === "browse" && versions.length > 0 && selectedVersion === null) {
      setSelectedVersion(versions[0].version_number);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [versions, mode]);

  useEffect(() => {
    if (selectedVersion === null) { setSelectedDetail(null); return; }
    let cancelled = false;
    setLoadingSelected(true);
    fetchVersionDetail(selectedVersion).then((d) => {
      if (!cancelled) { setSelectedDetail(d); setLoadingSelected(false); }
    });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedVersion]);

  useEffect(() => {
    if (compareLeft === null) { setCompareLeftDetail(null); return; }
    if (compareLeftDetail?.version_number === compareLeft) return;
    let cancelled = false;
    setLoadingCompareLeft(true);
    fetchVersionDetail(compareLeft).then((d) => {
      if (!cancelled) { setCompareLeftDetail(d); setLoadingCompareLeft(false); }
    });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [compareLeft]);

  useEffect(() => {
    if (compareRight === null) { setCompareRightDetail(null); return; }
    if (compareRightDetail?.version_number === compareRight) return;
    let cancelled = false;
    setLoadingCompareRight(true);
    fetchVersionDetail(compareRight).then((d) => {
      if (!cancelled) { setCompareRightDetail(d); setLoadingCompareRight(false); }
    });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [compareRight]);

  useEffect(() => {
    if (!versionHistoryContextId) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (mode === "compare") handleExitCompare();
        else setVersionHistoryContextId(null);
      }
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [versionHistoryContextId, mode]);

  const handleEnterCompare = useCallback(() => {
    const left = selectedVersion;
    const rightDefault =
      versions[0]?.version_number === selectedVersion && versions.length > 1
        ? versions[1].version_number
        : versions[0]?.version_number ?? null;
    setCompareLeft(left);
    setCompareLeftDetail(selectedDetail);
    setLoadingCompareLeft(false);
    setCompareRight(rightDefault);
    setMode("compare");
  }, [selectedVersion, selectedDetail, versions]);

  const handleExitCompare = useCallback(() => {
    setSelectedVersion(compareLeft);
    setSelectedDetail(compareLeftDetail);
    setMode("browse");
  }, [compareLeft, compareLeftDetail]);

  const handleRestore = async (versionNumber: number) => {
    const ok = await restoreVersion(versionNumber);
    if (ok) {
      await Promise.all([fetchContexts(), fetchHistory(true)]);
      toast.success(`Restored to version ${versionNumber}`);
    } else {
      toast.error("Failed to restore version");
    }
  };

  const leftDiffContent = useMemo(() => {
    if (!compareLeftDetail?.snapshot) return "";
    return stripHtml((compareLeftDetail.snapshot.content as string) || "");
  }, [compareLeftDetail]);

  const rightDiffContent = useMemo(() => {
    if (!compareRightDetail?.snapshot) return "";
    return stripHtml((compareRightDetail.snapshot.content as string) || "");
  }, [compareRightDetail]);

  if (!versionHistoryContextId) return null;

  const restoreTarget = mode === "compare" ? compareRight : selectedVersion;
  const canCompare = versions.length >= 2;

  return (
    <div className="fixed inset-0 z-[70] flex justify-end bg-black/30 backdrop-blur-[2px]">
      {/* Backdrop click to close */}
      <div className="flex-1" onClick={() => setVersionHistoryContextId(null)} />
      <motion.div
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", stiffness: 300, damping: 30 }}
        className="flex w-full lg:w-4/5 flex-col bg-background shadow-2xl overflow-hidden"
      >
      {/* Header */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2 bg-muted/50 shrink-0">
        {/* Title */}
        <h2 className="text-sm font-semibold text-foreground flex items-center gap-2 mr-auto">
          <History className="h-4 w-4 text-muted-foreground" />
          Version History
        </h2>

        {/* Compare selectors */}
        {mode === "compare" && (
          <div className="flex items-center gap-1.5">
            <VersionSelector versions={versions} selected={compareLeft} onChange={setCompareLeft} label="Old" />
            <span className="text-muted-foreground text-xs">&rarr;</span>
            <VersionSelector versions={versions} selected={compareRight} onChange={setCompareRight} label="New" />
          </div>
        )}

        {/* Actions */}
        {mode === "browse" ? (
          <button
            onClick={handleEnterCompare}
            disabled={!canCompare}
            className="flex items-center gap-1.5 rounded-lg border border-input px-2.5 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Columns2 className="h-3.5 w-3.5" />
            Compare
          </button>
        ) : (
          <>
            <button onClick={() => setSplitView(!splitView)} className="flex items-center gap-1.5 rounded-lg border border-input px-2.5 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors">
              {splitView ? <Rows2 className="h-3.5 w-3.5" /> : <Columns2 className="h-3.5 w-3.5" />}
              {splitView ? "Unified" : "Split"}
            </button>
            <button onClick={() => setExpandAll(!expandAll)} className={cn("flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors", expandAll ? "border-primary/30 bg-primary/5 text-primary" : "border-input text-muted-foreground hover:bg-muted hover:text-foreground")}>
              {expandAll ? "Collapse" : "Expand All"}
            </button>
            <button onClick={handleExitCompare} className="flex items-center gap-1.5 rounded-lg border border-input px-2.5 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors">
              <X className="h-3.5 w-3.5" />
              Exit
            </button>
          </>
        )}
        {restoreTarget && (
          <button
            onClick={() => handleRestore(restoreTarget)}
            disabled={isRestoring}
            className="flex items-center gap-1.5 rounded-lg border border-primary/30 bg-primary/5 px-2.5 py-1.5 text-xs font-medium text-primary hover:bg-primary/10 transition-colors disabled:opacity-50"
          >
            {isRestoring ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
            v{restoreTarget}
          </button>
        )}
        <button onClick={() => setVersionHistoryContextId(null)} className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors">
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden min-w-0">
        {/* Timeline sidebar */}
        <div className="w-64 shrink-0 border-r border-border bg-muted/30 flex flex-col">
          <div className="px-4 py-2.5 border-b border-border shrink-0">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Versions ({versions.length})
            </span>
          </div>
          <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1">
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            ) : versions.length === 0 ? (
              <p className="text-xs text-muted-foreground px-2 py-4 text-center">No versions yet</p>
            ) : (
              versions.map((v) => {
                const isActive = mode === "browse" ? selectedVersion === v.version_number : compareLeft === v.version_number;
                return (
                  <button
                    key={v.id}
                    onClick={() => {
                      if (mode === "browse") setSelectedVersion(v.version_number);
                      else setCompareLeft(v.version_number);
                    }}
                    className={cn(
                      "w-full text-left rounded-lg border px-3 py-2 transition-all",
                      isActive
                        ? "border-primary/30 bg-primary/5 ring-1 ring-primary/20"
                        : "border-transparent bg-background hover:border-border hover:bg-muted/50",
                    )}
                  >
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-mono font-bold text-muted-foreground">v{v.version_number}</span>
                      <ChangeBadge type={v.change_type} />
                    </div>
                    <p className="text-xs text-muted-foreground mt-1 line-clamp-2 leading-snug">{v.change_summary || v.change_type}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">{formatDate(v.created_at)}</p>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Main content area */}
        <div className="flex-1 flex flex-col overflow-hidden min-w-0">
          <AnimatePresence mode="wait">
            {mode === "browse" ? (
              <motion.div key="browse" variants={fadeVariants} initial="initial" animate="animate" exit="exit" transition={{ duration: 0.12 }} className="flex-1 flex flex-col overflow-hidden">
                {loadingSelected ? (
                  <div className="flex items-center justify-center flex-1">
                    <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                    <span className="ml-2 text-sm text-muted-foreground">Loading...</span>
                  </div>
                ) : !selectedDetail ? (
                  <div className="flex items-center justify-center flex-1 text-muted-foreground">
                    <p className="text-sm">Select a version to view its content</p>
                  </div>
                ) : (
                  <>
                    <div className="sticky top-0 z-10 border-b border-border bg-background/95 backdrop-blur-sm px-6 py-2.5 shrink-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono font-bold text-muted-foreground">v{selectedDetail.version_number}</span>
                        <ChangeBadge type={selectedDetail.change_type} />
                        <span className="text-xs text-muted-foreground">{formatDate(selectedDetail.created_at)}</span>
                      </div>
                      {selectedDetail.change_summary && (
                        <p className="text-xs text-muted-foreground mt-0.5">{selectedDetail.change_summary}</p>
                      )}
                    </div>
                    <div className="flex-1 overflow-y-auto px-6 py-4">
                      <VersionContent content={(selectedDetail.snapshot.content as string) || ""} />
                    </div>
                  </>
                )}
              </motion.div>
            ) : (
              <motion.div key="compare" variants={fadeVariants} initial="initial" animate="animate" exit="exit" transition={{ duration: 0.12 }} className="flex-1 flex flex-col overflow-hidden min-w-0">
                <div className="flex-1 overflow-auto min-w-0">
                  {loadingCompareLeft || loadingCompareRight ? (
                    <div className="flex items-center justify-center h-full">
                      <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                      <span className="ml-2 text-sm text-muted-foreground">Loading versions...</span>
                    </div>
                  ) : compareLeftDetail && compareRightDetail ? (
                    splitView ? (
                      <SplitDiffViewer
                        oldValue={leftDiffContent}
                        newValue={rightDiffContent}
                        oldTitle={`Version ${compareLeft}`}
                        newTitle={`Version ${compareRight}`}
                        contextLines={expandAll ? Infinity : 3}
                      />
                    ) : (
                      <UnifiedDiffViewer
                        oldValue={leftDiffContent}
                        newValue={rightDiffContent}
                        contextLines={expandAll ? Infinity : 3}
                      />
                    )
                  ) : (
                    <div className="flex items-center justify-center h-full text-muted-foreground">
                      <p className="text-sm">Select versions to compare</p>
                    </div>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
      </motion.div>
    </div>
  );
}

function VersionContent({ content }: { content: string }) {
  if (!content) {
    return <p className="text-sm text-muted-foreground italic">No content available</p>;
  }
  if (looksLikeHtml(content)) {
    return <SafeHtml html={content} className="prose prose-sm max-w-none text-foreground" />;
  }
  return <pre className="whitespace-pre-wrap text-sm text-foreground font-sans leading-relaxed">{content}</pre>;
}
