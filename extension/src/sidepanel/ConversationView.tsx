import React, { useRef, useEffect, useState, useCallback } from 'react';
import { ChatMessage } from './useAgentRun';
import { Answer } from './Answer';
import { ActivityProgress } from './ActivityProgress';
import { EvidenceItem } from '../api/types';
import { IconArrowDown, IconRefresh, IconSparkles } from './Icons';

interface ConversationViewProps {
  messages: ChatMessage[];
  evidence: EvidenceItem[];
  onFollowUp: (question: string) => void;
  exhausted?: boolean;
  onSelectEvidence: (evidenceId: string) => void;
  onJump: (item: EvidenceItem) => void;
  onSaveAnswer?: (text: string) => void;
  onRetry: () => void;
  isBusy: boolean;
  activeStep?: string | null;
}

export const ConversationView: React.FC<ConversationViewProps> = ({
  messages = [],
  evidence = [],
  onFollowUp,
  exhausted = false,
  onSelectEvidence,
  onJump,
  onSaveAnswer,
  onRetry,
  isBusy,
  activeStep,
}) => {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const bottomAnchorRef = useRef<HTMLDivElement>(null);
  const [showScrollBottom, setShowScrollBottom] = useState(false);
  const isNearBottomRef = useRef(true);

  // Check scroll position to determine if user is near bottom
  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    const nearBottom = distanceToBottom < 70;
    isNearBottomRef.current = nearBottom;
    setShowScrollBottom(!nearBottom && el.scrollHeight > el.clientHeight + 100);
  }, []);

  // Smooth scroll to bottom
  const scrollToBottom = useCallback((smooth = true) => {
    const el = scrollContainerRef.current;
    if (el) {
      el.scrollTo?.({ top: el.scrollHeight, behavior: smooth && !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'smooth' : 'auto' });
      isNearBottomRef.current = true;
      setShowScrollBottom(false);
    }
  }, []);

  // Auto-scroll when messages update, but ONLY if user is already near bottom
  useEffect(() => {
    if (isNearBottomRef.current) {
      scrollToBottom(true);
    }
  }, [messages, activeStep, scrollToBottom]);

  const hasMessages = messages.length > 0;

  return (
    <div className="conversation-container">
    <div
      ref={scrollContainerRef}
      className="conversation-scroll-area"
      onScroll={handleScroll}
      role="log"
      aria-live="polite"
      aria-label="Conversation with PaperLens"
    >
      {!hasMessages ? (
        <section className="starter-hero" aria-label="Research conversation">
          <div className="starter-hero-icon">
            <IconSparkles size={28} />
          </div>
          <h2 className="starter-hero-title">Explore this paper</h2>
          <p className="starter-hero-description">
            PaperLens retrieves paragraphs from this arXiv document, and attached research images, and generates answers in your requested language with source citations.
          </p>

        </section>
      ) : (
        <div className="messages-list">
          {messages.map((msg, index) => {
            if (msg.role === 'user') {
              return (
                <div key={msg.id} className="message-wrapper message-user-wrapper">
                  <div className="message-user-bubble">
                    {msg.attachments && msg.attachments.length > 0 ? (
                      <div className="user-message-attachments">
                        {msg.attachments.map((att) => (
                          <div key={att.id} className="user-attachment-card">
                            {att.dataUrl ? (
                              <img
                                src={att.dataUrl}
                                alt={att.name}
                                className="user-attachment-img"
                                title={att.name}
                              />
                            ) : (
                              <div className="user-attachment-doc">
                                <span className="doc-icon">📄</span>
                                <span className="doc-name">{att.name}</span>
                                <span className="doc-size">({Math.round(att.size / 1024)} KB)</span>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : null}
                    <p className="message-text">{msg.content}</p>
                  </div>
                </div>
              );
            }

            // Assistant message
            const isLastMessage = index === messages.length - 1;
            const isInFlight = isLastMessage && (msg.isStreaming || isBusy);
            const blocks = msg.answerBlocks || [];
            const msgEvidence = msg.evidence || [];

            return (
              <div key={msg.id} className="message-wrapper message-assistant-wrapper">
                {/* In-flight activity indicator during generation only - keeps completed answers clean like web AI */}
                {isInFlight ? (
                  <ActivityProgress
                    activityState={msg.activityState || activeStep}
                    toolActivities={msg.toolActivities || []}
                    isStreaming={isInFlight}
                  />
                ) : null}

                {/* Answer Content */}
                <Answer
                  answerBlocks={blocks}
                  evidence={msgEvidence}
                  servingModel={msg.servingModel}
                  fallbackReason={msg.fallbackReason}
                  limitations={msg.limitations}
                  streamingText={msg.content}
                  isStreaming={isInFlight}
                  onSelectEvidence={onSelectEvidence}
                  onSaveAnswer={onSaveAnswer}
                  onJump={onJump}
                />

                {!isInFlight && !!msg.followUps?.length && ['completed', 'partial'].includes(msg.status || '') && (
                  <div className="follow-up-questions" aria-label="Continue this research discussion">
                    {msg.followUps.map(question => <button type="button" key={question} disabled={isBusy || exhausted}
                      className="follow-up-question" onClick={() => onFollowUp(question)}>{question}</button>)}
                  </div>
                )}

                {!isInFlight && blocks.length === 0 && !msg.content && msg.limitations && (
                  <div className="alert alert-warning" role="alert"><p>{msg.limitations}</p>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry} disabled={isBusy || exhausted}>Retry question</button>
                  </div>
                )}

                {/* Failure and Retry Action */}
                {(msg.error || msg.status === 'failed') ? (
                  <div className="alert alert-danger message-error" role="alert">
                    <p>{msg.error || 'Request failed'}</p>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm retry-btn"
                      onClick={onRetry}
                    >
                      <IconRefresh size={12} />
                      <span>Retry question</span>
                    </button>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}

      {/* Anchor for auto-scrolling */}
      <div ref={bottomAnchorRef} className="scroll-anchor" />

    </div>
      <div className="conversation-scroll-controls">
      {/* Reserved space keeps the scroll control off the answer text. */}
      {showScrollBottom ? (
        <button
          type="button"
          className="jump-to-bottom-btn"
          onClick={() => scrollToBottom(true)}
          aria-label="Jump to latest message"
        >
          <IconArrowDown size={14} />
          <span>Jump to latest</span>
        </button>
      ) : null}
      </div>
    </div>
  );
};
