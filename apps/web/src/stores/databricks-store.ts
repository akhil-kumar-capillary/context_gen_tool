import { create } from "zustand";

// ── Types ──

export interface DatabricksConnection {
  cluster: string;       // canonical cluster key (e.g. "APAC2")
  instance: string;      // Databricks workspace URL — display-only, resolved from backend
}

export interface ExtractionRun {
  id: string;
  user_id: number;
  databricks_instance: string;
  root_path: string;
  modified_since?: string | null;
  total_notebooks?: number;
  processed_notebooks?: number;
  skipped_notebooks?: number;
  total_sqls_extracted?: number;
  valid_sqls?: number;
  unique_hashes?: number;
  api_failures?: number;
  status: string;
  started_at?: string;
  completed_at?: string;
}

export interface OrgIdEntry {
  org_id: string;
  total_sqls: number;
  valid_sqls: number;
}

export interface AnalysisRun {
  id: string;
  run_id: string;
  org_id: string;
  version: number;
  total_weight: number;
  status: string;
  created_at: string;
  fingerprint_count?: number;
  notebook_count?: number;
  databricks_instance?: string;
  root_path?: string;
  valid_sqls?: number;
}

export interface ContextDoc {
  id: number;
  source_type: string;
  source_run_id?: string;
  user_id: number;
  org_id?: string;
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
  doc_key?: string;
  doc_name?: string;
  word_count?: number;
  error?: string;
  [key: string]: unknown;
}

export type PipelineStep = "connect" | "extract" | "analyze" | "generate";

// ── Store ──

interface DatabricksState {
  // Connection (auto-resolved from JWT cluster)
  connection: DatabricksConnection;
  connectionStatus: "idle" | "testing" | "connected" | "failed";
  connectionError: string | null;

  // Active step in the pipeline
  activeStep: PipelineStep;

  // Extraction
  extractionRuns: ExtractionRun[];
  activeExtractionId: string | null;
  extractionProgress: ProgressEvent[];
  isExtracting: boolean;

  // Org IDs (after extraction)
  orgIds: OrgIdEntry[];
  selectedOrgId: string | null;

  // Analysis
  analysisRuns: AnalysisRun[];
  activeAnalysisId: string | null;
  analysisProgress: ProgressEvent[];
  isAnalyzing: boolean;

  // Doc Generation
  contextDocs: ContextDoc[];
  generationProgress: ProgressEvent[];
  isGenerating: boolean;

  // Loading states
  isLoadingRuns: boolean;
  isLoadingAnalysis: boolean;
  isLoadingDocs: boolean;

  // Actions
  setConnection: (conn: Partial<DatabricksConnection>) => void;
  setConnectionStatus: (status: "idle" | "testing" | "connected" | "failed", error?: string | null) => void;
  setActiveStep: (step: PipelineStep) => void;

  setExtractionRuns: (runs: ExtractionRun[]) => void;
  setActiveExtractionId: (id: string | null) => void;
  addExtractionProgress: (event: ProgressEvent) => void;
  clearExtractionProgress: () => void;
  setIsExtracting: (v: boolean) => void;

  setOrgIds: (orgs: OrgIdEntry[]) => void;
  setSelectedOrgId: (id: string | null) => void;

  setAnalysisRuns: (runs: AnalysisRun[]) => void;
  setActiveAnalysisId: (id: string | null) => void;
  addAnalysisProgress: (event: ProgressEvent) => void;
  clearAnalysisProgress: () => void;
  setIsAnalyzing: (v: boolean) => void;

  setContextDocs: (docs: ContextDoc[]) => void;
  addGenerationProgress: (event: ProgressEvent) => void;
  clearGenerationProgress: () => void;
  setIsGenerating: (v: boolean) => void;

  setIsLoadingRuns: (v: boolean) => void;
  setIsLoadingAnalysis: (v: boolean) => void;
  setIsLoadingDocs: (v: boolean) => void;

  reset: () => void;
}

const initialState = {
  connection: { cluster: "", instance: "" },
  connectionStatus: "idle" as const,
  connectionError: null,
  activeStep: "connect" as PipelineStep,
  extractionRuns: [] as ExtractionRun[],
  activeExtractionId: null,
  extractionProgress: [] as ProgressEvent[],
  isExtracting: false,
  orgIds: [] as OrgIdEntry[],
  selectedOrgId: null,
  analysisRuns: [] as AnalysisRun[],
  activeAnalysisId: null,
  analysisProgress: [] as ProgressEvent[],
  isAnalyzing: false,
  contextDocs: [] as ContextDoc[],
  generationProgress: [] as ProgressEvent[],
  isGenerating: false,
  isLoadingRuns: false,
  isLoadingAnalysis: false,
  isLoadingDocs: false,
};

export const useDatabricksStore = create<DatabricksState>((set) => ({
  ...initialState,

  // Connection
  setConnection: (conn) =>
    set((s) => ({ connection: { ...s.connection, ...conn } })),
  setConnectionStatus: (status, error = null) =>
    set({ connectionStatus: status, connectionError: error }),
  setActiveStep: (step) => set({ activeStep: step }),

  // Extraction
  setExtractionRuns: (runs) => set({ extractionRuns: runs }),
  setActiveExtractionId: (id) => set({ activeExtractionId: id }),
  addExtractionProgress: (event) =>
    set((s) => ({ extractionProgress: [...s.extractionProgress, event] })),
  clearExtractionProgress: () => set({ extractionProgress: [] }),
  setIsExtracting: (v) => set({ isExtracting: v }),

  // Org IDs
  setOrgIds: (orgs) => set({ orgIds: orgs }),
  setSelectedOrgId: (id) => set({ selectedOrgId: id }),

  // Analysis
  setAnalysisRuns: (runs) => set({ analysisRuns: runs }),
  setActiveAnalysisId: (id) => set({ activeAnalysisId: id }),
  addAnalysisProgress: (event) =>
    set((s) => ({ analysisProgress: [...s.analysisProgress, event] })),
  clearAnalysisProgress: () => set({ analysisProgress: [] }),
  setIsAnalyzing: (v) => set({ isAnalyzing: v }),

  // Generation
  setContextDocs: (docs) => set({ contextDocs: docs }),
  addGenerationProgress: (event) =>
    set((s) => ({ generationProgress: [...s.generationProgress, event] })),
  clearGenerationProgress: () => set({ generationProgress: [] }),
  setIsGenerating: (v) => set({ isGenerating: v }),

  // Loading
  setIsLoadingRuns: (v) => set({ isLoadingRuns: v }),
  setIsLoadingAnalysis: (v) => set({ isLoadingAnalysis: v }),
  setIsLoadingDocs: (v) => set({ isLoadingDocs: v }),

  // Reset all
  reset: () => set(initialState),
}));
