"use client";

import React, { useMemo, useRef, useCallback } from "react";
import { diffLines, diffWordsWithSpace } from "diff";
import { cn } from "@/lib/utils";

interface SplitDiffViewerProps {
  oldValue: string;
  newValue: string;
  oldTitle?: string;
  newTitle?: string;
  contextLines?: number;
}

// ── Types ──────────────────────────────────────────────────────────

interface DiffRow {
  leftNum: number | null;
  rightNum: number | null;
  leftContent: string;
  rightContent: string;
  type: "added" | "removed" | "modified" | "unchanged";
}

interface WordSegment {
  text: string;
  highlight: boolean;
}

// ── Build diff rows with alignment ─────────────────────────────────

function buildRows(oldText: string, newText: string): DiffRow[] {
  const changes = diffLines(oldText, newText);
  const rows: DiffRow[] = [];
  let oldNum = 1;
  let newNum = 1;

  let i = 0;
  while (i < changes.length) {
    const change = changes[i];
    const lines = change.value.replace(/\n$/, "").split("\n");

    if (change.removed) {
      // Check if next change is "added" — if so, pair them as "modified"
      const next = changes[i + 1];
      if (next && next.added) {
        const addedLines = next.value.replace(/\n$/, "").split("\n");
        const maxLen = Math.max(lines.length, addedLines.length);
        for (let j = 0; j < maxLen; j++) {
          rows.push({
            leftNum: j < lines.length ? oldNum++ : null,
            rightNum: j < addedLines.length ? newNum++ : null,
            leftContent: j < lines.length ? lines[j] : "",
            rightContent: j < addedLines.length ? addedLines[j] : "",
            type: j < lines.length && j < addedLines.length ? "modified" : j < lines.length ? "removed" : "added",
          });
        }
        i += 2; // skip the "added" change
        continue;
      }
      // Pure removal
      for (const line of lines) {
        rows.push({ leftNum: oldNum++, rightNum: null, leftContent: line, rightContent: "", type: "removed" });
      }
    } else if (change.added) {
      for (const line of lines) {
        rows.push({ leftNum: null, rightNum: newNum++, leftContent: "", rightContent: line, type: "added" });
      }
    } else {
      for (const line of lines) {
        rows.push({ leftNum: oldNum++, rightNum: newNum++, leftContent: line, rightContent: line, type: "unchanged" });
      }
    }
    i++;
  }

  return rows;
}

// ── Word-level diff within a line ──────────────────────────────────

function wordDiff(oldLine: string, newLine: string): { oldSegs: WordSegment[]; newSegs: WordSegment[] } {
  const changes = diffWordsWithSpace(oldLine, newLine);
  const oldSegs: WordSegment[] = [];
  const newSegs: WordSegment[] = [];

  for (const c of changes) {
    if (c.added) {
      newSegs.push({ text: c.value, highlight: true });
    } else if (c.removed) {
      oldSegs.push({ text: c.value, highlight: true });
    } else {
      oldSegs.push({ text: c.value, highlight: false });
      newSegs.push({ text: c.value, highlight: false });
    }
  }

  return { oldSegs, newSegs };
}

// ── Collapsible context ────────────────────────────────────────────

function collapseUnchanged(rows: DiffRow[], contextLines: number): (DiffRow | { type: "collapse"; count: number })[] {
  const result: (DiffRow | { type: "collapse"; count: number })[] = [];

  // Find ranges of unchanged lines
  let i = 0;
  while (i < rows.length) {
    if (rows[i].type === "unchanged") {
      // Find end of unchanged block
      let j = i;
      while (j < rows.length && rows[j].type === "unchanged") j++;
      const blockLen = j - i;

      if (blockLen > contextLines * 2 + 1) {
        // Show first contextLines, collapse middle, show last contextLines
        for (let k = i; k < i + contextLines; k++) result.push(rows[k]);
        result.push({ type: "collapse", count: blockLen - contextLines * 2 });
        for (let k = j - contextLines; k < j; k++) result.push(rows[k]);
      } else {
        // Too short to collapse — show all
        for (let k = i; k < j; k++) result.push(rows[k]);
      }
      i = j;
    } else {
      result.push(rows[i]);
      i++;
    }
  }

  return result;
}

// ── Styled segments renderer ───────────────────────────────────────

function WordHighlight({ segments, isRemoved }: { segments: WordSegment[]; isRemoved: boolean }) {
  return (
    <>
      {segments.map((seg, i) => (
        <span
          key={i}
          className={cn(
            seg.highlight && isRemoved && "bg-red-200 dark:bg-red-800/50 rounded-sm",
            seg.highlight && !isRemoved && "bg-green-200 dark:bg-green-800/50 rounded-sm",
          )}
        >
          {seg.text}
        </span>
      ))}
    </>
  );
}

// ── Row styles ─────────────────────────────────────────────────────

const ROW_BG = {
  added: "bg-green-50/80 dark:bg-green-950/20",
  removed: "bg-red-50/80 dark:bg-red-950/20",
  modified: "",
  unchanged: "",
};

const GUTTER_BG = {
  added: "bg-green-100/80 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  removed: "bg-red-100/80 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  modified: "bg-muted/50 text-muted-foreground",
  unchanged: "bg-muted/30 text-muted-foreground/60",
};

const MARKER = { added: "+", removed: "\u2212", modified: "~", unchanged: " " };

// ── Main component ─────────────────────────────────────────────────

export function SplitDiffViewer({
  oldValue,
  newValue,
  oldTitle,
  newTitle,
  contextLines = 3,
}: SplitDiffViewerProps) {
  const leftRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  const syncing = useRef(false);

  const rows = useMemo(() => buildRows(oldValue, newValue), [oldValue, newValue]);
  const collapsed = useMemo(() => collapseUnchanged(rows, contextLines), [rows, contextLines]);

  // Synchronized scrolling
  const handleScroll = useCallback((source: "left" | "right") => {
    if (syncing.current) return;
    syncing.current = true;
    const from = source === "left" ? leftRef.current : rightRef.current;
    const to = source === "left" ? rightRef.current : leftRef.current;
    if (from && to) {
      to.scrollTop = from.scrollTop;
    }
    requestAnimationFrame(() => { syncing.current = false; });
  }, []);

  return (
    <div className="flex h-full min-h-0">
      {/* Left (old) */}
      <div className="border-r border-border flex flex-col" style={{ width: "50%", minWidth: 0 }}>
        {oldTitle && (
          <div className="px-3 py-1.5 text-xs font-medium text-muted-foreground bg-muted/50 border-b border-border shrink-0">
            {oldTitle}
          </div>
        )}
        <div
          ref={leftRef}
          className="flex-1 overflow-auto"
          onScroll={() => handleScroll("left")}
        >
          <table className="w-full border-collapse text-xs" style={{ tableLayout: "fixed" }}>
            <colgroup>
              <col style={{ width: "36px" }} />
              <col style={{ width: "20px" }} />
              <col />
            </colgroup>
            <tbody>
              {collapsed.map((item, i) => {
                if ("count" in item) {
                  return (
                    <tr key={`c-${i}`}>
                      <td colSpan={3} className="text-center py-1 text-xs text-muted-foreground bg-muted/30 border-y border-border">
                        {item.count} unchanged lines
                      </td>
                    </tr>
                  );
                }
                const row = item as DiffRow;
                const leftType = row.type === "added" ? "unchanged" : row.type;
                const isModified = row.type === "modified";
                const wordSegs = isModified ? wordDiff(row.leftContent, row.rightContent) : null;

                return (
                  <tr key={i} className={ROW_BG[leftType]}>
                    <td className={cn("w-8 select-none text-right px-1.5 py-px border-r border-border tabular-nums", GUTTER_BG[leftType])}>
                      {row.leftNum ?? ""}
                    </td>
                    <td className={cn("w-5 select-none text-center py-px", GUTTER_BG[leftType])}>
                      {row.leftNum !== null ? MARKER[leftType] : ""}
                    </td>
                    <td className={cn("px-2 py-px whitespace-pre-wrap break-words", isModified && "bg-red-50/60 dark:bg-red-950/15")}>
                      {isModified && wordSegs ? (
                        <WordHighlight segments={wordSegs.oldSegs} isRemoved />
                      ) : (
                        row.leftContent || "\u00A0"
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Right (new) */}
      <div className="flex flex-col" style={{ width: "50%", minWidth: 0 }}>
        {newTitle && (
          <div className="px-3 py-1.5 text-xs font-medium text-muted-foreground bg-muted/50 border-b border-border shrink-0">
            {newTitle}
          </div>
        )}
        <div
          ref={rightRef}
          className="flex-1 overflow-auto"
          onScroll={() => handleScroll("right")}
        >
          <table className="w-full border-collapse text-xs" style={{ tableLayout: "fixed" }}>
            <colgroup>
              <col style={{ width: "36px" }} />
              <col style={{ width: "20px" }} />
              <col />
            </colgroup>
            <tbody>
              {collapsed.map((item, i) => {
                if ("count" in item) {
                  return (
                    <tr key={`c-${i}`}>
                      <td colSpan={3} className="text-center py-1 text-xs text-muted-foreground bg-muted/30 border-y border-border">
                        {item.count} unchanged lines
                      </td>
                    </tr>
                  );
                }
                const row = item as DiffRow;
                const rightType = row.type === "removed" ? "unchanged" : row.type;
                const isModified = row.type === "modified";
                const wordSegs = isModified ? wordDiff(row.leftContent, row.rightContent) : null;

                return (
                  <tr key={i} className={ROW_BG[rightType]}>
                    <td className={cn("w-8 select-none text-right px-1.5 py-px border-r border-border tabular-nums", GUTTER_BG[rightType])}>
                      {row.rightNum ?? ""}
                    </td>
                    <td className={cn("w-5 select-none text-center py-px", GUTTER_BG[rightType])}>
                      {row.rightNum !== null ? MARKER[rightType] : ""}
                    </td>
                    <td className={cn("px-2 py-px whitespace-pre-wrap break-words", isModified && "bg-green-50/60 dark:bg-green-950/15")}>
                      {isModified && wordSegs ? (
                        <WordHighlight segments={wordSegs.newSegs} isRemoved={false} />
                      ) : (
                        row.rightContent || "\u00A0"
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ── Unified diff view ──────────────────────────────────────────────

export function UnifiedDiffViewer({
  oldValue,
  newValue,
  contextLines = 3,
}: {
  oldValue: string;
  newValue: string;
  contextLines?: number;
}) {
  const rows = useMemo(() => buildRows(oldValue, newValue), [oldValue, newValue]);
  const collapsed = useMemo(() => collapseUnchanged(rows, contextLines), [rows, contextLines]);

  return (
    <div className="overflow-auto">
      <table className="w-full border-collapse text-xs" style={{ tableLayout: "fixed" }}>
        <colgroup>
          <col style={{ width: "36px" }} />
          <col style={{ width: "36px" }} />
          <col style={{ width: "20px" }} />
          <col />
        </colgroup>
        <tbody>
          {collapsed.map((item, i) => {
            if ("count" in item) {
              return (
                <tr key={`c-${i}`}>
                  <td colSpan={4} className="text-center py-1 text-xs text-muted-foreground bg-muted/30 border-y border-border">
                    {item.count} unchanged lines
                  </td>
                </tr>
              );
            }
            const row = item as DiffRow;
            const isModified = row.type === "modified";
            const wordSegs = isModified ? wordDiff(row.leftContent, row.rightContent) : null;

            if (isModified) {
              return (
                <React.Fragment key={i}>
                  <tr className="bg-red-50/80 dark:bg-red-950/20">
                    <td className={cn("select-none text-right px-1.5 py-px border-r border-border tabular-nums", GUTTER_BG.removed)}>{row.leftNum}</td>
                    <td className={cn("select-none text-right px-1.5 py-px border-r border-border tabular-nums", GUTTER_BG.removed)}></td>
                    <td className={cn("select-none text-center py-px", GUTTER_BG.removed)}>{MARKER.removed}</td>
                    <td className="px-2 py-px whitespace-pre-wrap break-words">
                      {wordSegs ? <WordHighlight segments={wordSegs.oldSegs} isRemoved /> : row.leftContent}
                    </td>
                  </tr>
                  <tr className="bg-green-50/80 dark:bg-green-950/20">
                    <td className={cn("select-none text-right px-1.5 py-px border-r border-border tabular-nums", GUTTER_BG.added)}></td>
                    <td className={cn("select-none text-right px-1.5 py-px border-r border-border tabular-nums", GUTTER_BG.added)}>{row.rightNum}</td>
                    <td className={cn("select-none text-center py-px", GUTTER_BG.added)}>{MARKER.added}</td>
                    <td className="px-2 py-px whitespace-pre-wrap break-words">
                      {wordSegs ? <WordHighlight segments={wordSegs.newSegs} isRemoved={false} /> : row.rightContent}
                    </td>
                  </tr>
                </React.Fragment>
              );
            }

            const type = row.type;
            return (
              <tr key={i} className={ROW_BG[type]}>
                <td className={cn("select-none text-right px-1.5 py-px border-r border-border tabular-nums", GUTTER_BG[type])}>{type !== "added" ? row.leftNum : ""}</td>
                <td className={cn("select-none text-right px-1.5 py-px border-r border-border tabular-nums", GUTTER_BG[type])}>{type !== "removed" ? row.rightNum : ""}</td>
                <td className={cn("select-none text-center py-px", GUTTER_BG[type])}>{MARKER[type]}</td>
                <td className="px-2 py-px whitespace-pre-wrap break-words">{row.leftContent || row.rightContent || "\u00A0"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
