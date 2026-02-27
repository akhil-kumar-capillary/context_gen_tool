import { create } from "zustand";

// ── Types ──

export interface ContextTreeNode {
  id: string;
  name: string;
  type: "root" | "cat" | "leaf";
  health: number;
  visibility: "public" | "private";
  children?: ContextTreeNode[];
  desc?: string;
  source?: string; // "databricks" | "config_apis" | "capillary" | "manual"
  source_doc_key?: string;
  used?: string; // last retrieved timestamp
  hits?: number; // retrieval count
  secrets?: Array<{
    key: string;
    scope: string;
    type: string;
    rotated?: string;
    usedBy?: string[];
  }>;
  secretRefs?: string[];
  attachments?: Array<{
    name: string;
    size: string;
    scanned: boolean;
    sensitive: boolean;
    by: string;
    at: string;
  }>;
  analysis?: {
    redundancy: {
      score: number;
      overlaps_with: string[];
      detail: string;
    };
    conflicts: Array<{
      with_node: string;
      description: string;
      severity: "low" | "medium" | "high";
    }>;
    suggestions: string[];
  };
}

export interface TreeRun {
  id: string;
  status: string;
  created_at: string | null;
  completed_at: string | null;
  input_context_count: number | null;
  input_sources?: Record<string, unknown[]>;
  model_used?: string;
  provider_used?: string;
  token_usage?: { input_tokens: number; output_tokens: number };
  error_message?: string | null;
  progress_data?: ProgressEntry[];
}

export interface ProgressEntry {
  phase: string;
  detail: string;
  status: string;
  error?: string;
}

export interface SyncResult {
  name: string;
  status: string;
  reason?: string;
}

// ── Store ──

interface ContextEngineState {
  // Tree runs
  treeRuns: TreeRun[];
  activeRunId: string | null;
  treeData: ContextTreeNode | null;

  // Generation
  isGenerating: boolean;
  generationProgress: ProgressEntry[];

  // UI state
  selectedNodeId: string | null;
  expandedNodes: Record<string, boolean>;
  isEditing: boolean;

  // Sync
  isSyncing: boolean;
  syncResults: SyncResult[] | null;

  // Loading
  isLoadingRuns: boolean;
  isLoadingTree: boolean;

  // Actions
  setTreeRuns: (runs: TreeRun[]) => void;
  setActiveRunId: (id: string | null) => void;
  setTreeData: (data: ContextTreeNode | null) => void;
  setIsGenerating: (v: boolean) => void;
  addProgress: (p: ProgressEntry) => void;
  clearProgress: () => void;
  selectNode: (id: string | null) => void;
  toggleExpand: (id: string) => void;
  expandAll: () => void;
  collapseAll: () => void;
  setIsEditing: (v: boolean) => void;
  updateNode: (nodeId: string, updates: Partial<ContextTreeNode>) => void;
  deleteNode: (nodeId: string) => void;
  addNode: (parentId: string, node: Partial<ContextTreeNode>) => void;
  setIsSyncing: (v: boolean) => void;
  setSyncResults: (results: SyncResult[] | null) => void;
  setIsLoadingRuns: (v: boolean) => void;
  setIsLoadingTree: (v: boolean) => void;
  reset: () => void;
}

// ── Tree helpers ──

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

function removeNode(tree: ContextTreeNode, id: string): boolean {
  const children = tree.children || [];
  for (let i = 0; i < children.length; i++) {
    if (children[i].id === id) {
      children.splice(i, 1);
      return true;
    }
    if (removeNode(children[i], id)) return true;
  }
  return false;
}

function collectAllIds(node: ContextTreeNode): string[] {
  const ids = [node.id];
  for (const child of node.children || []) {
    ids.push(...collectAllIds(child));
  }
  return ids;
}

const initialState = {
  treeRuns: [] as TreeRun[],
  activeRunId: null as string | null,
  treeData: null as ContextTreeNode | null,
  isGenerating: false,
  generationProgress: [] as ProgressEntry[],
  selectedNodeId: null as string | null,
  expandedNodes: {} as Record<string, boolean>,
  isEditing: false,
  isSyncing: false,
  syncResults: null as SyncResult[] | null,
  isLoadingRuns: false,
  isLoadingTree: false,
};

export const useContextEngineStore = create<ContextEngineState>((set, get) => ({
  ...initialState,

  setTreeRuns: (runs) => set({ treeRuns: runs }),
  setActiveRunId: (id) => set({ activeRunId: id }),
  setTreeData: (data) => {
    // Auto-expand root and first-level categories on load
    const expanded: Record<string, boolean> = {};
    if (data) {
      expanded[data.id] = true;
      for (const child of data.children || []) {
        expanded[child.id] = true;
      }
    }
    set({ treeData: data, expandedNodes: expanded });
  },

  setIsGenerating: (v) => set({ isGenerating: v }),
  addProgress: (p) =>
    set((s) => {
      const list = [...s.generationProgress];

      // Deduplicate "complete" — only allow one entry
      if (p.phase === "complete") {
        if (list.some((e) => e.phase === "complete")) return {};
        return { generationProgress: [...list, p] };
      }

      // "done" or "failed" → remove all "running" entries for the same phase, then append
      if (p.status === "done" || p.status === "failed") {
        const filtered = list.filter(
          (e) => !(e.phase === p.phase && e.status === "running")
        );
        return { generationProgress: [...filtered, p] };
      }

      // "running" → replace the last "running" entry for the same phase (streaming updates)
      if (p.status === "running") {
        const lastIdx = list.findLastIndex(
          (e) => e.phase === p.phase && e.status === "running"
        );
        if (lastIdx !== -1) {
          list[lastIdx] = p;
          return { generationProgress: list };
        }
        return { generationProgress: [...list, p] };
      }

      // Fallback: append
      return { generationProgress: [...list, p] };
    }),
  clearProgress: () => set({ generationProgress: [] }),

  selectNode: (id) => set({ selectedNodeId: id }),
  toggleExpand: (id) =>
    set((s) => ({
      expandedNodes: {
        ...s.expandedNodes,
        [id]: !s.expandedNodes[id],
      },
    })),
  expandAll: () => {
    const { treeData } = get();
    if (!treeData) return;
    const all = collectAllIds(treeData);
    const expanded: Record<string, boolean> = {};
    for (const id of all) expanded[id] = true;
    set({ expandedNodes: expanded });
  },
  collapseAll: () => set({ expandedNodes: {} }),

  setIsEditing: (v) => set({ isEditing: v }),

  updateNode: (nodeId, updates) => {
    const { treeData } = get();
    if (!treeData) return;
    // Deep clone to avoid mutation
    const clone = JSON.parse(JSON.stringify(treeData)) as ContextTreeNode;
    const node = findNode(clone, nodeId);
    if (node) {
      Object.assign(node, updates);
      set({ treeData: clone });
    }
  },

  deleteNode: (nodeId) => {
    const { treeData, selectedNodeId } = get();
    if (!treeData || nodeId === "root") return;
    const clone = JSON.parse(JSON.stringify(treeData)) as ContextTreeNode;
    removeNode(clone, nodeId);
    set({
      treeData: clone,
      selectedNodeId: selectedNodeId === nodeId ? null : selectedNodeId,
    });
  },

  addNode: (parentId, node) => {
    const { treeData } = get();
    if (!treeData) return;
    const clone = JSON.parse(JSON.stringify(treeData)) as ContextTreeNode;
    const parent = findNode(clone, parentId);
    if (parent) {
      if (!parent.children) parent.children = [];
      const newNode: ContextTreeNode = {
        id: node.id || `custom_${Date.now()}`,
        name: node.name || "New Node",
        type: node.type || "leaf",
        health: node.health ?? 80,
        visibility: node.visibility || "public",
        desc: node.desc || "",
        source: "manual",
        ...node,
      };
      parent.children.push(newNode);
      set({ treeData: clone });
    }
  },

  setIsSyncing: (v) => set({ isSyncing: v }),
  setSyncResults: (results) => set({ syncResults: results }),
  setIsLoadingRuns: (v) => set({ isLoadingRuns: v }),
  setIsLoadingTree: (v) => set({ isLoadingTree: v }),

  reset: () => set(initialState),
}));
