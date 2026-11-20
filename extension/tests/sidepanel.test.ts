/**
 * @vitest-environment jsdom
 */

// @ts-ignore
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ApiClient } from '../src/api/client';
import { PaperIngestRequest, RetrieveRequest } from '../src/api/types';

describe('Sidepanel API Client and Workflow', () => {
  let client: ApiClient;

  beforeEach(() => {
    client = new ApiClient({
      baseUrl: 'http://localhost:8000',
      token: 'dev-token-test',
    });
    vi.restoreAllMocks();
  });

  describe('ApiClient HTTP Methods', () => {
    it('fetches session info with bearer token', async () => {
      const mockSession = {
        user_id: 'dev-token-test',
        quota_remaining: { new_indexes: 5, agent_turns: 5, semantic_retrievals: 20 },
      };
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => mockSession,
      });

      const res = await client.getSession();
      expect(res.user_id).toBe('dev-token-test');
      expect(res.quota_remaining.new_indexes).toBe(5);
      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v1/session',
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: 'Bearer dev-token-test',
          }),
        })
      );
    });

    it('ingests paper and returns lexical readiness', async () => {
      const payload: PaperIngestRequest = {
        title: 'Attention Is All You Need',
        arxiv_id: '1706.03762',
        version: 'v7',
        canonical_url: 'https://arxiv.org/html/1706.03762v7',
        parser_version: '1.0.0',
        sections: [],
        paragraphs: [
          {
            id: 'p1',
            section_id: 's1',
            section_path: 'Intro',
            order: 0,
            text: 'Transformers use self-attention.',
            locator: { element_id: 'p1' },
          },
        ],
      };

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          paper_id: 'paper_123',
          index_status: 'ready',
          lexical_ready: true,
          semantic_ready: false,
          content_hash: 'hash123',
        }),
      });

      const res = await client.ingestPaper(payload);
      expect(res.paper_id).toBe('paper_123');
      expect(res.lexical_ready).toBe(true);
    });

    it('retrieves evidence in B1 mode', async () => {
      const payload: RetrieveRequest = {
        request_id: 'req_1',
        paper_id: 'paper_123',
        question: 'What is attention?',
        top_k: 3,
      };

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          request_id: 'req_1',
          paper_id: 'paper_123',
          status: 'ok',
          retrieval_mode: 'B1',
          evidence: [
            {
              passage_id: 'p1',
              parent_passage_id: 'p1',
              rank: 1,
              score: 2.5,
              section_heading: 'Intro',
              section_path: 'Intro',
              text: 'Transformers use self-attention.',
              locator: { element_id: 'p1' },
              contributing_chunks: ['p1'],
            },
          ],
        }),
      });

      const res = await client.retrieve(payload);
      expect(res.retrieval_mode).toBe('B1');
      expect(res.evidence).toHaveLength(1);
      expect(res.evidence[0].passage_id).toBe('p1');
    });

    it('throws structured error on 401 unauthorized', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ detail: 'Missing or invalid authentication credentials' }),
      });

      await expect(client.getSession()).rejects.toThrow('Unauthorized');
    });

    it('throws structured error on 429 quota exceeded', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 429,
        json: async () => ({ detail: 'Daily quota exceeded for new_indexes' }),
      });

      const payload: PaperIngestRequest = {
        title: 'Over Quota',
        arxiv_id: '2401.00000',
        version: 'v1',
        canonical_url: 'https://arxiv.org/html/2401.00000v1',
        parser_version: '1.0.0',
        sections: [],
        paragraphs: [],
      };

      await expect(client.ingestPaper(payload)).rejects.toThrow('Daily quota exceeded for new_indexes');
    });

    it('creates an agent run via POST /api/v1/agent/runs', async () => {
      const runRequest = {
        request_id: 'req_agent_1',
        paper_id: 'paper_123',
        question: 'What datasets were used?',
        mode: 'A2',
      };

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 202,
        json: async () => ({
          run_id: 'run_abc_1',
          paper_id: 'paper_123',
          status: 'queued',
        }),
      });

      const res = await client.createAgentRun(runRequest);
      expect(res.run_id).toBe('run_abc_1');
      expect(res.status).toBe('queued');
      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v1/agent/runs',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(runRequest),
        })
      );
    });

    it('polls agent run via GET /api/v1/agent/runs/{run_id}', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          run_id: 'run_abc_1',
          paper_id: 'paper_123',
          status: 'completed',
          serving_model: 'ag/gemini-3.8-flash-medium',
          answer_blocks: [{ text: 'WMT 2014 was used.', evidence_ids: ['p1'] }],
        }),
      });

      const res = await client.getAgentRun('run_abc_1');
      expect(res.run_id).toBe('run_abc_1');
      expect(res.status).toBe('completed');
      expect(res.serving_model).toBe('ag/gemini-3.8-flash-medium');
      expect(res.answer_blocks).toHaveLength(1);
    });

    it('cancels agent run via POST /api/v1/agent/runs/{run_id}/cancel', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          run_id: 'run_abc_1',
          paper_id: 'paper_123',
          status: 'cancelled',
        }),
      });

      const res = await client.cancelAgentRun('run_abc_1');
      expect(res.run_id).toBe('run_abc_1');
      expect(res.status).toBe('cancelled');
    });
  });

  describe('useAgentRun hook lifecycle', () => {
    it('initializes and executes agent run flow', async () => {
      const React = await import('react');
      const { createRoot } = await import('react-dom/client');
      const { useAgentRun } = await import('../src/sidepanel/useAgentRun');

      let hookState: any = null;
      function TestComponent() {
        hookState = useAgentRun({
          client,
          paperId: 'paper_test_1',
          pollIntervalMs: 10,
        });
        return React.createElement('div', { id: 'status' }, hookState.status || 'idle');
      }

      // Mock createAgentRun -> queued, then getAgentRun -> running -> completed
      let pollCount = 0;
      global.fetch = vi.fn().mockImplementation((url: string, opts: any) => {
        if (url.includes('/api/v1/agent/runs') && opts?.method === 'POST') {
          return Promise.resolve({
            ok: true,
            status: 202,
            json: async () => ({
              run_id: 'run_lifecycle_1',
              paper_id: 'paper_test_1',
              status: 'queued',
            }),
          });
        }
        if (url.includes('/api/v1/agent/runs/run_lifecycle_1')) {
          pollCount++;
          if (pollCount === 1) {
            return Promise.resolve({
              ok: true,
              status: 200,
              json: async () => ({
                run_id: 'run_lifecycle_1',
                paper_id: 'paper_test_1',
                status: 'running',
              }),
            });
          }
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => ({
              run_id: 'run_lifecycle_1',
              paper_id: 'paper_test_1',
              status: 'completed',
              serving_model: 'ag/gemini-3.8-flash-medium',
              answer_blocks: [{ text: 'The transformer model uses multi-head attention.', evidence_ids: ['e1'] }],
              evidence: [
                {
                  passage_id: 'e1',
                  parent_passage_id: 'p1',
                  rank: 1,
                  score: 3.0,
                  section_heading: '3 Model Architecture',
                  section_path: '3 Model Architecture',
                  text: 'An attention function can be described as mapping a query and a set of key-value pairs...',
                  locator: { element_id: 'p1' },
                },
              ],
            }),
          });
        }
        return Promise.reject(new Error(`Unexpected fetch: ${url}`));
      });

      const container = document.createElement('div');
      document.body.appendChild(container);
      const root = createRoot(container);

      await React.act(async () => {
        root.render(React.createElement(TestComponent));
      });

      expect(hookState.status).toBeNull();
      expect(hookState.history).toHaveLength(0);

      // Trigger startRun
      await React.act(async () => {
        await hookState.startRun('How does attention work?');
      });

      // Wait a short tick for polling to transition
      await React.act(async () => {
        await new Promise((r) => setTimeout(r, 60));
      });

      expect(hookState.status).toBe('completed');
      expect(hookState.servingModel).toBe('ag/gemini-3.8-flash-medium');
      expect(hookState.answerBlocks).toHaveLength(1);
      expect(hookState.evidence).toHaveLength(1);
      expect(hookState.history).toHaveLength(2); // user + assistant

      // Test cancelRun
      global.fetch = vi.fn().mockImplementation((url: string, opts: any) => {
        if (url.includes('/cancel') && opts?.method === 'POST') {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => ({
              run_id: 'run_lifecycle_1',
              paper_id: 'paper_test_1',
              status: 'cancelled',
            }),
          });
        }
        return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
      });

      await React.act(async () => {
        await hookState.cancelRun();
      });

      expect(hookState.status).toBe('cancelled');

      // Test resetConversation
      await React.act(async () => {
        hookState.resetConversation();
      });
      expect(hookState.status).toBeNull();
      expect(hookState.answerBlocks).toHaveLength(0);
      expect(hookState.history).toHaveLength(0);

      await React.act(async () => root.unmount());
      document.body.removeChild(container);
    });

    it('records history immediately when POST returns terminal status', async () => {
      const React = await import('react');
      const { createRoot } = await import('react-dom/client');
      const { useAgentRun } = await import('../src/sidepanel/useAgentRun');

      let hookState: any = null;
      function TestComponent() {
        hookState = useAgentRun({
          client,
          paperId: 'paper_term_1',
          pollIntervalMs: 10,
        });
        return React.createElement('div', null, hookState.status || 'idle');
      }

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          run_id: 'run_term_1',
          paper_id: 'paper_term_1',
          status: 'completed',
          answer_blocks: [{ text: 'Instant answer from cache.', evidence_ids: ['p1'] }],
          evidence: [],
          serving_model: 'ag/gemini-3.8-flash-medium',
        }),
      });

      const container = document.createElement('div');
      document.body.appendChild(container);
      const root = createRoot(container);

      await React.act(async () => {
        root.render(React.createElement(TestComponent));
      });

      await React.act(async () => {
        await hookState.startRun('Is attention fast?');
      });

      expect(hookState.status).toBe('completed');
      expect(hookState.history).toHaveLength(2);
      expect(hookState.history[0].content).toBe('Is attention fast?');
      expect(hookState.history[1].content).toBe('Instant answer from cache.');

      await React.act(async () => root.unmount());
      document.body.removeChild(container);
    });
  });

  describe('usePaper tab listeners', () => {
    it('registers and removes chrome tab event listeners', async () => {
      const React = await import('react');
      const { createRoot } = await import('react-dom/client');
      const { usePaper } = await import('../src/sidepanel/usePaper');

      const addActivated = vi.fn();
      const removeActivated = vi.fn();
      const addUpdated = vi.fn();
      const removeUpdated = vi.fn();

      (global as any).chrome = {
        tabs: {
          query: vi.fn().mockResolvedValue([{ id: 101 }]),
          sendMessage: vi.fn(),
          onActivated: { addListener: addActivated, removeListener: removeActivated },
          onUpdated: { addListener: addUpdated, removeListener: removeUpdated },
        },
      };

      function PaperTestComponent() {
        usePaper(client);
        return React.createElement('div', null, 'paper-test');
      }

      const container = document.createElement('div');
      document.body.appendChild(container);
      const root = createRoot(container);

      await React.act(async () => {
        root.render(React.createElement(PaperTestComponent));
      });

      expect(addActivated).toHaveBeenCalled();
      expect(addUpdated).toHaveBeenCalled();

      await React.act(async () => {
        await React.act(async () => root.unmount());
      });

      expect(removeActivated).toHaveBeenCalled();
      expect(removeUpdated).toHaveBeenCalled();

      document.body.removeChild(container);
    });
  });

  describe('Local Notes Library and Markdown Export', () => {
    it('saves notes, retrieves them, and exports cleanly formatted markdown', async () => {
      const { saveNote, getNotes, deleteNote, exportNotesToMarkdown } = await import(
        '../src/sidepanel/library'
      );

      const saved1 = await saveNote({
        paperId: 'paper_1',
        arxivId: '1706.03762',
        version: 'v7',
        title: 'Attention Is All You Need',
        canonicalUrl: 'https://arxiv.org/html/1706.03762v7',
        text: 'Self-attention mechanism connects all pairs of input tokens.',
        type: 'answer',
      });

      const saved2 = await saveNote({
        paperId: 'paper_1',
        arxivId: '1706.03762',
        version: 'v7',
        title: 'Attention Is All You Need',
        canonicalUrl: 'https://arxiv.org/html/1706.03762v7',
        text: 'The Transformer is the first model relying entirely on self-attention.',
        type: 'quote',
        sectionPath: '1 Introduction',
        evidenceId: 'S1.p1',
      });

      const notes = await getNotes('1706.03762');
      expect(notes.length).toBeGreaterThanOrEqual(2);

      const md = exportNotesToMarkdown(
        notes,
        'Attention Is All You Need',
        'https://arxiv.org/html/1706.03762v7'
      );

      expect(md).toContain('# PaperLens Notes: Attention Is All You Need');
      expect(md).toContain('https://arxiv.org/html/1706.03762v7');
      expect(md).toContain('Self-attention mechanism connects all pairs of input tokens.');
      expect(md).toContain('[1 Introduction]');

      // Delete note
      await deleteNote(saved1.id);
      const afterDel = await getNotes('1706.03762');
      expect(afterDel.find((n) => n.id === saved1.id)).toBeUndefined();
    });

    it('verifies built manifest paths point to valid relative paths without dist prefix', async () => {
      const fs = await import('node:fs');
      const path = await import('node:path');
      const manifestPath = path.resolve(__dirname, '../dist/manifest.json');
      if (fs.existsSync(manifestPath)) {
        const raw = fs.readFileSync(manifestPath, 'utf-8');
        const m = JSON.parse(raw);
        expect(m.background?.service_worker).toBe('background.js');
        expect(m.content_scripts?.[0]?.js?.[0]).toBe('content.js');
        expect(m.side_panel?.default_path).toBe('sidepanel/index.html');
      }
    });
  });
});
