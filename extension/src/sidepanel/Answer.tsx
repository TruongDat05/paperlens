/**
 * Display answers and link them to the corresponding evidence.
 *
 * Show backend-validated answer blocks for completed, partial, or
 * evidence_only outcomes. Link evidence_ids to evidence cards and display
 * the actual model, fallback reason, or limitations when available.
 */

import React, { useState } from 'react';
import { AnswerBlock, EvidenceItem } from '../api/types';
import { MarkdownRenderer } from './MarkdownRenderer';
import {
  IconCopy,
  IconCheck,
  IconBookmark,
  IconJump,
  IconSparkles,
  IconExternalLink,
} from './Icons';

export interface AnswerProps {
  answerBlocks: AnswerBlock[];
  evidence: EvidenceItem[];
  servingModel?: string | null;
  fallbackReason?: string | null;
  limitations?: string | null;
  onSelectEvidence: (evidenceId: string) => void;
  onSaveAnswer?: (text: string) => void;
  onJump?: (item: EvidenceItem) => void;
  streamingText?: string;
  isStreaming?: boolean;
}

export const Answer: React.FC<AnswerProps> = ({
  answerBlocks,
  evidence,
  servingModel,
  fallbackReason,
  limitations,
  onSelectEvidence,
  onSaveAnswer,
  onJump,
  streamingText,
  isStreaming = false,
}) => {
  const [copied, setCopied] = useState(false);
  const [saved, setSaved] = useState(false);
  const [expandedCitationId, setExpandedCitationId] = useState<string | null>(null);

  const hasBlocks = answerBlocks && answerBlocks.length > 0;
  const hasStreamingText = Boolean(streamingText && streamingText.trim());

  if (!hasBlocks && !hasStreamingText && !isStreaming) {
    return null;
  }

  const fullAnswerText = hasBlocks
    ? answerBlocks.map((b) => b.text).join('\n\n')
    : streamingText || '';

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(fullAnswerText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback
    }
  };

  const handleSave = () => {
    if (onSaveAnswer && fullAnswerText) {
      onSaveAnswer(fullAnswerText);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    }
  };

  const citationIds = [...new Set(answerBlocks.flatMap(block => block.evidence_ids || []))];
  const citationLabels = Object.fromEntries(citationIds.map((id, index) => [id, index + 1]));
  const handleCitationClick = (eid: string) => {
    const source = evidence.find(item => item.passage_id === eid || item.parent_passage_id === eid);
    if (source && onJump && !/^(ext_|img_|chat_|mem_|profile_)/.test(eid)) onJump(source);
    else onSelectEvidence(eid);
    setExpandedCitationId((prev) => (prev === eid ? null : eid));
  };

  const activeEvidenceItem = expandedCitationId
    ? (evidence || []).find(
        (e) =>
          e.passage_id === expandedCitationId ||
          e.parent_passage_id === expandedCitationId
      )
    : null;

  const isExternal = Boolean(
    activeEvidenceItem?.section_path?.toLowerCase().includes('external') ||
    activeEvidenceItem?.section_heading?.toLowerCase().includes('external') ||
    activeEvidenceItem?.locator?.xpath?.startsWith('http') ||
    (activeEvidenceItem?.paper_id && activeEvidenceItem.paper_id.startsWith('arxiv:'))
  );
  const isMemory = expandedCitationId?.startsWith('mem_');

  const externalUrl = activeEvidenceItem?.locator?.xpath?.startsWith('http')
    ? activeEvidenceItem.locator.xpath
    : activeEvidenceItem?.paper_id?.startsWith('arxiv:')
    ? `https://arxiv.org/abs/${activeEvidenceItem.paper_id.replace(/^arxiv:/, '')}`
    : null;

  const actionableLimitations = limitations?.replace(/Citation IDs were checked; semantic support for synthesized claims is unverified\./g, '').trim();
  const sanitizedFallbackReason = fallbackReason
    ? fallbackReason
        .replace(/claude\s+(failover|fallback)\s+applied/gi, 'Alternative research provider applied')
        .replace(/(claude|gemini|anthropic|google|ag\/[a-z0-9_.-]+)/gi, 'secondary provider')
    : null;

  return (
    <article className="card answer-card" aria-label="Generated Answer">
      <header className="answer-header">
        <div className="answer-title-group">
          <IconSparkles size={16} className="assistant-avatar-icon" />
          <h2 className="card-title">PaperLens</h2>
        </div>

        <div className="answer-top-actions">
          <button
            type="button"
            className="action-btn"
            onClick={handleCopy}
            title={copied ? 'Copied to clipboard' : 'Copy answer'}
            aria-label={copied ? 'Answer copied' : 'Copy answer to clipboard'}
          >
            {copied ? <IconCheck size={14} className="text-success" /> : <IconCopy size={14} />}
            <span className="action-label">{copied ? 'Copied' : 'Copy'}</span>
          </button>

          {onSaveAnswer ? (
            <button
              type="button"
              className="action-btn"
              onClick={handleSave}
              title={saved ? 'Saved to notes' : 'Save to notes'}
              aria-label={saved ? 'Answer saved' : 'Save answer to local notes'}
            >
              {saved ? <IconCheck size={14} className="text-success" /> : <IconBookmark size={14} />}
              <span className="action-label">{saved ? 'Saved' : 'Save'}</span>
            </button>
          ) : null}
        </div>
      </header>

      {sanitizedFallbackReason ? (
        <div className="alert alert-warning" role="note">
          {sanitizedFallbackReason}
        </div>
      ) : null}

      <div className="answer-content">
        {hasBlocks ? (
          answerBlocks.map((block, idx) => {
            // Include any evidence_ids not already present in block text
            const unmentionedEids = (block.evidence_ids || []).filter(
              (eid) => !block.text.includes(`[${eid}]`)
            );
            const blockText = unmentionedEids.length > 0
              ? `${block.text} ${unmentionedEids.map((id) => `[${id}]`).join(' ')}`
              : block.text;

            return (
              <div key={idx} className="answer-block-item">
                <MarkdownRenderer
                  content={blockText}
                  onCitationClick={handleCitationClick}
                  activeCitationId={expandedCitationId}
                  citationLabels={citationLabels}
                />
              </div>
            );
          })
        ) : hasStreamingText ? (
          <div className="streaming-text-container">
            <MarkdownRenderer
              content={streamingText || ''}
              onCitationClick={handleCitationClick}
              activeCitationId={expandedCitationId}
            />
            {isStreaming ? <span className="streaming-cursor" aria-hidden="true" /> : null}
          </div>
        ) : null}
      </div>

      {/* Expandable citation drawer/card when a citation is selected */}
      {activeEvidenceItem ? (
        <div className="citation-preview-card" role="region" aria-label="Referenced source passage">
          <div className="citation-preview-header">
            <span className={`badge ${isExternal ? 'badge-neutral' : 'badge-primary'}`}>
              {`${isMemory ? 'Memory' : isExternal ? 'External source' : 'Source'} ${citationLabels[expandedCitationId!] || ''}`}
            </span>
            <span className="citation-preview-heading" title={activeEvidenceItem.section_heading}>
              {activeEvidenceItem.section_heading}
            </span>
            <button
              type="button"
              className="citation-close-btn"
              onClick={() => setExpandedCitationId(null)}
              aria-label="Close citation details"
            >
              ✕
            </button>
          </div>
          <details className="citation-preview-excerpt"><summary>{activeEvidenceItem.text.slice(0, 200)}{activeEvidenceItem.text.length > 200 ? '…' : ''}</summary>
            <blockquote className="citation-preview-quote">{activeEvidenceItem.text}</blockquote>
          </details>
          <div className="citation-preview-actions">
            {isExternal && externalUrl ? (
              <a
                href={externalUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-secondary btn-sm"
                aria-label={`Open external paper in new tab: ${activeEvidenceItem.section_heading}`}
              >
                <IconExternalLink size={12} />
                <span>{isMemory ? 'Open memory source' : 'Open external paper'}</span>
              </a>
            ) : onJump && !/^(img_|chat_|mem_|profile_)/.test(activeEvidenceItem.passage_id) ? (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => onJump(activeEvidenceItem)}
                aria-label={`Jump to passage in section ${activeEvidenceItem.section_heading}`}
              >
                <IconJump size={12} />
                <span>Jump to source paragraph</span>
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      {actionableLimitations ? (
        <p className="description text-warning answer-limitations" role="note">
          {actionableLimitations}
        </p>
      ) : null}
    </article>
  );
};
