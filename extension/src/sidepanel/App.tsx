/**
 * Lay out the paper-reading and question interface in the side panel.
 *
 * Coordinate usePaper, useAgentRun, Header, ConversationView, Composer,
 * EvidenceList, and library to provide a polished conversational AI assistant.
 *
 * Support Clean White and GitHub-inspired Dark themes, live custom appearance preferences,
 * genuine incremental streaming, multiline composer with IME safety, real tool execution tracking,
 * and robust source citation navigation.
 */

import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { ApiClient } from '../api/client';
import { usePaper } from './usePaper';
import { useAgentRun, ComposerAttachment } from './useAgentRun';
import { Header } from './Header';
import { ConversationView } from './ConversationView';
import { Composer } from './Composer';
import { EvidenceList } from './EvidenceList';
import { AccountProfile, EvidenceItem, ResearchLevel } from '../api/types';
import { PageType, JumpStatus } from '../messages';
import { saveNote } from './library';
import { IconSparkles } from './Icons';
import { AccountPanel, claimLegacyStorage } from './AccountPanel';
import { HistoryPanel } from './HistoryPanel';
import {
  AppearancePreferences,
  DEFAULT_PRESET_LIGHT,
  loadAppearancePreferences,
  saveAppearancePreferences,
  applyAppearanceToDOM,
} from './theme';

export const App: React.FC = () => {
  const client = useMemo(() => new ApiClient(), []);
  const [account, setAccount] = useState<AccountProfile | null>(null);
  const [error, setError] = useState('');
  const [appearance, setAppearance] = useState<AppearancePreferences>(DEFAULT_PRESET_LIGHT);

  // Initialize and apply appearance preferences
  useEffect(() => {
    void loadAppearancePreferences().then((loaded) => {
      setAppearance(loaded);
      applyAppearanceToDOM(loaded);
    });
  }, []);

  const refresh = useCallback(async () => {
    setError('');
    try {
      const next = await client.getAccount();
      await claimLegacyStorage(next.owner_id);
      setAccount(next);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [client]);

  useEffect(() => {
    void refresh();
    const listener = (changes: Record<string, chrome.storage.StorageChange>) => {
      if (changes[client.sessionStorageKey]) void refresh();
    };
    if (typeof chrome !== 'undefined') chrome.storage?.onChanged?.addListener(listener);
    return () => {
      if (typeof chrome !== 'undefined') chrome.storage?.onChanged?.removeListener(listener);
    };
  }, [refresh, client]);

  if (!account)
    return (
      <main className="panel-container account-loading">
        <IconSparkles size={24} />
        {error ? (
          <>
            <p role="alert">{error}</p>
            <button className="btn btn-secondary" onClick={() => void refresh()}>
              Reconnect
            </button>
          </>
        ) : (
          <p role="status">Opening your research workspace…</p>
        )}
      </main>
    );

  if (!account.onboarded)
    return (
      <main className="panel-container account-setup">
        <AccountPanel
          key={account.owner_id}
          client={client}
          account={account}
          onSaved={setAccount}
          refresh={refresh}
          onboarding
          appearance={appearance}
          onAppearanceChange={setAppearance}
        />
      </main>
    );

  return (
    <Workspace
      key={account.owner_id}
      client={client}
      account={account}
      onAccountSaved={setAccount}
      refreshAccount={refresh}
      appearance={appearance}
      onAppearanceChange={setAppearance}
    />
  );
};

const Workspace: React.FC<{
  client: ApiClient;
  account: AccountProfile;
  onAccountSaved: (account: AccountProfile) => void;
  refreshAccount: () => Promise<void>;
  appearance: AppearancePreferences;
  onAppearanceChange: (prefs: AppearancePreferences) => void;
}> = ({ client, account, onAccountSaved, refreshAccount, appearance, onAppearanceChange }) => {
  const {
    context,
    loading,
    analyzing,
    consentGranted,
    grantConsent,
    paperId,
    paperStatus,
    error: paperError,
    analyze,
    jump,
  } = usePaper(client, account.owner_id);

  const [view, setView] = useState<'chat' | 'history' | 'settings'>('chat');

  const [mode, setMode] = useState<'agent' | 'evidence'>('agent');
  const [reasoningLevel, setReasoningLevel] = useState<ResearchLevel>('low');
  const [chatRevision, setChatRevision] = useState(0);
  const [retrieving, setRetrieving] = useState(false);
  const [evidenceB1, setEvidenceB1] = useState<EvidenceItem[]>([]);
  const [activePassageId, setActivePassageId] = useState<string | null>(null);
  const [jumpFeedback, setJumpFeedback] = useState<string | null>(null);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [saveFeedback, setSaveFeedback] = useState<string | null>(null);
  const [composerDraft, setComposerDraft] = useState<string>('');

  const toggleTheme = useCallback(() => {
    const nextTheme = appearance.theme === 'dark' ? 'light' : 'dark';
    const next: AppearancePreferences = {
      ...appearance,
      theme: nextTheme,
    };
    onAppearanceChange(next);
    applyAppearanceToDOM(next);
    void saveAppearancePreferences(next);
  }, [appearance, onAppearanceChange]);

  const {
    status: agentStatus,
    polling: agentPolling,
    activeStep: agentActiveStep,
    answerBlocks,
    evidence: agentEvidence,
    servingModel,
    fallbackReason,
    limitations,
    errorMessage: agentError,
    history,
    messages,
    startRun,
    cancelRun,
    resetConversation,
    retryLastTurn,
    restoreConversation,
    budget,
  } = useAgentRun({
    client,
    paperId,
    arxivId: context?.arxivId,
    version: context?.version,
    canonicalUrl: context?.canonicalUrl,
    ownerId: account.owner_id,
  });

  const retrievalGeneration = useRef(0);
  useEffect(() => {
    ++retrievalGeneration.current;
    setEvidenceB1([]);
    setRetrieving(false);
    setQueryError(null);
    setActivePassageId(null);
    setJumpFeedback(null);
    setSaveFeedback(null);
  }, [paperId]);

  useEffect(() => {
    setComposerDraft('');
  }, [context?.canonicalUrl, context?.arxivId, context?.version]);

  useEffect(() => () => {
    ++retrievalGeneration.current;
  }, []);

  const handleSearchB1 = async (queryText: string) => {
    if (!paperId || !queryText.trim()) return;

    const epoch = ++retrievalGeneration.current;
    setEvidenceB1([]);
    setRetrieving(true);
    setQueryError(null);
    setJumpFeedback(null);

    try {
      const res = await client.retrieve({
        request_id: `req_${Date.now()}`,
        paper_id: paperId,
        question: queryText.trim(),
        top_k: 5,
      });
      if (retrievalGeneration.current !== epoch) return;
      setEvidenceB1(res.evidence);
    } catch (err) {
      if (retrievalGeneration.current === epoch) setQueryError((err as Error).message);
    } finally {
      if (retrievalGeneration.current === epoch) setRetrieving(false);
    }
  };

  const handleAsk = async (
    queryText: string,
    attachments?: ComposerAttachment[],
    level: ResearchLevel = reasoningLevel
  ) => {
    if (!queryText.trim() && (!attachments || attachments.length === 0)) return;
    setQueryError(null);
    setJumpFeedback(null);
    setSaveFeedback(null);

    let activeId = paperId;
    if (!activeId) {
      activeId = await analyze();
    }
    if (!activeId) {
      setQueryError('Could not index paper. Please make sure the paper page is fully loaded.');
      return;
    }

    if (mode === 'agent') {
      await startRun(queryText, 'A2', attachments, activeId, level);
    } else {
      await handleSearchB1(queryText);
    }
  };

  const handleJump = useCallback(
    async (item: EvidenceItem) => {
      setActivePassageId(item.passage_id);
      setJumpFeedback(null);

      if (!context?.arxivId) return;

      const res = await jump({
        elementId: item.locator.element_id,
        selector: item.locator.selector,
        sectionId: item.section_id || item.locator.element_id,
        fingerprint: item.fingerprint || '',
        arxivId: context.arxivId,
        version: context.version || 'unknown',
      });

      if (res.status === JumpStatus.VERIFIED) {
        setJumpFeedback('Source paragraph verified and highlighted.');
      } else if (res.status === JumpStatus.SECTION_FALLBACK) {
        setJumpFeedback(`Navigated to section fallback (${res.fallbackSectionId}).`);
      } else {
        setJumpFeedback('Source location could not be verified in the active document.');
      }

      setTimeout(() => setJumpFeedback(null), 4000);
    },
    [context, jump]
  );

  const handleCitationSelect = useCallback(
    (evidenceId: string) => {
      setActivePassageId(evidenceId);
    },
    []
  );

  const handleSaveAnswerToNotes = async (text: string) => {
    if (!paperId || !context?.arxivId) return;
    try {
      await saveNote({
        paperId,
        arxivId: context.arxivId,
        version: context.version || 'unknown',
        title: paperStatus?.title || `arXiv:${context.arxivId}`,
        canonicalUrl: context.canonicalUrl || `https://arxiv.org/html/${context.arxivId}`,
        text,
        type: 'answer',
      });
      setSaveFeedback('Answer saved to your local PaperLens notes.');
    } catch {
      setSaveFeedback('Failed to save answer to notes.');
    }
    setTimeout(() => setSaveFeedback(null), 4000);
  };

  const isBusy = mode === 'agent' ? agentPolling : retrieving;
  const displayError = paperError || queryError || agentError;

  if (loading) {
    return (
      <main className="panel-container" role="main" aria-label="Loading PaperLens">
        <header className="panel-header">
          <div className="header-brand">
            <IconSparkles size={20} className="brand-logo" />
            <h1 className="panel-title">PaperLens</h1>
          </div>
        </header>
        <div className="empty-state-loading" role="status">
          <span className="activity-pulse-dot" aria-hidden="true" />
          <p className="description">Detecting arXiv paper context...</p>
        </div>
      </main>
    );
  }

  return (
    <main className="panel-container" role="main" aria-label="PaperLens Research Assistant">
      <Header
        context={context}
        paperStatus={paperStatus}
        mode={mode}
        onModeChange={setMode}
        theme={appearance.theme}
        onToggleTheme={toggleTheme}
        onNewConversation={() => {
          resetConversation();
          setComposerDraft('');
          setChatRevision((value) => value + 1);
          setView('chat');
        }}
        isBusy={isBusy}
        canReset={messages.length > 0}
        isAnalyzing={analyzing}
        displayName={account.identities[0]?.display_name || account.name}
        onHistory={() => setView(view === 'history' ? 'chat' : 'history')}
        onSettings={() => setView(view === 'settings' ? 'chat' : 'settings')}
        view={view}
      />

      {view !== 'chat' && (
        <div className="page-toolbar">
          <button className="btn btn-ghost btn-sm" onClick={() => setView('chat')}>
            Back to chat
          </button>
        </div>
      )}

      {view === 'settings' && (
        <div className="settings-scroll">
          <AccountPanel
            client={client}
            account={account}
            onSaved={onAccountSaved}
            refresh={refreshAccount}
            appearance={appearance}
            onAppearanceChange={onAppearanceChange}
          />
        </div>
      )}

      {view === 'history' && (
        <HistoryPanel
          client={client}
          ownerId={account.owner_id}
          canonicalUrl={context?.canonicalUrl}
          onRestore={(saved) => {
            restoreConversation(saved);
            setComposerDraft('');
            setChatRevision((value) => value + 1);
            setView('chat');
          }}
          onDeleted={(id) => {
            if (budget.chat_id === id) resetConversation();
          }}
        />
      )}

      {/* Global alert for paper/query errors (shown only in chat view) */}
      {view === 'chat' && displayError ? (
        <div className="alert alert-danger global-paper-alert" role="alert">
          {displayError}
        </div>
      ) : null}

      {/* Transient feedback toast */}
      {jumpFeedback ? (
        <div className="feedback-toast" role="status">
          {jumpFeedback}
        </div>
      ) : null}

      {saveFeedback ? (
        <div className="feedback-toast" role="status">
          {saveFeedback}
        </div>
      ) : null}

      {/* Unsupported or Abstract page guidance */}
      {view === 'chat' && context?.pageType === PageType.UNSUPPORTED ? (
        <div className="card notice-card" role="region" aria-label="Unsupported Page">
          <h3>Unsupported Page</h3>
          <p className="description">
            Please navigate to an arXiv HTML paper (e.g. <code>https://arxiv.org/html/...</code>) to use PaperLens.
          </p>
        </div>
      ) : null}

      {view === 'chat' && context?.pageType === PageType.ABSTRACT ? (
        <div className="card notice-card" role="region" aria-label="arXiv Abstract Page">
          <h3>arXiv Abstract Page</h3>
          <p className="description">
            PaperLens operates directly on arXiv HTML papers with full-text paragraph navigation.
          </p>
          {context.htmlUrl ? (
            <a href={context.htmlUrl} target="_blank" rel="noreferrer" className="btn btn-primary">
              Open HTML Version
            </a>
          ) : (
            <p className="description text-warning">
              No experimental HTML conversion is available for this paper.
            </p>
          )}
        </div>
      ) : null}

      {/* HTML Page flow */}
      {view === 'chat' && context?.pageType === PageType.HTML ? (
        <div className="qa-workspace" aria-label="Paper Assistant Workspace">
          {mode === 'agent' ? (
            <>
              {/* Conversational Layout */}
              <ConversationView
                messages={messages}
                evidence={agentEvidence}
                onFollowUp={(question) => handleAsk(question)}
                exhausted={budget?.chat_exhausted}
                onSelectEvidence={handleCitationSelect}
                onJump={handleJump}
                onSaveAnswer={handleSaveAnswerToNotes}
                onRetry={retryLastTurn}
                isBusy={agentPolling}
                activeStep={agentActiveStep}
              />

              {/* Accessible Multiline Composer */}
              <Composer
                key={`${context?.canonicalUrl || context?.arxivId}:${chatRevision}`}
                onSend={handleAsk}
                level={reasoningLevel}
                onLevelChange={setReasoningLevel}
                onStop={cancelRun}
                isBusy={agentPolling}
                disabled={false}
                tokensUsed={budget?.tokens_used}
                tokenLimit={budget?.token_limit}
                exhausted={budget?.chat_exhausted}
                usageEstimated={budget?.usage_estimated}
                draftText={composerDraft}
                onDraftChange={setComposerDraft}
              />
            </>
          ) : (
            /* Evidence Search (B1) mode */
            <div className="evidence-search-view" role="region" aria-label="Evidence Passages Search">
              <div className="evidence-search-box">
                <label htmlFor="b1-search-input" className="form-label">
                  Search evidence passages:
                </label>
                <div className="input-group">
                  <input
                    id="b1-search-input"
                    type="text"
                    className="text-input"
                    placeholder="Search paper paragraphs..."
                    value={composerDraft}
                    onChange={(e) => setComposerDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && composerDraft.trim()) {
                        e.preventDefault();
                        handleSearchB1(composerDraft);
                      }
                    }}
                    maxLength={1024}
                    disabled={retrieving}
                  />
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={retrieving || !composerDraft.trim()}
                    onClick={() => handleSearchB1(composerDraft)}
                  >
                    {retrieving ? 'Searching...' : 'Search'}
                  </button>
                </div>
              </div>

              <EvidenceList
                evidence={evidenceB1}
                activePassageId={activePassageId}
                onJump={handleJump}
              />
            </div>
          )}
        </div>
      ) : null}
    </main>
  );
};
