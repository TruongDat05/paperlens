/**
 * Send HTTP requests from the side panel to FastAPI.
 *
 * Use the backend origin for the current build and the current session
 * token. Support aborting fetches and reuse request_id when retrying the
 * same operation.
 *
 * Normalize offline, authentication, quota, and provider errors for display
 * in the UI.
 */

import {
  SessionResponse,
  PaperIngestRequest,
  PaperIngestResponse,
  PaperStatusResponse,
  RetrieveRequest,
  EvidenceResult,
  AgentRunRequest,
  AgentRunResponse,
  AccountProfile, ResearchMemory, ChatSummary, SavedConversation,
} from './types';

export interface ApiClientOptions {
  baseUrl?: string;
  token?: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export class ApiClient {
  private baseUrl: string;
  private token: string;
  private sessionPromise?: Promise<void>;
  private managedSession: boolean;
  get sessionStorageKey(): string { return `paperlens_session:${this.baseUrl}`; }

  private async ensureSession(): Promise<void> {
    if (this.managedSession && typeof chrome !== 'undefined' && chrome.storage?.local) {
      const latest = await chrome.storage.local.get(this.sessionStorageKey);
      if (latest[this.sessionStorageKey]) this.token = latest[this.sessionStorageKey];
    }
    if (this.token) return;
    if (!this.sessionPromise) this.sessionPromise = (async () => {
      const storage = typeof chrome !== 'undefined' ? chrome.storage?.local : undefined;
      const key = `paperlens_session:${this.baseUrl}`;
      const saved = storage ? await storage.get(key) : {};
      if (saved[key]) { this.token = saved[key]; return; }
      const res = await fetch(`${this.baseUrl}/api/v1/session`, { method: 'POST' });
      if (!res.ok) throw new ApiError(res.status, 'UNAUTHORIZED', 'Session creation failed');
      this.token = (await res.json()).token;
      if (storage) await storage.set({ [key]: this.token });
    })().catch((err) => { this.sessionPromise = undefined; throw err; });
    await this.sessionPromise;
  }

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = (options.baseUrl || process.env.BACKEND_URL || 'http://localhost:8000').replace(/\/+$/, '');
    this.token = options.token || '';
    this.managedSession = !options.token;
  }

  setToken(token: string): void {
    this.token = token;
  }

  private async saveSession(token: string): Promise<void> {
    this.token = token;
    this.sessionPromise = undefined;
    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      await chrome.storage.local.set({[this.sessionStorageKey]:token});
      await chrome.storage.session?.remove('paperlens_active_agent_run');
    }
  }

  async signIn(provider: 'google' | 'github'): Promise<void> {
    const redirect = chrome.identity.getRedirectURL('oauth');
    const start = await this.request<{authorization_url:string;state:string}>(`/api/v1/auth/${provider}/start`,
      {method:'POST',body:JSON.stringify({redirect_uri:redirect})});
    const result = await chrome.identity.launchWebAuthFlow({url:start.authorization_url,interactive:true});
    if (!result) throw new Error('Sign-in was cancelled.');
    const params = new URL(result).searchParams;
    if (params.get('state') !== start.state || params.has('error') || !params.get('ticket'))
      throw new Error('Sign-in could not be completed. Please try again.');
    const session = await this.request<{token:string}>('/api/v1/auth/complete',
      {method:'POST',body:JSON.stringify({ticket:params.get('ticket')})});
    await this.saveSession(session.token);
  }

  async signOut(): Promise<void> {
    const session = await this.request<{token:string}>('/api/v1/auth/logout',{method:'POST'});
    await this.saveSession(session.token);
  }

  getAccount(): Promise<AccountProfile> { return this.request('/api/v1/account'); }
  updateProfile(value: Pick<AccountProfile,'name'|'research_area'|'nationality'|'memory_enabled'>): Promise<AccountProfile> {
    return this.request('/api/v1/account/profile',{method:'PUT',body:JSON.stringify(value)});
  }
  getMemories(): Promise<ResearchMemory[]> { return this.request('/api/v1/account/memories'); }
  addMemory(text: string): Promise<unknown> {
    return this.request('/api/v1/account/memories',{method:'POST',body:JSON.stringify({text})});
  }
  updateMemory(id: string,text: string): Promise<unknown> {
    return this.request(`/api/v1/account/memories/${encodeURIComponent(id)}`,{method:'PUT',body:JSON.stringify({text})});
  }
  deleteMemory(id: string): Promise<unknown> {
    return this.request(`/api/v1/account/memories/${encodeURIComponent(id)}`,{method:'DELETE'});
  }
  getChats(query = ''): Promise<ChatSummary[]> { return this.request('/api/v1/account/chats?q='+encodeURIComponent(query)); }
  getConversation(id: string): Promise<SavedConversation> { return this.request('/api/v1/account/chats/'+encodeURIComponent(id)); }
  deleteConversation(id: string): Promise<unknown> { return this.request('/api/v1/account/chats/'+encodeURIComponent(id),{method:'DELETE'}); }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    await this.ensureSession();
    const url = `${this.baseUrl}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
    const headers: Record<string, string> = {};
    if (options.headers) {
      if (options.headers instanceof Headers) {
        options.headers.forEach((value, key) => {
          headers[key] = value;
        });
      } else if (Array.isArray(options.headers)) {
        options.headers.forEach(([key, value]) => {
          headers[key] = value;
        });
      } else {
        Object.assign(headers, options.headers);
      }
    }

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }
    if (!headers['Content-Type'] && options.body) {
      headers['Content-Type'] = 'application/json';
    }

    let response: Response;
    try {
      response = await fetch(url, {
        ...options,
        headers,
      });
    } catch (err) {
      throw new ApiError(0, 'NETWORK_ERROR', `Failed to connect to PaperLens backend: ${(err as Error).message}`);
    }

    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const errorJson = await response.json();
        if (errorJson?.detail) {
          detail = typeof errorJson.detail === 'string'
            ? errorJson.detail
            : errorJson.detail.message || JSON.stringify(errorJson.detail);
        }
      } catch {
        // Fall back to status text
        detail = response.statusText || detail;
      }

      if (response.status === 401) {
        throw new ApiError(401, 'UNAUTHORIZED', `Unauthorized: ${detail}`);
      } else if (response.status === 404) {
        throw new ApiError(404, 'NOT_FOUND', `Not found: ${detail}`);
      } else if (response.status === 429) {
        throw new ApiError(429, 'QUOTA_EXCEEDED', detail);
      } else if (response.status === 413) {
        throw new ApiError(413, 'PAYLOAD_TOO_LARGE', `Payload too large: ${detail}`);
      }
      throw new ApiError(response.status, 'API_ERROR', detail);
    }

    return response.json() as Promise<T>;
  }

  async getChatState(chatId: string): Promise<import('./types').ChatBudget> {
    return this.request(`/api/v1/agent/chats/${encodeURIComponent(chatId)}`);
  }

  async getSession(): Promise<SessionResponse> {
    return this.request<SessionResponse>('/api/v1/session');
  }

  async ingestPaper(req: PaperIngestRequest): Promise<PaperIngestResponse> {
    return this.request<PaperIngestResponse>('/api/v1/papers/ingest', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  }

  async getPaperStatus(paperId: string): Promise<PaperStatusResponse> {
    return this.request<PaperStatusResponse>(`/api/v1/papers/${encodeURIComponent(paperId)}/status`);
  }

  async retrieve(req: RetrieveRequest): Promise<EvidenceResult> {
    return this.request<EvidenceResult>('/api/v1/retrieve', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  }

  async deletePaper(paperId: string): Promise<{ status: string; paper_id: string }> {
    return this.request<{ status: string; paper_id: string }>(
      `/api/v1/papers/${encodeURIComponent(paperId)}`,
      { method: 'DELETE' }
    );
  }

  async createAgentRun(req: AgentRunRequest): Promise<AgentRunResponse> {
    return this.request<AgentRunResponse>('/api/v1/agent/runs', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  }

  async getAgentRun(runId: string): Promise<AgentRunResponse> {
    return this.request<AgentRunResponse>(`/api/v1/agent/runs/${encodeURIComponent(runId)}`);
  }

  async cancelAgentRun(runId: string): Promise<AgentRunResponse> {
    return this.request<AgentRunResponse>(
      `/api/v1/agent/runs/${encodeURIComponent(runId)}/cancel`,
      { method: 'POST' }
    );
  }

  async streamAgentRunEvents(
    runId: string,
    onEvent: (event: any) => void,
    signal?: AbortSignal
  ): Promise<void> {
    await this.ensureSession();
    const url = `${this.baseUrl}/api/v1/agent/runs/${encodeURIComponent(runId)}/events`;
    const headers: Record<string, string> = {
      Accept: 'text/event-stream',
    };
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const response = await fetch(url, { headers, signal });
    if (!response.ok) {
      throw new ApiError(response.status, 'STREAM_ERROR', `Events stream failed with status ${response.status}`);
    }
    if (!response.body) return;

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith('data: ')) {
            const jsonStr = trimmed.slice(6).trim();
            try {
              const parsed = JSON.parse(jsonStr);
              onEvent(parsed);
            } catch {
              // ignore malformed lines
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  }
}
