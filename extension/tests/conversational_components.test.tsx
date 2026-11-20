/**
 * @vitest-environment jsdom
 */

// @ts-ignore
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

import React, { act } from 'react';
import { createRoot, Root } from 'react-dom/client';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { Composer } from '../src/sidepanel/Composer';
import { ActivityProgress } from '../src/sidepanel/ActivityProgress';
import { Answer } from '../src/sidepanel/Answer';
import { Header } from '../src/sidepanel/Header';
import { ConversationView } from '../src/sidepanel/ConversationView';
import { ToolActivity, ChatMessage } from '../src/sidepanel/useAgentRun';
import { ApiClient } from '../src/api/client';
import { useAgentRun } from '../src/sidepanel/useAgentRun';
import { EvidenceItem } from '../src/api/types';
import { PageType } from '../src/messages';

function setInputValue(el: HTMLTextAreaElement, val: string) {
  const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
  if (nativeSetter) {
    nativeSetter.call(el, val);
  } else {
    el.value = val;
  }
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
}

describe('Conversational UI Components and State Machine', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    await act(async () => {
      root.unmount();
    });
    if (container.parentNode) {
      container.parentNode.removeChild(container);
    }
  });

  describe('Composer Component', () => {
    it('selects the High reasoning level', async () => {
      const onSend = vi.fn();
      await act(async () => root.render(<Composer onSend={onSend} onStop={vi.fn()} isBusy={false} />));
      const mathButton = Array.from(container.querySelectorAll('button')).find(button => button.textContent === 'High')!;
      await act(async () => mathButton.click());
      await act(async () => setInputValue(container.querySelector('textarea')!, 'Explain the loss equation.'));
      await act(async () => (container.querySelector('.composer-btn-send') as HTMLButtonElement).click());
      expect(onSend).toHaveBeenCalledWith('Explain the loss equation.', [], 'high');
    });

    it('renders textarea with placeholder and handles Enter to send', async () => {
      const onSend = vi.fn();
      const onStop = vi.fn();

      await act(async () => {
        root.render(
          <Composer
            onSend={onSend}
            onStop={onStop}
            isBusy={false}
            disabled={false}
            placeholder="Ask a question..."
          />
        );
      });

      const textarea = container.querySelector('textarea') as HTMLTextAreaElement;
      expect(textarea).not.toBeNull();
      expect(textarea.placeholder).toBe('Ask a question...');

      // Type text using setter helper
      await act(async () => {
        setInputValue(textarea, 'What is the main contribution?');
      });

      // Press Enter without shift
      await act(async () => {
        const enterEvent = new KeyboardEvent('keydown', {
          key: 'Enter',
          code: 'Enter',
          bubbles: true,
          cancelable: true,
        });
        textarea.dispatchEvent(enterEvent);
      });

      expect(onSend).toHaveBeenCalledWith('What is the main contribution?', [], 'low');
    });

    it('adds newline on Shift+Enter without sending', async () => {
      const onSend = vi.fn();
      const onStop = vi.fn();

      await act(async () => {
        root.render(
          <Composer
            onSend={onSend}
            onStop={onStop}
            isBusy={false}
            disabled={false}
          />
        );
      });

      const textarea = container.querySelector('textarea') as HTMLTextAreaElement;

      await act(async () => {
        setInputValue(textarea, 'Line 1');
      });

      // Press Shift+Enter
      await act(async () => {
        const shiftEnterEvent = new KeyboardEvent('keydown', {
          key: 'Enter',
          code: 'Enter',
          shiftKey: true,
          bubbles: true,
          cancelable: true,
        });
        textarea.dispatchEvent(shiftEnterEvent);
      });

      expect(onSend).not.toHaveBeenCalled();
    });

    it('respects IME composition and does NOT send when composing (Vietnamese Telex/VNI)', async () => {
      const onSend = vi.fn();
      const onStop = vi.fn();

      await act(async () => {
        root.render(
          <Composer
            onSend={onSend}
            onStop={onStop}
            isBusy={false}
            disabled={false}
          />
        );
      });

      const textarea = container.querySelector('textarea') as HTMLTextAreaElement;

      // Start IME composition
      await act(async () => {
        textarea.dispatchEvent(new CompositionEvent('compositionstart', { bubbles: true }));
      });

      // Enter during IME composition
      await act(async () => {
        const enterDuringIme = new KeyboardEvent('keydown', {
          key: 'Enter',
          code: 'Enter',
          bubbles: true,
          cancelable: true,
        });
        Object.defineProperty(enterDuringIme, 'isComposing', { value: true });
        textarea.dispatchEvent(enterDuringIme);
      });

      expect(onSend).not.toHaveBeenCalled();

      // End IME composition
      await act(async () => {
        setInputValue(textarea, 'Mô hình hoạt động như thế nào?');
        textarea.dispatchEvent(new CompositionEvent('compositionend', { bubbles: true }));
      });

      // Normal Enter after composition ended
      await act(async () => {
        const enterAfterIme = new KeyboardEvent('keydown', {
          key: 'Enter',
          code: 'Enter',
          bubbles: true,
          cancelable: true,
        });
        textarea.dispatchEvent(enterAfterIme);
      });

      expect(onSend).toHaveBeenCalledWith('Mô hình hoạt động như thế nào?', [], 'low');
    });

    it('shows Stop button while running and triggers onStop', async () => {
      const onSend = vi.fn();
      const onStop = vi.fn();

      await act(async () => {
        root.render(
          <Composer
            onSend={onSend}
            onStop={onStop}
            isBusy={true}
            disabled={false}
          />
        );
      });

      const stopBtn = container.querySelector('.composer-btn-stop') as HTMLButtonElement;
      expect(stopBtn).not.toBeNull();
      expect(stopBtn.getAttribute('aria-label')).toBe('Stop generating response');

      await act(async () => {
        stopBtn.click();
      });

      expect(onStop).toHaveBeenCalled();
    });

    it('preserves draft and handles draft updates', async () => {
      const onSend = vi.fn();
      const onDraftChange = vi.fn();

      await act(async () => {
        root.render(
          <Composer
            draftText="Draft question saved"
            onDraftChange={onDraftChange}
            onSend={onSend}
            onStop={vi.fn()}
            isBusy={false}
            disabled={false}
          />
        );
      });

      const textarea = container.querySelector('textarea') as HTMLTextAreaElement;
      expect(textarea.value).toBe('Draft question saved');

      await act(async () => {
        setInputValue(textarea, 'Updated draft');
      });

      expect(onDraftChange).toHaveBeenCalledWith('Updated draft');
    });

    it('switches research modes and sends selected mode', async () => {
      const onSend = vi.fn();

      await act(async () => {
        root.render(
          <Composer
            onSend={onSend}
            onStop={vi.fn()}
            isBusy={false}
            disabled={false}
          />
        );
      });

      // Find mode chips
      const modeChips = container.querySelectorAll('.mode-chip');
      expect(modeChips.length).toBe(3); // Deep Research, Fast QA, Math & Tables

      // Click "Fast QA" (index 1)
      await act(async () => {
        (modeChips[1] as HTMLButtonElement).click();
      });

      const textarea = container.querySelector('textarea') as HTMLTextAreaElement;
      await act(async () => {
        setInputValue(textarea, 'Quick summary?');
      });

      const sendBtn = container.querySelector('.composer-btn-send') as HTMLButtonElement;
      await act(async () => {
        sendBtn.click();
      });

      expect(onSend).toHaveBeenCalledWith('Quick summary?', [], 'medium');
    });

    it('renders file and image upload action buttons and drop zone', async () => {
      await act(async () => {
        root.render(
          <Composer
            onSend={vi.fn()}
            onStop={vi.fn()}
            isBusy={false}
            disabled={false}
          />
        );
      });

      const actionBtns = container.querySelectorAll('.composer-icon-action-btn');
      expect(actionBtns.length).toBe(1); // Images only

      // Check hidden file inputs exist
      const fileInputs = container.querySelectorAll('input[type="file"]');
      expect(fileInputs.length).toBe(1);
      expect(fileInputs[0].getAttribute('accept')).toBe('image/png,image/jpeg,image/webp');
    });
  });

  it('renders contextual follow-ups and forwards the chosen question', async () => {
    const follow = vi.fn();
    await act(async () => root.render(<ConversationView messages={[{id:'a',role:'assistant',timestamp:0,status:'completed',content:'A supported explanation.',answerBlocks:[{text:'A supported explanation.',evidence_ids:['p1']}],followUps:['How would we isolate the retriever in an ablation?']}]} evidence={[]} onFollowUp={follow} onSelectEvidence={vi.fn()} onJump={vi.fn()} onSaveAnswer={vi.fn()} onRetry={vi.fn()} isBusy={false} />));
    const button = container.querySelector('.follow-up-question') as HTMLButtonElement;
    expect(button.textContent).toContain('isolate the retriever');
    await act(async () => button.click());
    expect(follow).toHaveBeenCalledWith('How would we isolate the retriever in an ablation?');
    expect(container.querySelector('.starter-chip')).toBeNull();
  });

  it('announces a full context and disables sending until a new session', async () => {
    await act(async () => root.render(<Composer onSend={vi.fn()} onStop={vi.fn()} isBusy={false} tokensUsed={500000} exhausted draftText="Another question" />));
    expect(container.querySelector('[role=meter]')?.getAttribute('aria-valuenow')).toBe('500000');
    expect((container.querySelector('.composer-btn-send') as HTMLButtonElement).disabled).toBe(true);
    expect(container.textContent).toContain('Vui lòng tạo session mới');
  });

  describe('ActivityProgress Component', () => {
    it('displays accurate activity states', async () => {
      const activities: ToolActivity[] = [];

      // Test searching state
      await act(async () => {
        root.render(
          <ActivityProgress
            activityState="searching_paper"
            toolActivities={activities}
          />
        );
      });

      expect(container.textContent).toContain('searching_paper');

      // Test reading state
      await act(async () => {
        root.render(
          <ActivityProgress
            activityState="reading_sources"
            toolActivities={activities}
          />
        );
      });

      expect(container.textContent).toContain('reading_sources');

      // Test writing state
      await act(async () => {
        root.render(
          <ActivityProgress
            activityState="writing_answer"
            toolActivities={activities}
          />
        );
      });

      expect(container.textContent).toContain('writing_answer');
    });

    it('renders real tool activity chips with arguments and results expandable without fake CoT', async () => {
      const toolActivities: ToolActivity[] = [
        {
          id: 'tool_1',
          toolName: 'search_evidence',
          arguments: { query: 'transformer architecture' },
          state: 'running',
        },
      ];

      await act(async () => {
        root.render(
          <ActivityProgress
            activityState="searching_paper"
            toolActivities={toolActivities}
          />
        );
      });

      const toolSection = container.querySelector('.tool-activity-section') as HTMLElement;
      expect(toolSection).not.toBeNull();
      expect(toolSection.textContent).toContain('1 tool action');

      // Update to completed with result
      const completedActivities: ToolActivity[] = [
        {
          id: 'tool_1',
          toolName: 'search_evidence',
          arguments: { query: 'transformer architecture' },
          summary: 'Found 4 relevant passages',
          state: 'completed',
        },
      ];

      await act(async () => {
        root.render(
          <ActivityProgress
            activityState="reading_sources"
            toolActivities={completedActivities}
          />
        );
      });

      expect(container.textContent).toContain('Found 4 relevant passages');

      // Toggle details
      const toggleBtn = container.querySelector('.tool-toggle-btn') as HTMLButtonElement;
      expect(toggleBtn).not.toBeNull();
      await act(async () => {
        toggleBtn.click();
      });

      // Verify expanded details show real args, not fake reasoning
      const chip = container.querySelector('.tool-chip');
      expect(chip).not.toBeNull();
      expect(chip?.textContent).toContain('Search Paper');
      expect(chip?.textContent).toContain('transformer architecture');
      // Ensure no private reasoning / chain-of-thought text
      expect(container.textContent).not.toContain('thinking:');
      expect(container.textContent).not.toContain('internal_monologue');
    });
  });

  describe('Answer Component', () => {
    it('renders answer text, citation badges, and handles citation preview & jump to source', async () => {
      const onJump = vi.fn();
      const onSelectEvidence = vi.fn();
      const onSaveAnswer = vi.fn();

      const answerBlocks = [
        {
          text: 'The Transformer model relies entirely on self-attention [p1]. Multi-head attention allows joint attending [p2].',
          evidence_ids: ['p1', 'p2'],
        },
      ];

      const evidence: EvidenceItem[] = [
        {
          passage_id: 'p1',
          parent_passage_id: 'p1',
          rank: 1,
          score: 3.5,
          section_heading: '1 Introduction',
          section_path: '1 Introduction',
          text: 'The Transformer is the first transduction model relying entirely on self-attention.',
          locator: { element_id: 'p1' },
        },
        {
          passage_id: 'p2',
          parent_passage_id: 'p2',
          rank: 2,
          score: 2.8,
          section_heading: '3.2 Multi-Head Attention',
          section_path: '3 Model Architecture > 3.2 Multi-Head Attention',
          text: 'Multi-head attention allows the model to jointly attend to information from different representation subspaces.',
          locator: { element_id: 'p2' },
        },
      ];

      await act(async () => {
        root.render(
          <Answer
            answerBlocks={answerBlocks}
            evidence={evidence}
            servingModel="ag/gemini-3.8-flash-medium"
            onSelectEvidence={onSelectEvidence}
            onJump={onJump}
            onSaveAnswer={onSaveAnswer}
          />
        );
      });

      // Verify model names and internal aliases are NOT displayed in user-facing interface
      expect(container.textContent).not.toContain('gemini');
      expect(container.textContent).not.toContain('claude');
      expect(container.textContent).not.toContain('ag/');

      // Verify citation badges
      const badges = container.querySelectorAll('.citation-link');
      expect(badges.length).toBe(2);
      expect(badges[0].textContent).toBe('1');

      // Click first citation badge to expand preview card
      await act(async () => {
        (badges[0] as HTMLButtonElement).click();
      });

      expect(onJump).toHaveBeenCalledWith(expect.objectContaining({passage_id:'p1'}));

      const previewCard = container.querySelector('.citation-preview-card');
      expect(previewCard).not.toBeNull();
      expect(previewCard?.textContent).toContain('1 Introduction');
      expect(previewCard?.textContent).toContain('The Transformer is the first transduction model');

      // Click "Jump to source"
      const jumpBtn = previewCard?.querySelector('.citation-preview-actions button') as HTMLButtonElement;
      expect(jumpBtn).not.toBeNull();
      await act(async () => {
        jumpBtn.click();
      });

      expect(onJump).toHaveBeenCalledWith(expect.objectContaining({ passage_id: 'p1' }));
    });

    it('copies answer text to clipboard and shows feedback', async () => {
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, {
        clipboard: { writeText: writeTextMock },
      });

      const answerBlocks = [{ text: 'Answer for clipboard test.', evidence_ids: [] }];

      await act(async () => {
        root.render(
          <Answer
            answerBlocks={answerBlocks}
            evidence={[]}
            onSelectEvidence={vi.fn()}
          />
        );
      });

      const copyBtn = container.querySelector('.action-btn[title="Copy answer"]') as HTMLButtonElement;
      expect(copyBtn).not.toBeNull();

      await act(async () => {
        copyBtn.click();
      });

      expect(writeTextMock).toHaveBeenCalledWith('Answer for clipboard test.');
      expect(copyBtn.getAttribute('title')).toBe('Copied to clipboard');
    });

    it('triggers save note and shows saved confirmation', async () => {
      const onSaveAnswer = vi.fn();
      const answerBlocks = [{ text: 'Groundbreaking finding.', evidence_ids: ['p1'] }];

      await act(async () => {
        root.render(
          <Answer
            answerBlocks={answerBlocks}
            evidence={[]}
            onSelectEvidence={vi.fn()}
            onSaveAnswer={onSaveAnswer}
          />
        );
      });

      const saveBtn = container.querySelector('.action-btn[title="Save to notes"]') as HTMLButtonElement;
      expect(saveBtn).not.toBeNull();

      await act(async () => {
        saveBtn.click();
      });

      expect(onSaveAnswer).toHaveBeenCalledWith('Groundbreaking finding.');
      expect(saveBtn.getAttribute('title')).toBe('Saved to notes');
    });
  });

  describe('Header Component', () => {
    it('displays paper metadata, indexing status, theme toggle, and new chat', async () => {
      const onNewConversation = vi.fn();
      const onToggleTheme = vi.fn();
      const onModeChange = vi.fn();

      await act(async () => {
        root.render(
          <Header
            context={{
              isSupported: true,
              arxivId: '2504.01346',
              version: 'v4',
              pageType: PageType.HTML,
              canonicalUrl: 'https://arxiv.org/html/2504.01346v4',
              htmlUrl: 'https://arxiv.org/html/2504.01346v4',
            }}
            paperStatus={{
              paper_id: 'paper_survey_1',
              title: 'Reasoning in Large Language Models: A Comprehensive Survey',
              arxiv_id: '2504.01346',
              version: 'v4',
              lexical_ready: true,
              semantic_ready: true,
            }}
            mode="agent"
            onModeChange={onModeChange}
            theme="dark"
            onToggleTheme={onToggleTheme}
            onNewConversation={onNewConversation}
            isBusy={false}
            canReset={true}
          />
        );
      });

      expect(container.textContent).toContain('PaperLens');
      expect(container.textContent).toContain('2504.01346');
      expect(container.textContent).toContain('(v4)');
      expect(container.textContent).toContain('Dense Ready');
      expect(container.textContent).toContain('Reasoning in Large Language Models');

      // Theme toggle
      const themeBtn = container.querySelector('.icon-control-btn[title*="theme"]') as HTMLButtonElement;
      expect(themeBtn).not.toBeNull();
      await act(async () => {
        themeBtn.click();
      });
      expect(onToggleTheme).toHaveBeenCalled();

      // New chat
      const newChatBtn = container.querySelector('.icon-control-btn[title="Start a new conversation"]') as HTMLButtonElement;
      expect(newChatBtn).not.toBeNull();
      await act(async () => {
        newChatBtn.click();
      });
      expect(onNewConversation).toHaveBeenCalled();
    });
  });

  describe('ConversationView & Starter Prompts', () => {
    it('has no generic starter questions in an empty conversation', async () => {
      await act(async () => root.render(<ConversationView messages={[]} evidence={[]} onFollowUp={vi.fn()}
        onSelectEvidence={vi.fn()} onJump={vi.fn()} onSaveAnswer={vi.fn()} onRetry={vi.fn()} isBusy={false} />));
      expect(container.textContent).toContain('Explore this paper');
      expect(container.querySelector('.starter-chip')).toBeNull();
    });

    it('renders conversational messages and retry action for error messages', async () => {
      const onRetry = vi.fn();
      const messages: ChatMessage[] = [
        {
          id: 'm1',
          role: 'user',
          content: 'Explain self-attention simply.',
          timestamp: Date.now(),
        },
        {
          id: 'm2',
          role: 'assistant',
          content: '',
          status: 'failed',
          error: 'Connection interrupted',
          timestamp: Date.now(),
        },
      ];

      await act(async () => {
        root.render(
          <ConversationView
            messages={messages}
            evidence={[]}
            onFollowUp={vi.fn()}
            onSelectEvidence={vi.fn()}
            onJump={vi.fn()}
            onSaveAnswer={vi.fn()}
            onRetry={onRetry}
            isBusy={false}
          />
        );
      });

      expect(container.textContent).toContain('Explain self-attention simply.');
      expect(container.textContent).toContain('Connection interrupted');

      const retryBtn = container.querySelector('.retry-btn') as HTMLButtonElement;
      expect(retryBtn).not.toBeNull();
      await act(async () => {
        retryBtn.click();
      });

      expect(onRetry).toHaveBeenCalled();
    });
  });

  describe('useAgentRun Streaming and Cancellation', () => {
    it('receives streaming events and populates conversational assistant message', async () => {
      const client = new ApiClient({ token: 'test-token' });

      vi.spyOn(client, 'createAgentRun').mockResolvedValue({
        run_id: 'run_stream_test',
        paper_id: 'paper_1',
        status: 'queued',
      });

      vi.spyOn(client, 'streamAgentRunEvents').mockImplementation(async (runId, onEvent) => {
        onEvent({ type: 'activity', activity: 'searching_paper' });
        onEvent({
          type: 'tool_call',
          tool: { id: 'tc1', name: 'lexical_search', label: 'Search attention', arguments: { query: 'attention' } },
        });
        onEvent({
          type: 'tool_result',
          tool_call_id: 'tc1',
          summary: 'Found 3 passages',
          passages_count: 3,
        });
        onEvent({ type: 'activity', activity: 'writing_answer' });
        onEvent({ type: 'delta', delta: 'Attention ' });
        onEvent({ type: 'delta', delta: 'is all you need.' });
        onEvent({
          type: 'done',
          status: 'completed',
          serving_model: 'ag/gemini-3.8-flash-medium',
          answer_blocks: [{ text: 'Attention is all you need.', evidence_ids: ['p1'] }],
          evidence: [
            {
              passage_id: 'p1',
              parent_passage_id: 'p1',
              rank: 1,
              score: 3.0,
              section_heading: 'Intro',
              section_path: 'Intro',
              text: 'Attention is all you need.',
              locator: { element_id: 'p1' },
            },
          ],
        });
      });

      let hook: any = null;
      function Harness() {
        hook = useAgentRun({ client, paperId: 'paper_1' });
        return null;
      }

      await act(async () => {
        root.render(<Harness />);
      });

      await act(async () => {
        await hook.startRun('What is attention?');
      });

      expect(hook.status).toBe('completed');
      expect(hook.servingModel).toBe('ag/gemini-3.8-flash-medium');
      expect(hook.messages).toHaveLength(2);
      expect(hook.messages[0].role).toBe('user');
      expect(hook.messages[0].content).toBe('What is attention?');
      expect(hook.messages[1].role).toBe('assistant');
      expect(hook.messages[1].content).toBe('Attention is all you need.');
      expect(hook.evidence).toHaveLength(1);
    });

    it('cancels running agent and prevents late events from overwriting state', async () => {
      const client = new ApiClient({ token: 'test-token' });

      vi.spyOn(client, 'createAgentRun').mockResolvedValue({
        run_id: 'run_cancel_test',
        paper_id: 'paper_1',
        status: 'queued',
      });

      vi.spyOn(client, 'cancelAgentRun').mockResolvedValue({
        run_id: 'run_cancel_test',
        paper_id: 'paper_1',
        status: 'cancelled',
      });

      let emitLateEvent: ((event: any) => void) | null = null;
      vi.spyOn(client, 'streamAgentRunEvents').mockImplementation(async (runId, onEvent, signal) => {
        emitLateEvent = onEvent;
        return new Promise((resolve) => {
          signal?.addEventListener('abort', () => resolve());
        });
      });

      let hook: any = null;
      function Harness() {
        hook = useAgentRun({ client, paperId: 'paper_1' });
        return null;
      }

      await act(async () => {
        root.render(<Harness />);
      });

      await act(async () => {
        // Start run without awaiting the entire long-lived stream
        hook.startRun('Long question to cancel');
      });

      // Polling is active or status is queued
      expect(hook.polling || hook.status === 'queued').toBe(true);

      // Cancel run
      await act(async () => {
        await hook.cancelRun();
      });

      expect(hook.status).toBe('cancelled');

      // Attempt to emit late event after cancellation
      if (emitLateEvent) {
        await act(async () => {
          emitLateEvent!({
            type: 'done',
            status: 'completed',
            answer_blocks: [{ text: 'LATE STALE ANSWER', evidence_ids: [] }],
          });
        });
      }

      // Late event must be discarded
      expect(hook.status).toBe('cancelled');
      expect(hook.answerBlocks.some((b: any) => b.text === 'LATE STALE ANSWER')).toBe(false);
    });
  });

  describe('MarkdownRenderer Component', () => {
    it('renders headings, bold, italic, lists, and code blocks without exposing raw markdown', async () => {
      const mdSample = `### Phương pháp chính
Bài báo đề xuất **T-RAG** [C1] với cấu trúc:
- **Hierarchical Index**: phân cấp bảng
- **Multi-stage Retrieval**: truy xuất đa tầng
1. Bước 1: Khởi tạo \`index\`
2. Bước 2: Truy xuất
> Trích dẫn kết quả thực nghiệm.`;

      await act(async () => {
        root.render(
          <Answer
            answerBlocks={[{ text: mdSample, evidence_ids: ['C1'] }]}
            evidence={[]}
            onSelectEvidence={vi.fn()}
          />
        );
      });

      // Verify headings rendered as HTML elements, not raw "###"
      const h5 = container.querySelector('h5');
      expect(h5).not.toBeNull();
      expect(h5?.textContent).toContain('Phương pháp chính');
      expect(container.textContent).not.toContain('###');

      // Verify bold rendered as <strong>, not raw "**"
      const strongs = container.querySelectorAll('strong');
      expect(strongs.length).toBeGreaterThanOrEqual(3);
      expect(strongs[0].textContent).toBe('T-RAG');
      expect(container.textContent).not.toContain('**T-RAG**');

      // Verify lists rendered as <ul> and <ol>, not raw "- " or "1. "
      const ul = container.querySelector('ul.md-ul');
      expect(ul).not.toBeNull();
      const ol = container.querySelector('ol.md-ol');
      expect(ol).not.toBeNull();

      // Verify inline code rendered as <code>, not raw backticks
      const code = container.querySelector('code.md-inline-code');
      expect(code).not.toBeNull();
      expect(code?.textContent).toBe('index');
      expect(container.textContent).not.toContain('`index`');

      // Verify blockquote rendered
      const bq = container.querySelector('blockquote.md-blockquote');
      expect(bq).not.toBeNull();

      // Verify citation link rendered as interactive button
      const citationBtn = container.querySelector('.citation-link');
      expect(citationBtn).not.toBeNull();
      expect(citationBtn?.textContent).toBe('1');
    });

    it('sanitizes and strips any accidental JSON, tool calls, or reasoning tags', async () => {
      const rawWithLeak = `<reasoning>Internal thinking step 1</reasoning>
<tool_call>search_evidence({"query": "leak"})</tool_call>
\`\`\`json
{"answer_blocks": [{"text": "Actual human response without leaks **highlight** [p1]."}]}
\`\`\``;

      await act(async () => {
        root.render(
          <Answer
            answerBlocks={[{ text: rawWithLeak, evidence_ids: ['p1'] }]}
            evidence={[]}
            onSelectEvidence={vi.fn()}
          />
        );
      });

      expect(container.textContent).not.toContain('<reasoning>');
      expect(container.textContent).not.toContain('Internal thinking');
      expect(container.textContent).not.toContain('<tool_call>');
      expect(container.textContent).not.toContain('search_evidence');
      expect(container.textContent).not.toContain('{"answer_blocks"');
      expect(container.textContent).toContain('Actual human response without leaks');

      // Formatted bold rendered
      const strong = container.querySelector('strong');
      expect(strong?.textContent).toBe('highlight');
    });

    it('renders exact links to other papers as clickable external anchor tags', async () => {
      const linkSample = `Bạn có thể tham khảo [Reformer: The Efficient Transformer](https://arxiv.org/abs/2001.04451) [ext_1] hoặc link trực tiếp https://arxiv.org/abs/2205.14135.`;

      await act(async () => {
        root.render(
          <Answer
            answerBlocks={[{ text: linkSample, evidence_ids: ['ext_1'] }]}
            evidence={[
              {
                passage_id: 'ext_1',
                parent_passage_id: 'ext_1',
                rank: 1,
                score: 1.0,
                section_heading: 'External Paper: Reformer',
                section_path: 'External Scholarly Literature',
                text: 'Reformer paper abstract',
                locator: { xpath: 'https://arxiv.org/abs/2001.04451', element_id: 'arxiv:2001.04451' },
              },
            ]}
            onSelectEvidence={vi.fn()}
          />
        );
      });

      const links = container.querySelectorAll('a.external-paper-link');
      expect(links.length).toBe(2);
      expect(links[0].getAttribute('href')).toBe('https://arxiv.org/abs/2001.04451');
      expect(links[0].getAttribute('target')).toBe('_blank');
      expect(links[0].textContent).toBe('Reformer: The Efficient Transformer');
      expect(links[1].getAttribute('href')).toBe('https://arxiv.org/abs/2205.14135');
    });
  });

  describe('Conversation Persistence Across Tab Switching', () => {
    it('persists and restores conversation history from chrome.storage.local', async () => {
      const storageMock: Record<string, any> = {};
      const chromeMock = {
        storage: {
          local: {
            get: vi.fn(async (key: string) => ({ [key]: storageMock[key] })),
            set: vi.fn(async (items: Record<string, any>) => {
              Object.assign(storageMock, items);
            }),
            remove: vi.fn(async (key: string) => {
              delete storageMock[key];
            }),
          },
          session: {
            remove: vi.fn(async () => {}),
            set: vi.fn(async () => {}),
            get: vi.fn(async () => ({})),
          },
        },
      };
      vi.stubGlobal('chrome', chromeMock);

      const client = new ApiClient({ token: 'test' });
      vi.spyOn(client, 'createAgentRun').mockResolvedValue({
        run_id: 'run_persist_1',
        paper_id: 'paper_1',
        status: 'completed',
        answer_blocks: [{ text: 'Here is the persisted answer', evidence_ids: ['p1'] }],
      });

      let hook: any;
      function Harness({ canonicalUrl, paperId }: { canonicalUrl: string; paperId: string }) {
        hook = useAgentRun({
          client,
          paperId,
          canonicalUrl,
        });
        return <div>{hook.messages.length}</div>;
      }

      // Step 1: User asks question on Paper A
      await act(async () => {
        root.render(
          <Harness canonicalUrl="https://arxiv.org/html/1706.03762v7" paperId="paper_1" />
        );
      });
      await act(async () => {
        await hook.startRun('What is transformer?');
      });

      expect(hook.messages.length).toBe(2);
      expect(hook.messages[0].content).toBe('What is transformer?');
      expect(hook.messages[1].content).toBe('Here is the persisted answer');

      // Verify stored in chrome.storage.local
      expect(storageMock['paperlens_chat_https://arxiv.org/html/1706.03762v7']).toBeDefined();
      expect(storageMock['paperlens_chat_https://arxiv.org/html/1706.03762v7'].messages).toHaveLength(2);

      // Step 2: User navigates/switches to Paper B or other tab
      await act(async () => {
        root.render(
          <Harness canonicalUrl="https://arxiv.org/html/2312.00000v1" paperId="paper_2" />
        );
      });
      // Paper B has no chat yet
      expect(hook.messages.length).toBe(0);

      // Step 3: User switches BACK to Paper A
      await act(async () => {
        root.render(
          <Harness canonicalUrl="https://arxiv.org/html/1706.03762v7" paperId="paper_1" />
        );
      });

      // Hook restores Paper A's conversation from chrome.storage.local!
      expect(hook.messages.length).toBe(2);
      expect(hook.messages[0].content).toBe('What is transformer?');
      expect(hook.messages[1].content).toBe('Here is the persisted answer');

      // Step 4: User clicks New Conversation / Reset
      await act(async () => {
        hook.resetConversation();
      });
      expect(hook.messages.length).toBe(0);
      expect(storageMock['paperlens_chat_https://arxiv.org/html/1706.03762v7']).toBeUndefined();

      vi.unstubAllGlobals();
    });

    it('renders external literature citations with link and without model badges', async () => {
      const answerBlocks = [
        {
          text: 'To extend the architecture for long sequences, Reformer introduces LSH attention [ext_reformer].',
          evidence_ids: ['ext_reformer'],
        },
      ];
      const evidence = [
        {
          passage_id: 'ext_reformer',
          parent_passage_id: 'ext_reformer',
          rank: 1,
          score: 0.95,
          section_heading: 'External Paper: Reformer',
          section_path: 'External Scholarly Literature',
          text: 'Reformer replaces dot-product attention with locality-sensitive hashing.',
          locator: {
            xpath: 'https://arxiv.org/abs/2001.04451',
            element_id: 'arxiv:2001.04451',
          },
          contributing_chunks: ['ext_reformer'],
          paper_id: 'arxiv:2001.04451',
        },
      ];

      const onSelect = vi.fn();
      const onJump = vi.fn();

      await act(async () => {
        root.render(
          <Answer
            answerBlocks={answerBlocks}
            evidence={evidence}
            servingModel="ag/gemini-3.8-flash-medium"
            onSelectEvidence={onSelect}
            onJump={onJump}
          />
        );
      });

      // Confirm no model names leaked
      expect(container.textContent).not.toContain('gemini');
      expect(container.textContent).not.toContain('claude');
      expect(container.textContent).not.toContain('ag/');

      // Verify citation link
      const citationBtn = container.querySelector('.citation-link') as HTMLButtonElement;
      expect(citationBtn).not.toBeNull();
      expect(citationBtn.textContent).toBe('1');

      // Click to open drawer
      await act(async () => {
        citationBtn.click();
      });

      expect(onSelect).toHaveBeenCalledWith('ext_reformer');

      // Verify drawer shows external paper badge and external paper link
      const previewCard = container.querySelector('.citation-preview-card');
      expect(previewCard).not.toBeNull();
      expect(previewCard?.textContent).toContain('External source 1');
      expect(previewCard?.textContent).toContain('External Paper: Reformer');

      const extLink = previewCard?.querySelector('a') as HTMLAnchorElement;
      expect(extLink).not.toBeNull();
      expect(extLink.href).toBe('https://arxiv.org/abs/2001.04451');
      expect(extLink.textContent).toContain('Open external paper');
    });
  });
});
