/**
 * Define HTTP data shared by the side panel and FastAPI.
 *
 * Describe requests and responses for session, ingest, paper status,
 * retrieve, agent runs, cancellation, and deletion according to backend
 * schemas. Preserve evidence IDs, source locations, index status, answer
 * mode, and model metadata.
 */

export interface SourceLocation {
  element_id?: string;
  selector?: string;
  xpath?: string;
  dataset_name?: string;
  paragraph_index?: number;
}

export interface AccountProfile {
  owner_id: string;
  name: string;
  research_area: string;
  nationality: string;
  memory_enabled: boolean;
  onboarded: boolean;
  identities: {provider: 'google' | 'github'; display_name: string}[];
  auth_providers: {google: boolean; github: boolean};
}

export interface ResearchMemory {
  memory_id: string;
  kind: string;
  text: string;
  source_label: string;
  source_url?: string;
  updated_at: string;
}

export interface ChatSummary {
  chat_id: string;
  paper_id: string;
  title: string;
  paper_title: string;
  canonical_url: string;
  updated_at: string;
  turns: number;
}

export interface SavedConversation {
  budget: ChatBudget;
  messages: import('../sidepanel/useAgentRun').ChatMessage[];
  canonical_url: string;
  paper_id: string;
  active_run_id?: string|null;
}

export interface SectionInput {
  id: string;
  heading: string;
  path: string;
  order: number;
  section_type?: string;
}

export interface ParagraphInput {
  id: string;
  section_id: string;
  section_path: string;
  order: number;
  text: string;
  locator?: SourceLocation;
  fingerprint?: string;
  has_math?: boolean;
  has_table?: boolean;
}

export interface PaperIngestRequest {
  title: string;
  arxiv_id: string;
  version: string;
  canonical_url: string;
  parser_version: string;
  sections: SectionInput[];
  paragraphs: ParagraphInput[];
}

export interface PaperIngestResponse {
  paper_id: string;
  index_status: string;
  lexical_ready: boolean;
  semantic_ready: boolean;
  content_hash: string;
}

export interface AnswerBlock {
  text: string;
  evidence_ids: string[];
}

export interface PaperStatusResponse {
  paper_id: string;
  title: string;
  arxiv_id: string;
  version: string;
  lexical_ready: boolean;
  semantic_ready: boolean;
  indexing_error?: string | null;
}

export interface RetrieveRequest {
  request_id: string;
  paper_id: string;
  question: string;
  top_k?: number;
  mode?: string;
}

export interface EvidenceItem {
  passage_id: string;
  parent_passage_id: string;
  rank: number;
  score: number;
  section_heading: string;
  section_path: string;
  text: string;
  locator: SourceLocation;
  contributing_chunks?: string[];
  fingerprint?: string;
  section_id?: string;
  paper_id?: string;
}

export interface EvidenceResult {
  request_id: string;
  paper_id: string;
  status: string;
  retrieval_mode: string;
  fallback_reason?: string | null;
  evidence: EvidenceItem[];
}

export interface QuotaRemaining {
  new_indexes: number | null;
  agent_turns: number | null;
  semantic_retrievals: number | null;
}

export const CHAT_TOKEN_LIMIT = 500_000;

export type ResearchLevel = 'low' | 'medium' | 'high';

export interface ChatBudget {
  chat_id?: string | null;
  tokens_used: number;
  token_limit: number;
  usage_estimated: boolean;
  chat_exhausted: boolean;
}

export interface AgentRunRequest {
  request_id: string;
  paper_id: string;
  question: string;
  history?: Array<{ role: string; content: string }>;
  mode?: string;
  level?: ResearchLevel;
  chat_id?: string;
  images?: Array<{ name: string; data_url: string }>;
}

export interface AgentRunResponse extends Partial<ChatBudget> {
  run_id: string;
  paper_id: string;
  status: 'queued' | 'running' | 'completed' | 'partial' | 'evidence_only' | 'cancelled' | 'failed' | 'refused';
  retrieval_mode?: string | null;
  retrieval_fallback_reason?: string | null;
  serving_model?: string | null;
  fallback_reason?: string | null;
  answer_blocks?: AnswerBlock[] | null;
  evidence?: EvidenceItem[] | null;
  limitations?: string | null;
  follow_ups?: string[];
  error_message?: string | null;
}

export interface AgentRunEvent extends Partial<ChatBudget> {
  type: 'status' | 'activity' | 'tool_call' | 'tool_result' | 'delta' | 'done' | 'error';
  status?: AgentRunResponse['status'];
  state?: 'searching_paper' | 'reading_sources' | 'writing_answer' | string;
  message?: string;
  tool_name?: string;
  arguments?: Record<string, any>;
  summary?: string;
  count?: number;
  delta?: string;
  text?: string;
  answer_blocks?: AnswerBlock[];
  evidence?: EvidenceItem[];
  serving_model?: string | null;
  fallback_reason?: string | null;
  limitations?: string | null;
  follow_ups?: string[];
  error?: string;
}

export interface SessionResponse {
  user_id: string;
  quota_remaining: QuotaRemaining;
}
