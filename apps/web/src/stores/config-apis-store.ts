import { create } from "zustand";

// ── Types ──

export interface CategorySchema {
  id: string;
  label: string;
  description: string;
  params_schema: ParamSchema[];
}

export interface ParamSchema {
  key: string;
  label: string;
  type: "number" | "text" | "boolean" | "select" | "multi_select";
  required: boolean;
  default?: unknown;
  help?: string;
  options?: string[];
}

export interface APICallResult {
  api_name: string;
  status: "success" | "error";
  http_status?: number | null;
  item_count?: number | null;
  error_message?: string | null;
  duration_ms: number;
  response_bytes?: number | null;
}

export interface ExtractionRun {
  id: string;
  user_id: number;
  org_id: number;
  host: string;
  categories: string[];
  category_params: Record<string, Record<string, unknown>>;
  stats: Record<string, { apis: number; success: number; failed: number; duration_s: number }>;
  api_call_log?: Record<string, APICallResult[]> | null;
  status: string;
  error_message?: string;
  started_at?: string;
  completed_at?: string;
  created_at?: string;
}

export interface AnalysisRun {
  id: string;
  run_id: string;
  org_id: number;
  version: number;
  status: string;
  error_message?: string;
  created_at?: string;
  completed_at?: string;
}

export interface ContextDoc {
  id: number;
  doc_key: string;
  doc_name?: string;
  doc_content?: string;
  model_used?: string;
  provider_used?: string;
  token_count?: number;
  status: string;
  created_at?: string;
}

export interface ProgressEvent {
  type: string;
  channel?: string;
  phase?: string;
  status?: string;
  completed?: number;
  total?: number;
  detail?: string;
  error?: string;
  [key: string]: unknown;
}

// ── NEW: Review & Select types ──

export interface ConfigFingerprint {
  id: string;
  category: string;
  entity_type: string;
  entity_subtype: string;
  entity_name: string;
  entity_id?: unknown;
  field_names: string[];
  nested_objects: string[];
  field_types: Record<string, string>;
  field_values: Record<string, unknown>;
  depth: number;
  total_fields: number;
  has_rules: boolean;
  has_conditions: boolean;
  has_workflow: boolean;
  raw_object: Record<string, unknown>;
}

export interface ConfigCluster {
  entity_type: string;
  entity_subtype: string;
  count: number;
  template_ids: string[];
  templates: Record<string, unknown>[];
  common_fields: string[];
  field_value_dist: Record<string, Record<string, number>>;
  naming_pattern: string;
  avg_depth: number;
  avg_fields: number;
  structural_features: {
    has_rules: number;
    has_conditions: number;
    has_workflow: number;
  };
}

export interface PayloadPreview {
  doc_name: string;
  focus: string;
  payload: string;
  chars: number;
  est_tokens: number;
}

export type PipelineStep = "extract" | "analyze" | "review" | "generate";

// ── Store ──

interface ConfigApisState {
  // Active step
  activeStep: PipelineStep;

  // Categories
  categories: CategorySchema[];
  selectedCategories: string[];
  categoryParams: Record<string, Record<string, unknown>>;

  // Extraction
  extractionRuns: ExtractionRun[];
  activeExtractionId: string | null;
  extractionProgress: ProgressEvent[];
  isExtracting: boolean;

  // Analysis
  analysisRuns: AnalysisRun[];
  activeAnalysisId: string | null;
  analysisProgress: ProgressEvent[];
  isAnalyzing: boolean;

  // Review & Select (NEW)
  fingerprints: ConfigFingerprint[] | null;
  counters: Record<string, unknown> | null;
  clusters: ConfigCluster[] | null;
  entityTypeCounts: Record<string, number> | null;
  inclusions: Record<string, Record<string, boolean>>;
  customPrompts: Record<string, string>;
  defaultPrompts: Record<string, string>;
  tokenBudgets: Record<string, number>;
  docNames: Record<string, string>;
  payloadPreviews: Record<string, PayloadPreview> | null;
  isLoadingReviewData: boolean;
  isLoadingPayloads: boolean;

  // Generation
  contextDocs: ContextDoc[];
  generationProgress: ProgressEvent[];
  isGenerating: boolean;

  // Call log viewer
  extractionCallLog: Record<string, APICallResult[]> | null;
  rawApiResponse: unknown | null;
  isLoadingCallLog: boolean;
  isLoadingRawResponse: boolean;

  // Loading
  isLoadingRuns: boolean;
  isLoadingAnalysis: boolean;
  isLoadingDocs: boolean;

  // Actions
  setActiveStep: (step: PipelineStep) => void;

  setCategories: (cats: CategorySchema[]) => void;
  setSelectedCategories: (ids: string[]) => void;
  toggleCategory: (id: string) => void;
  setCategoryParam: (catId: string, key: string, value: unknown) => void;

  setExtractionRuns: (runs: ExtractionRun[]) => void;
  setActiveExtractionId: (id: string | null) => void;
  addExtractionProgress: (event: ProgressEvent) => void;
  clearExtractionProgress: () => void;
  setIsExtracting: (v: boolean) => void;

  setAnalysisRuns: (runs: AnalysisRun[]) => void;
  setActiveAnalysisId: (id: string | null) => void;
  addAnalysisProgress: (event: ProgressEvent) => void;
  clearAnalysisProgress: () => void;
  setIsAnalyzing: (v: boolean) => void;

  // Review & Select actions
  setFingerprints: (fps: ConfigFingerprint[] | null) => void;
  setCounters: (c: Record<string, unknown> | null) => void;
  setClusters: (cl: ConfigCluster[] | null) => void;
  setEntityTypeCounts: (etc: Record<string, number> | null) => void;
  setInclusion: (docKey: string, path: string, value: boolean) => void;
  setAllInclusions: (docKey: string, paths: string[], value: boolean) => void;
  setCustomPrompt: (docKey: string, prompt: string) => void;
  resetPrompt: (docKey: string) => void;
  setDefaultPrompts: (p: Record<string, string>) => void;
  setTokenBudgets: (b: Record<string, number>) => void;
  setDocNames: (n: Record<string, string>) => void;
  setPayloadPreviews: (p: Record<string, PayloadPreview> | null) => void;
  setIsLoadingReviewData: (v: boolean) => void;
  setIsLoadingPayloads: (v: boolean) => void;

  setContextDocs: (docs: ContextDoc[]) => void;
  addGenerationProgress: (event: ProgressEvent) => void;
  clearGenerationProgress: () => void;
  setIsGenerating: (v: boolean) => void;

  setExtractionCallLog: (log: Record<string, APICallResult[]> | null) => void;
  setRawApiResponse: (data: unknown | null) => void;
  setIsLoadingCallLog: (v: boolean) => void;
  setIsLoadingRawResponse: (v: boolean) => void;

  setIsLoadingRuns: (v: boolean) => void;
  setIsLoadingAnalysis: (v: boolean) => void;
  setIsLoadingDocs: (v: boolean) => void;

  reset: () => void;
}

const initialState = {
  activeStep: "extract" as PipelineStep,
  categories: [] as CategorySchema[],
  selectedCategories: [] as string[],
  categoryParams: {} as Record<string, Record<string, unknown>>,
  extractionRuns: [] as ExtractionRun[],
  activeExtractionId: null as string | null,
  extractionProgress: [] as ProgressEvent[],
  isExtracting: false,
  analysisRuns: [] as AnalysisRun[],
  activeAnalysisId: null as string | null,
  analysisProgress: [] as ProgressEvent[],
  isAnalyzing: false,
  // Review & Select
  fingerprints: null as ConfigFingerprint[] | null,
  counters: null as Record<string, unknown> | null,
  clusters: null as ConfigCluster[] | null,
  entityTypeCounts: null as Record<string, number> | null,
  inclusions: {} as Record<string, Record<string, boolean>>,
  customPrompts: {} as Record<string, string>,
  defaultPrompts: {} as Record<string, string>,
  tokenBudgets: {} as Record<string, number>,
  docNames: {} as Record<string, string>,
  payloadPreviews: null as Record<string, PayloadPreview> | null,
  isLoadingReviewData: false,
  isLoadingPayloads: false,
  // Generation
  contextDocs: [] as ContextDoc[],
  generationProgress: [] as ProgressEvent[],
  isGenerating: false,
  extractionCallLog: null as Record<string, APICallResult[]> | null,
  rawApiResponse: null as unknown | null,
  isLoadingCallLog: false,
  isLoadingRawResponse: false,
  isLoadingRuns: false,
  isLoadingAnalysis: false,
  isLoadingDocs: false,
};

export const useConfigApisStore = create<ConfigApisState>((set) => ({
  ...initialState,

  setActiveStep: (step) => set({ activeStep: step }),

  // Categories
  setCategories: (cats) =>
    set({
      categories: cats,
      selectedCategories: cats.map((c) => c.id),
    }),
  setSelectedCategories: (ids) => set({ selectedCategories: ids }),
  toggleCategory: (id) =>
    set((s) => ({
      selectedCategories: s.selectedCategories.includes(id)
        ? s.selectedCategories.filter((c) => c !== id)
        : [...s.selectedCategories, id],
    })),
  setCategoryParam: (catId, key, value) =>
    set((s) => ({
      categoryParams: {
        ...s.categoryParams,
        [catId]: { ...s.categoryParams[catId], [key]: value },
      },
    })),

  // Extraction
  setExtractionRuns: (runs) => set({ extractionRuns: runs }),
  setActiveExtractionId: (id) => set({ activeExtractionId: id }),
  addExtractionProgress: (event) =>
    set((s) => ({ extractionProgress: [...s.extractionProgress, event] })),
  clearExtractionProgress: () => set({ extractionProgress: [] }),
  setIsExtracting: (v) => set({ isExtracting: v }),

  // Analysis
  setAnalysisRuns: (runs) => set({ analysisRuns: runs }),
  setActiveAnalysisId: (id) => set({ activeAnalysisId: id }),
  addAnalysisProgress: (event) =>
    set((s) => ({ analysisProgress: [...s.analysisProgress, event] })),
  clearAnalysisProgress: () => set({ analysisProgress: [] }),
  setIsAnalyzing: (v) => set({ isAnalyzing: v }),

  // Review & Select
  setFingerprints: (fps) => set({ fingerprints: fps }),
  setCounters: (c) => set({ counters: c }),
  setClusters: (cl) => set({ clusters: cl }),
  setEntityTypeCounts: (etc) => set({ entityTypeCounts: etc }),
  setInclusion: (docKey, path, value) =>
    set((s) => ({
      inclusions: {
        ...s.inclusions,
        [docKey]: {
          ...(s.inclusions[docKey] || {}),
          [path]: value,
        },
      },
    })),
  setAllInclusions: (docKey, paths, value) =>
    set((s) => {
      const docInc = { ...(s.inclusions[docKey] || {}) };
      for (const p of paths) {
        docInc[p] = value;
      }
      return { inclusions: { ...s.inclusions, [docKey]: docInc } };
    }),
  setCustomPrompt: (docKey, prompt) =>
    set((s) => ({
      customPrompts: { ...s.customPrompts, [docKey]: prompt },
    })),
  resetPrompt: (docKey) =>
    set((s) => {
      const { [docKey]: _, ...rest } = s.customPrompts;
      return { customPrompts: rest };
    }),
  setDefaultPrompts: (p) => set({ defaultPrompts: p }),
  setTokenBudgets: (b) => set({ tokenBudgets: b }),
  setDocNames: (n) => set({ docNames: n }),
  setPayloadPreviews: (p) => set({ payloadPreviews: p }),
  setIsLoadingReviewData: (v) => set({ isLoadingReviewData: v }),
  setIsLoadingPayloads: (v) => set({ isLoadingPayloads: v }),

  // Generation
  setContextDocs: (docs) => set({ contextDocs: docs }),
  addGenerationProgress: (event) =>
    set((s) => ({ generationProgress: [...s.generationProgress, event] })),
  clearGenerationProgress: () => set({ generationProgress: [] }),
  setIsGenerating: (v) => set({ isGenerating: v }),

  // Call log
  setExtractionCallLog: (log) => set({ extractionCallLog: log }),
  setRawApiResponse: (data) => set({ rawApiResponse: data }),
  setIsLoadingCallLog: (v) => set({ isLoadingCallLog: v }),
  setIsLoadingRawResponse: (v) => set({ isLoadingRawResponse: v }),

  // Loading
  setIsLoadingRuns: (v) => set({ isLoadingRuns: v }),
  setIsLoadingAnalysis: (v) => set({ isLoadingAnalysis: v }),
  setIsLoadingDocs: (v) => set({ isLoadingDocs: v }),

  reset: () => set(initialState),
}));
