import { create } from "zustand";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import type { Context, AiGeneratedContext, LLMUsage } from "@/types";

export type ContextStatusFilter = "active" | "archived" | "all";

interface ContextState {
  // Context list
  contexts: Context[];
  isLoading: boolean;
  error: string | null;
  statusFilter: ContextStatusFilter;

  // UI state
  editingContextId: string | null;
  confirmArchiveId: string | null;
  actionLoadingId: string | null;
  isCreating: boolean;

  // AI Generated (sanitize results)
  aiContexts: AiGeneratedContext[] | null;
  sanitizeUsage: LLMUsage | null;

  // CRUD actions
  fetchContexts: () => Promise<void>;
  createContext: (name: string, content: string, scope: string) => Promise<void>;
  updateContext: (contextId: string, name: string, content: string, scope: string) => Promise<void>;
  archiveContext: (contextId: string) => Promise<void>;
  restoreContext: (contextId: string) => Promise<void>;
  bulkUpload: () => Promise<void>;

  // UI setters
  setEditingContextId: (id: string | null) => void;
  setConfirmArchiveId: (id: string | null) => void;
  setIsCreating: (creating: boolean) => void;
  setError: (error: string | null) => void;
  setStatusFilter: (filter: ContextStatusFilter) => void;

  // Reset
  reset: () => void;

  // AI Generated actions
  setAiContexts: (contexts: AiGeneratedContext[] | null) => void;
  setSanitizeUsage: (usage: LLMUsage | null) => void;
  updateAiContext: (id: string, updates: Partial<Pick<AiGeneratedContext, "name" | "content" | "scope">>) => void;
  removeAiContext: (id: string) => void;
  setAiContextUploadStatus: (id: string, status: NonNullable<AiGeneratedContext["uploadStatus"]>, error?: string) => void;
  uploadSingleAiContext: (aiCtx: AiGeneratedContext) => Promise<void>;
  dismissAiContexts: () => void;
}

function applyStatusFilter(
  contexts: Context[],
  filter: ContextStatusFilter
): Context[] {
  if (filter === "all") return contexts;
  if (filter === "archived") return contexts.filter((c) => c.is_active === false);
  return contexts.filter((c) => c.is_active !== false);
}

export const useContextStore = create<ContextState>((set, get) => ({
  contexts: [],
  isLoading: false,
  error: null,
  statusFilter: "active",
  editingContextId: null,
  confirmArchiveId: null,
  actionLoadingId: null,
  isCreating: false,
  aiContexts: null,
  sanitizeUsage: null,

  // --- CRUD ---

  fetchContexts: async () => {
    const { token, orgId } = useAuthStore.getState();
    if (!token || !orgId) return;

    set({ isLoading: true, error: null });
    try {
      const { statusFilter } = get();
      const params = new URLSearchParams({ org_id: String(orgId) });
      if (statusFilter === "active") params.set("is_active", "true");
      else if (statusFilter === "archived") params.set("is_active", "false");

      const data = await apiClient.get<Context[] | { contexts: Context[] }>(
        `/api/contexts/list?${params}`,
        { token }
      );
      const list = Array.isArray(data) ? data : (data?.contexts ?? []);
      set({ contexts: list, isLoading: false });
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : "Failed to fetch contexts",
        isLoading: false,
      });
    }
  },

  createContext: async (name, content, scope) => {
    const { token, orgId } = useAuthStore.getState();
    if (!token || !orgId) return;

    set({ isLoading: true, error: null });
    try {
      await apiClient.post(
        `/api/contexts/upload?org_id=${orgId}`,
        { name, content, scope },
        { token }
      );
      set({ isCreating: false });
      await get().fetchContexts();
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : "Failed to create context",
        isLoading: false,
      });
      throw err;
    }
  },

  updateContext: async (contextId, name, content, scope) => {
    const { token, orgId } = useAuthStore.getState();
    if (!token || !orgId) return;

    set({ isLoading: true, error: null });
    try {
      await apiClient.put(
        `/api/contexts/update?org_id=${orgId}`,
        { context_id: contextId, name, content, scope },
        { token }
      );
      set({ editingContextId: null });
      await get().fetchContexts();
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : "Failed to update context",
        isLoading: false,
      });
      throw err;
    }
  },

  archiveContext: async (contextId) => {
    const { token, orgId } = useAuthStore.getState();
    if (!token || !orgId || get().actionLoadingId) return;

    set({ actionLoadingId: contextId, error: null });
    try {
      await apiClient.put(
        `/api/contexts/archive?context_id=${contextId}&org_id=${orgId}`,
        {},
        { token }
      );
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : "Failed to archive context",
        actionLoadingId: null,
        confirmArchiveId: null,
      });
      return;
    }
    // Optimistic local update, then background refetch
    set((state) => ({
      confirmArchiveId: null,
      actionLoadingId: null,
      contexts: applyStatusFilter(
        state.contexts.map((c) =>
          c.id === contextId ? { ...c, is_active: false } : c
        ),
        get().statusFilter
      ),
    }));
    get().fetchContexts();
  },

  restoreContext: async (contextId) => {
    const { token, orgId } = useAuthStore.getState();
    if (!token || !orgId || get().actionLoadingId) return;

    set({ actionLoadingId: contextId, error: null });
    try {
      await apiClient.put(
        `/api/contexts/restore?context_id=${contextId}&org_id=${orgId}`,
        {},
        { token }
      );
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : "Failed to restore context",
        actionLoadingId: null,
      });
      return;
    }
    // Optimistic local update, then background refetch
    set((state) => ({
      actionLoadingId: null,
      contexts: applyStatusFilter(
        state.contexts.map((c) =>
          c.id === contextId ? { ...c, is_active: true } : c
        ),
        get().statusFilter
      ),
    }));
    get().fetchContexts();
  },

  bulkUpload: async () => {
    const { token, orgId } = useAuthStore.getState();
    const { aiContexts, contexts } = get();
    if (!token || !orgId || !aiContexts) return;

    // Build existing name map for conflict detection
    const existingNameMap: Record<string, string> = {};
    contexts.forEach((ctx) => {
      existingNameMap[ctx.name] = ctx.id;
    });

    // Filter only contexts that haven't been uploaded yet
    const toUpload = aiContexts.filter(
      (c) => c.uploadStatus !== "success" && c.uploadStatus !== "uploading"
    );

    // Mark all as uploading
    for (const ctx of toUpload) {
      get().setAiContextUploadStatus(ctx.id, "uploading");
    }

    try {
      const result = await apiClient.post<{
        results: Array<{ name: string; status: string; error?: string }>;
      }>(
        `/api/contexts/bulk-upload?org_id=${orgId}`,
        {
          contexts: toUpload.map((c) => ({
            name: c.name,
            content: c.content,
            scope: c.scope,
          })),
          existing_name_map: existingNameMap,
        },
        { token }
      );

      // Update individual upload statuses
      for (const r of result.results) {
        const aiCtx = aiContexts.find((c) => c.name === r.name);
        if (aiCtx) {
          get().setAiContextUploadStatus(
            aiCtx.id,
            r.status === "error" ? "error" : "success",
            r.status === "error" ? r.error : undefined
          );
        }
      }

      // Refresh context list
      await get().fetchContexts();
    } catch (err) {
      // Mark all as failed
      for (const ctx of toUpload) {
        get().setAiContextUploadStatus(ctx.id, "error", "Upload failed");
      }
    }
  },

  // --- Reset ---

  reset: () =>
    set({
      contexts: [],
      isLoading: false,
      error: null,
      statusFilter: "active",
      editingContextId: null,
      confirmArchiveId: null,
      actionLoadingId: null,
      isCreating: false,
      aiContexts: null,
      sanitizeUsage: null,
    }),

  // --- UI setters ---

  setEditingContextId: (editingContextId) => set({ editingContextId }),
  setConfirmArchiveId: (confirmArchiveId) => set({ confirmArchiveId }),
  setIsCreating: (isCreating) => set({ isCreating }),
  setError: (error) => set({ error }),
  setStatusFilter: (statusFilter) => set({ statusFilter }),

  // --- AI Generated ---

  setAiContexts: (aiContexts) => set({ aiContexts }),
  setSanitizeUsage: (sanitizeUsage) => set({ sanitizeUsage }),

  updateAiContext: (id, updates) =>
    set((state) => ({
      aiContexts: state.aiContexts?.map((c) =>
        c.id === id ? { ...c, ...updates } : c
      ) ?? null,
    })),

  removeAiContext: (id) =>
    set((state) => ({
      aiContexts: state.aiContexts?.filter((c) => c.id !== id) ?? null,
    })),

  setAiContextUploadStatus: (id, status, error) =>
    set((state) => ({
      aiContexts: state.aiContexts?.map((c) =>
        c.id === id ? { ...c, uploadStatus: status, error } : c
      ) ?? null,
    })),

  uploadSingleAiContext: async (aiCtx) => {
    const { token, orgId } = useAuthStore.getState();
    const { contexts } = get();
    if (!token || !orgId) return;

    get().setAiContextUploadStatus(aiCtx.id, "uploading");

    // Check if context with same name already exists
    const existing = contexts.find((c) => c.name === aiCtx.name);

    try {
      if (existing) {
        await apiClient.put(
          `/api/contexts/update?org_id=${orgId}`,
          {
            context_id: existing.id,
            name: aiCtx.name,
            content: aiCtx.content,
            scope: aiCtx.scope,
          },
          { token }
        );
      } else {
        await apiClient.post(
          `/api/contexts/upload?org_id=${orgId}`,
          { name: aiCtx.name, content: aiCtx.content, scope: aiCtx.scope },
          { token }
        );
      }
      get().setAiContextUploadStatus(aiCtx.id, "success");
      await get().fetchContexts();
    } catch (err) {
      get().setAiContextUploadStatus(
        aiCtx.id,
        "error",
        err instanceof Error ? err.message : "Upload failed"
      );
    }
  },

  dismissAiContexts: () => set({ aiContexts: null, sanitizeUsage: null }),
}));
