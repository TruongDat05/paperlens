import React from 'react';
import { PaperStatusResponse } from '../api/types';
import { PageContext, PageType } from '../messages';
import { IconLogo, IconSun, IconMoon, IconPlus, IconHistory, IconSettings } from './Icons';

interface HeaderProps {
  context: PageContext | null;
  paperStatus: PaperStatusResponse | null;
  mode: 'agent' | 'evidence';
  onModeChange: (mode: 'agent' | 'evidence') => void;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  onNewConversation: () => void;
  isBusy: boolean;
  canReset: boolean;
  isAnalyzing?: boolean;
  displayName?: string;
  onHistory?: ()=>void;
  onSettings?: ()=>void;
  view?: 'chat'|'history'|'settings';
}

export const Header: React.FC<HeaderProps> = ({
  context,
  paperStatus,
  mode,
  onModeChange,
  theme,
  onToggleTheme,
  onNewConversation,
  isBusy,
  canReset,
  isAnalyzing,
  displayName,onHistory,onSettings,view,
}) => {
  const paperTitle = paperStatus?.title || (context?.arxivId ? `arXiv:${context.arxivId}` : '');
  const isLexicalReady = Boolean(paperStatus?.lexical_ready);
  const isSemanticReady = Boolean(paperStatus?.semantic_ready);

  return (
    <header className="panel-header" role="banner">
      <div className="header-main-row">
        <div className="header-brand">
          <IconLogo size={20} className="brand-logo" />
          <div className="brand-text">
            <div className="brand-title-line">
              <h1 className="panel-title">PaperLens</h1>
              {context?.arxivId ? (
                <span className="badge badge-meta" title={`arXiv ${context.arxivId} ${context.version || ''}`}>
                  {context.arxivId}
                  {context.version ? ` (${context.version})` : ''}
                </span>
              ) : null}
            </div>
            {paperTitle ? (
              <p className="paper-title-compact" title={paperTitle}>
                {paperTitle}
              </p>
            ) : null}
          </div>
        </div>

        <div className="header-controls">
          {onHistory && <button className={`icon-control-btn ${view==='history' ? 'selected' : ''}`} disabled={isBusy}
            onClick={onHistory} aria-label="Chat history" title="Chat history"><IconHistory size={16}/></button>}
          {onSettings && <button className={`account-avatar-btn ${view==='settings' ? 'selected' : ''}`} disabled={isBusy}
            onClick={onSettings} aria-label="Settings and memory" title={displayName ? `${displayName} · Settings and memory` : 'Settings and memory'}>
            {displayName ? <span aria-hidden="true">{displayName.split(/\s+/).map(part=>part[0]).slice(0,2).join('').toUpperCase()}</span> : <IconSettings size={16}/>}</button>}
          {/* New Conversation Button */}
          {(
            <button
              type="button"
              className="icon-control-btn"
              onClick={onNewConversation}
              disabled={isBusy}
              title="Start a new conversation"
              aria-label="Start new conversation"
            >
              <IconPlus size={16} />
            </button>
          )}

          {/* Theme Toggle Button */}
          <button
            type="button"
            className="icon-control-btn"
            onClick={onToggleTheme}
            title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          >
            {theme === 'dark' ? <IconSun size={16} /> : <IconMoon size={16} />}
          </button>
        </div>
      </div>

      {/* Sub-bar: Readiness Status & Answering Mode Pill */}
      {paperStatus?.paper_id || context?.pageType === PageType.HTML ? (
        <div className="header-sub-row">
          <div className="status-indicator-pill" role="status">
            <span
              className={`status-dot ${isLexicalReady ? 'status-ready' : 'status-indexing'}`}
              aria-hidden="true"
            />
            <span className="status-text">
              {isLexicalReady
                ? 'Lexical Ready'
                : isAnalyzing
                ? 'Indexing paper...'
                : 'Indexing'}
              {isSemanticReady ? ' • Dense Ready' : ''}
            </span>
          </div>

          <div className="mode-toggle-pill" role="tablist" aria-label="Answering Mode">
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'agent'}
              className={`mode-pill-btn ${mode === 'agent' ? 'active' : ''}`}
              onClick={() => onModeChange('agent')}
            >
              Agent QA
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'evidence'}
              className={`mode-pill-btn ${mode === 'evidence' ? 'active' : ''}`}
              onClick={() => onModeChange('evidence')}
            >
              Search Passages
            </button>
          </div>
        </div>
      ) : null}
    </header>
  );
};
