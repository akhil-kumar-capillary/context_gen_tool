import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { LLMProvider } from "@/types";

interface SettingsState {
  provider: LLMProvider;
  model: string;
  blueprintText: string | null;

  setProvider: (provider: LLMProvider) => void;
  setModel: (model: string) => void;
  setBlueprintText: (text: string | null) => void;
}

export const ANTHROPIC_MODELS = [
  { id: "claude-sonnet-4-5-20250929", label: "Claude Sonnet 4.5" },
  { id: "claude-opus-4-6", label: "Claude Opus 4.6" },
  { id: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5" },
] as const;

export const OPENAI_MODELS = [
  { id: "gpt-4o", label: "GPT-4o" },
  { id: "gpt-4o-mini", label: "GPT-4o Mini" },
  { id: "o1", label: "o1" },
] as const;

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      provider: "anthropic",
      model: "claude-sonnet-4-5-20250929",
      blueprintText: null,

      setProvider: (provider) => {
        const defaultModel =
          provider === "anthropic"
            ? "claude-sonnet-4-5-20250929"
            : "gpt-4o";
        set({ provider, model: defaultModel });
      },
      setModel: (model) => set({ model }),
      setBlueprintText: (blueprintText) => set({ blueprintText }),
    }),
    {
      name: "aira-settings",
    }
  )
);
