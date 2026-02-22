import { create } from "zustand";
import type { Context } from "@/types";

interface ContextState {
  contexts: Context[];
  isLoading: boolean;
  error: string | null;
  editingContextId: string | null;
  confirmDeleteId: string | null;
  isCreating: boolean;

  setContexts: (contexts: Context[]) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setEditingContextId: (id: string | null) => void;
  setConfirmDeleteId: (id: string | null) => void;
  setIsCreating: (creating: boolean) => void;
}

export const useContextStore = create<ContextState>((set) => ({
  contexts: [],
  isLoading: false,
  error: null,
  editingContextId: null,
  confirmDeleteId: null,
  isCreating: false,

  setContexts: (contexts) => set({ contexts }),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),
  setEditingContextId: (editingContextId) => set({ editingContextId }),
  setConfirmDeleteId: (confirmDeleteId) => set({ confirmDeleteId }),
  setIsCreating: (isCreating) => set({ isCreating }),
}));
