"use client";

import { useState } from "react";
import {
  X,
  Globe,
  Lock,
  Key,
  Paperclip,
  FileText,
  AlertTriangle,
  Copy,
  Check,
  Pencil,
  Save,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  useContextEngineStore,
  type ContextTreeNode,
} from "@/stores/context-engine-store";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import { MarkdownRenderer } from "@/components/chat/markdown-renderer";

// ── Helpers ──

function healthColors(score: number) {
  if (score >= 80)
    return { bg: "bg-green-50", text: "text-green-700", dot: "bg-green-500" };
  if (score >= 60)
    return { bg: "bg-amber-50", text: "text-amber-700", dot: "bg-amber-500" };
  return { bg: "bg-red-50", text: "text-red-700", dot: "bg-red-500" };
}

function findNode(
  tree: ContextTreeNode,
  id: string
): ContextTreeNode | null {
  if (tree.id === id) return tree;
  for (const child of tree.children || []) {
    const found = findNode(child, id);
    if (found) return found;
  }
  return null;
}

// ── NodeDetail ──

export function NodeDetail() {
  const { token } = useAuthStore();
  const {
    treeData,
    selectedNodeId,
    activeRunId,
    isEditing,
    selectNode,
    setIsEditing,
    updateNode,
  } = useContextEngineStore();

  const [editedDesc, setEditedDesc] = useState("");
  const [copied, setCopied] = useState(false);

  if (!treeData || !selectedNodeId) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-gray-400">
        Select a node to view details
      </div>
    );
  }

  // Handle secret selection (delegated to SecretDetail)
  if (selectedNodeId.startsWith("secret:")) {
    return null; // SecretDetail handles this
  }

  const node = findNode(treeData, selectedNodeId);
  if (!node) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-gray-400">
        Node not found
      </div>
    );
  }

  const h = healthColors(node.health);
  const isLeaf = node.type === "leaf";
  const analysis = node.analysis;
  const secretRefs = node.secretRefs || [];
  const attachments = node.attachments || [];

  const handleStartEdit = () => {
    setEditedDesc(node.desc || "");
    setIsEditing(true);
  };

  const handleSaveEdit = async () => {
    updateNode(node.id, { desc: editedDesc });
    setIsEditing(false);

    // Persist to backend
    if (activeRunId && token) {
      try {
        await apiClient.put(
          `/api/context-engine/runs/${activeRunId}/node/${node.id}`,
          { desc: editedDesc },
          { token }
        );
      } catch {
        // Silently fail — local update already applied
      }
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(node.desc || "");
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
        <div className="flex items-center gap-2 min-w-0">
          <h3 className="text-sm font-semibold text-gray-900 truncate">
            {node.name}
          </h3>
          <span className="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-500 uppercase">
            {node.type}
          </span>
          {node.visibility === "private" ? (
            <Lock className="h-3 w-3 text-gray-400 shrink-0" />
          ) : (
            <Globe className="h-3 w-3 text-gray-300 shrink-0" />
          )}
        </div>
        <button
          onClick={() => selectNode(null)}
          className="shrink-0 rounded p-1 hover:bg-gray-100"
        >
          <X className="h-4 w-4 text-gray-400" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Health score */}
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">Health</span>
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-bold",
              h.bg,
              h.text
            )}
          >
            <span className={cn("h-2 w-2 rounded-full", h.dot)} />
            {node.health}/100
          </span>
        </div>

        {/* Source */}
        {node.source && (
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-500">Source</span>
            <span className="text-xs text-gray-700">{node.source}</span>
            {node.source_doc_key && (
              <span className="font-mono text-[10px] text-gray-400">
                ({node.source_doc_key})
              </span>
            )}
          </div>
        )}

        {/* Usage */}
        {(node.used || node.hits) && (
          <div className="flex items-center gap-4">
            {node.used && (
              <span className="text-xs text-gray-400">
                Last used: {node.used}
              </span>
            )}
            {node.hits && (
              <span className="text-xs text-gray-400">
                {node.hits} retrievals
              </span>
            )}
          </div>
        )}

        {/* Content (for leaf nodes) */}
        {isLeaf && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-gray-500">
                Content
              </span>
              <div className="flex items-center gap-1">
                <button
                  onClick={handleCopy}
                  className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                  title="Copy content"
                >
                  {copied ? (
                    <Check className="h-3.5 w-3.5 text-green-500" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" />
                  )}
                </button>
                {!isEditing ? (
                  <button
                    onClick={handleStartEdit}
                    className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                    title="Edit content"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                ) : (
                  <button
                    onClick={handleSaveEdit}
                    className="rounded p-1 text-green-500 hover:bg-green-50"
                    title="Save changes"
                  >
                    <Save className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>
            {isEditing ? (
              <textarea
                value={editedDesc}
                onChange={(e) => setEditedDesc(e.target.value)}
                className="w-full rounded-lg border border-gray-200 bg-white p-3 text-xs font-mono text-gray-700 min-h-[200px] focus:border-violet-300 focus:outline-none focus:ring-1 focus:ring-violet-300"
              />
            ) : node.desc ? (
              <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 max-h-[400px] overflow-y-auto">
                <MarkdownRenderer
                  content={node.desc}
                  className="prose-compact text-xs text-gray-700 [&_p]:text-xs [&_p]:mb-1.5 [&_li]:text-xs [&_code]:text-[11px] [&_h1]:text-sm [&_h2]:text-xs [&_h3]:text-xs [&_pre]:my-2 [&_table]:text-xs [&_th]:text-[10px] [&_th]:px-2 [&_th]:py-1 [&_td]:text-xs [&_td]:px-2 [&_td]:py-1 [&_ul]:text-xs [&_ol]:text-xs [&_blockquote]:text-xs"
                />
              </div>
            ) : (
              <p className="text-xs text-gray-400 italic">No content</p>
            )}
          </div>
        )}

        {/* Analysis section */}
        {analysis && (
          <div className="space-y-3">
            <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wider">
              Analysis
            </h4>

            {/* Redundancy */}
            {analysis.redundancy && analysis.redundancy.score > 0 && (
              <div className="rounded-lg bg-amber-50 border border-amber-200 p-3">
                <div className="flex items-center gap-2 mb-1">
                  <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
                  <span className="text-xs font-medium text-amber-800">
                    Redundancy: {analysis.redundancy.score}%
                  </span>
                </div>
                <p className="text-[11px] text-amber-700">
                  {analysis.redundancy.detail}
                </p>
                {analysis.redundancy.overlaps_with.length > 0 && (
                  <p className="text-[11px] text-amber-600 mt-1">
                    Overlaps with:{" "}
                    {analysis.redundancy.overlaps_with.join(", ")}
                  </p>
                )}
              </div>
            )}

            {/* Conflicts */}
            {analysis.conflicts && analysis.conflicts.length > 0 && (
              <div className="space-y-2">
                {analysis.conflicts.map((c, i) => (
                  <div
                    key={i}
                    className={cn(
                      "rounded-lg border p-3",
                      c.severity === "high"
                        ? "bg-red-50 border-red-200"
                        : c.severity === "medium"
                          ? "bg-amber-50 border-amber-200"
                          : "bg-yellow-50 border-yellow-200"
                    )}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <AlertTriangle
                        className={cn(
                          "h-3.5 w-3.5",
                          c.severity === "high"
                            ? "text-red-600"
                            : "text-amber-600"
                        )}
                      />
                      <span
                        className={cn(
                          "text-xs font-medium",
                          c.severity === "high"
                            ? "text-red-800"
                            : "text-amber-800"
                        )}
                      >
                        Conflict ({c.severity}) with {c.with_node}
                      </span>
                    </div>
                    <p className="text-[11px] text-gray-600">
                      {c.description}
                    </p>
                  </div>
                ))}
              </div>
            )}

            {/* Suggestions */}
            {analysis.suggestions && analysis.suggestions.length > 0 && (
              <div className="rounded-lg bg-blue-50 border border-blue-200 p-3">
                <span className="text-xs font-medium text-blue-800">
                  Suggestions
                </span>
                <ul className="mt-1 space-y-1">
                  {analysis.suggestions.map((s, i) => (
                    <li key={i} className="text-[11px] text-blue-700">
                      &bull; {s}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Secret references */}
        {secretRefs.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-2">
              Secret References
            </h4>
            <div className="space-y-1">
              {secretRefs.map((ref) => (
                <div
                  key={ref}
                  className="flex items-center gap-2 rounded bg-amber-50 px-2.5 py-1.5"
                >
                  <Key className="h-3 w-3 text-amber-600" />
                  <span className="font-mono text-xs text-amber-800">{`{{${ref}}}`}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Attachments */}
        {attachments.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-2">
              Attachments
            </h4>
            <div className="space-y-1.5">
              {attachments.map((a) => (
                <div
                  key={a.name}
                  className="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2"
                >
                  <FileText
                    className={cn(
                      "h-4 w-4 shrink-0",
                      a.sensitive ? "text-red-500" : "text-indigo-500"
                    )}
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-gray-700 truncate">{a.name}</p>
                    <p className="text-[10px] text-gray-400">
                      {a.size} &middot; by {a.by} &middot; {a.at}
                    </p>
                  </div>
                  {a.sensitive && (
                    <span className="shrink-0 rounded bg-red-50 px-1.5 py-0.5 text-[9px] text-red-600 font-medium">
                      sensitive
                    </span>
                  )}
                  {a.scanned && !a.sensitive && (
                    <span className="shrink-0 rounded bg-green-50 px-1.5 py-0.5 text-[9px] text-green-600 font-medium">
                      scanned
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Category children count */}
        {!isLeaf && node.children && (
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-500">Children</span>
            <span className="text-xs text-gray-700">
              {node.children.length} node
              {node.children.length !== 1 ? "s" : ""}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
