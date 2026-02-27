"use client";

import { Key, Shield, X } from "lucide-react";
import {
  useContextEngineStore,
  type ContextTreeNode,
} from "@/stores/context-engine-store";

// ── Helpers ──

interface SecretInfo {
  key: string;
  scope: string;
  type: string;
  rotated?: string;
  usedBy?: string[];
}

function findSecretInTree(
  tree: ContextTreeNode,
  secretKey: string
): SecretInfo | null {
  const secrets = tree.secrets || [];
  for (const s of secrets) {
    if (s.key === secretKey) return s;
  }
  for (const child of tree.children || []) {
    const found = findSecretInTree(child, secretKey);
    if (found) return found;
  }
  return null;
}

// ── SecretDetail ──

export function SecretDetail() {
  const { treeData, selectedNodeId, selectNode } = useContextEngineStore();

  if (
    !treeData ||
    !selectedNodeId ||
    !selectedNodeId.startsWith("secret:")
  ) {
    return null;
  }

  const secretKey = selectedNodeId.replace("secret:", "");
  const secret = findSecretInTree(treeData, secretKey);

  if (!secret) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-gray-400">
        Secret not found
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
        <div className="flex items-center gap-2">
          <Key className="h-4 w-4 text-amber-600" />
          <h3 className="text-sm font-semibold text-amber-900">
            Secret Detail
          </h3>
        </div>
        <button
          onClick={() => selectNode(null)}
          className="rounded p-1 hover:bg-gray-100"
        >
          <X className="h-4 w-4 text-gray-400" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Key name */}
        <div>
          <span className="text-xs text-gray-500 block mb-1">Key Name</span>
          <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2">
            <span className="font-mono text-sm text-amber-800 font-medium">
              {`{{${secret.key}}}`}
            </span>
          </div>
        </div>

        {/* Masked value */}
        <div>
          <span className="text-xs text-gray-500 block mb-1">Value</span>
          <div className="rounded-lg bg-gray-50 border border-gray-200 px-3 py-2">
            <span className="font-mono text-sm text-gray-400">
              ********************************
            </span>
          </div>
        </div>

        {/* Scope */}
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">Scope</span>
          <span className="text-xs text-gray-700">{secret.scope}</span>
        </div>

        {/* Type */}
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">Type</span>
          <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
            {secret.type}
          </span>
        </div>

        {/* Rotation */}
        {secret.rotated && (
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-500">Last Rotated</span>
            <span className="text-xs text-gray-700">{secret.rotated}</span>
          </div>
        )}

        {/* Used by */}
        {secret.usedBy && secret.usedBy.length > 0 && (
          <div>
            <span className="text-xs text-gray-500 block mb-1.5">
              Used By
            </span>
            <div className="space-y-1">
              {secret.usedBy.map((nodeId) => (
                <button
                  key={nodeId}
                  onClick={() => selectNode(nodeId)}
                  className="w-full text-left rounded bg-gray-50 border border-gray-200 px-2.5 py-1.5 text-xs text-violet-700 hover:bg-violet-50 hover:border-violet-200 transition-colors"
                >
                  {nodeId}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Security note */}
        <div className="rounded-lg bg-blue-50 border border-blue-200 p-3">
          <div className="flex items-start gap-2">
            <Shield className="h-4 w-4 text-blue-500 shrink-0 mt-0.5" />
            <div>
              <p className="text-xs font-medium text-blue-800">
                Security Note
              </p>
              <p className="text-[11px] text-blue-600 mt-1">
                Only the key name{" "}
                <span className="font-mono">{`{{${secret.key}}}`}</span> is
                passed to the LLM. The actual secret value is never included
                in any AI context or prompt.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
