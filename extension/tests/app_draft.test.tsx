/** @vitest-environment jsdom */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { it, expect, vi } from 'vitest';
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
const state = vi.hoisted(() => ({ paperId: null as string | null, url: 'https://arxiv.org/html/p1v1' }));
vi.mock('../src/sidepanel/usePaper', () => ({ usePaper: () => ({
  context: { pageType: 'html', arxivId: 'p1', canonicalUrl: state.url, version: 'v1' },
  paperId: state.paperId, loading: false, analyzing: !state.paperId, paperStatus: null,
}) }));
vi.mock('../src/sidepanel/useAgentRun', () => ({ useAgentRun: () => ({
  messages: [], evidence: [], history: [], answerBlocks: [], polling: false,
}) }));
import { App } from '../src/sidepanel/App';
import { ApiClient } from '../src/api/client';
vi.spyOn(ApiClient.prototype,'getAccount').mockResolvedValue({owner_id:'owner',name:'Researcher',research_area:'AI',nationality:'Vietnamese',memory_enabled:true,onboarded:true,identities:[],auth_providers:{google:false,github:false}});

it('preserves the question typed while the same paper finishes indexing', async () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(<App />));
  const textarea = container.querySelector('textarea')!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(textarea, 'Từ paper trên, tôi có thể tìm hướng mới');
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  });
  state.paperId = 'indexed-p1';
  await act(async () => root.render(<App />));
  expect(container.querySelector('textarea')!.value).toBe('Từ paper trên, tôi có thể tìm hướng mới');
  state.url = 'https://arxiv.org/html/p2v1';
  await act(async () => root.render(<App />));
  expect(container.querySelector('textarea')!.value).toBe('');
  await act(async () => root.unmount());
  container.remove();
});
