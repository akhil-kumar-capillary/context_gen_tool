import { create } from "zustand";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import type { Context, AiGeneratedContext, LLMUsage } from "@/types";

interface ContextState {
  // Context list
  contexts: Context[];
  isLoading: boolean;
  error: string | null;

  // UI state
  editingContextId: string | null;
  confirmDeleteId: string | null;
  isCreating: boolean;

  // AI Generated (sanitize results)
  aiContexts: AiGeneratedContext[] | null;
  sanitizeUsage: LLMUsage | null;

  // CRUD actions
  fetchContexts: () => Promise<void>;
  createContext: (name: string, content: string, scope: string) => Promise<void>;
  updateContext: (contextId: string, name: string, content: string, scope: string) => Promise<void>;
  deleteContext: (contextId: string) => Promise<void>;
  bulkUpload: () => Promise<void>;

  // UI setters
  setEditingContextId: (id: string | null) => void;
  setConfirmDeleteId: (id: string | null) => void;
  setIsCreating: (creating: boolean) => void;
  setError: (error: string | null) => void;

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

export const useContextStore = create<ContextState>((set, get) => ({
  contexts: [],
  isLoading: false,
  error: null,
  editingContextId: null,
  confirmDeleteId: null,
  isCreating: false,
  aiContexts: null,
  sanitizeUsage: null,

  // --- CRUD ---

  fetchContexts: async () => {
    const { token, orgId } = useAuthStore.getState();
    if (!token || !orgId) return;

    set({ isLoading: true, error: null });
    try {
      const data = await apiClient.get<Context[] | { contexts: Context[] }>(
        `/api/contexts/list?org_id=${orgId}`,
        { token }
      );
      // Capillary API wraps in { status, contexts: [...] }
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

  deleteContext: async (contextId) => {
    const { token, orgId } = useAuthStore.getState();
    if (!token || !orgId) return;

    set({ isLoading: true, error: null });
    try {
      await apiClient.delete(
        `/api/contexts/delete?context_id=${contextId}&org_id=${orgId}`,
        { token }
      );
      set({ confirmDeleteId: null });
      await get().fetchContexts();
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : "Failed to delete context",
        isLoading: false,
      });
    }
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
      editingContextId: null,
      confirmDeleteId: null,
      isCreating: false,
      aiContexts: null,
      sanitizeUsage: null,
    }),

  // --- UI setters ---

  setEditingContextId: (editingContextId) => set({ editingContextId }),
  setConfirmDeleteId: (confirmDeleteId) => set({ confirmDeleteId }),
  setIsCreating: (isCreating) => set({ isCreating }),
  setError: (error) => set({ error }),

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
