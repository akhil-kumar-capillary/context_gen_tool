// Auth types
export interface Org {
  id: number;
  name: string;
}

export interface User {
  id: number;
  email: string;
  displayName: string;
  isAdmin: boolean;
  orgs: Org[];
}

export interface LoginResponse {
  token: string;
  user: User;
}

// Context types
export interface Context {
  id: string;
  name: string;
  context: string;
  scope: "org" | "private";
  updated_by?: string;
  can_edit?: boolean;
}

export interface AiGeneratedContext {
  id: string;
  name: string;
  content: string;
  scope: "org" | "private";
  uploadStatus?: "pending" | "uploading" | "success" | "error";
  error?: string;
}

// LLM types
export type LLMProvider = "anthropic" | "openai";

export interface LLMUsage {
  input_tokens: number;
  output_tokens: number;
  warning?: string;
}

// Cluster configuration
export const CLUSTERS = [
  { id: "apac2", label: "APAC2", url: "https://apac2.intouch.capillarytech.com" },
  { id: "apac", label: "APAC", url: "https://apac.intouch.capillarytech.com" },
  { id: "eu", label: "EU", url: "https://eu.intouch.capillarytech.com" },
  { id: "north-america", label: "North America", url: "https://north-america.intouch.capillarytech.com" },
  { id: "tata", label: "TATA", url: "https://tata.intouch.capillarytech.com" },
  { id: "ushc", label: "USHC", url: "https://ushc.intouch.capillarytech.com" },
  { id: "sea", label: "SEA", url: "https://sea.intouch.capillarytech.com" },
] as const;

export type ClusterId = (typeof CLUSTERS)[number]["id"];

// Chat types
export interface ChatMessage {
  id: string;
  conversationId: string;
  role: "user" | "assistant" | "tool_result";
  content: string;
  toolCalls?: ToolCallStatus[];
  tokenUsage?: LLMUsage;
  error?: string;
  createdAt: string;
}

export interface ToolCallStatus {
  name: string;
  id: string;
  input?: Record<string, unknown>;
  result?: string;
  status: "preparing" | "running" | "done" | "error";
  display?: string;
  summary?: string;
}

export interface ChatConversation {
  id: string;
  title: string;
  provider: LLMProvider;
  model: string;
  createdAt: string;
  updatedAt: string;
  messageCount?: number;
}
