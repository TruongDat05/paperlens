/**
 * Render extracted evidence passages with source locators.
 *
 * Display the passage rank, enclosing section, text excerpt, and Jump action.
 * Distinguish active targets and maintain keyboard accessibility.
 */

import React from 'react';
import { EvidenceItem } from '../api/types';

interface EvidenceListProps {
  evidence: EvidenceItem[];
  activePassageId?: string | null;
  onJump: (item: EvidenceItem) => void;
  onSave?: (item: EvidenceItem) => void;
}

export const EvidenceList: React.FC<EvidenceListProps> = ({
  evidence,
  activePassageId,
  onJump,
  onSave,
}) => {
  if (evidence.length === 0) {
    return (
      <div className="empty-state" role="status">
        <p className="description">No matching evidence found in this paper.</p>
      </div>
    );
  }

  return (
    <section className="evidence-section" aria-label="Retrieved Evidence">
      <h2 className="section-title">Evidence Passages ({evidence.length})</h2>
      <ol className="evidence-list">
        {evidence.map((item) => {
          const isActive = activePassageId === item.passage_id;
          const isExternal = Boolean(
            item.section_path?.toLowerCase().includes('external') ||
            item.section_heading?.toLowerCase().includes('external') ||
            item.locator?.xpath?.startsWith('http') ||
            (item.paper_id && item.paper_id.startsWith('arxiv:'))
          );
          const externalUrl = item.locator?.xpath?.startsWith('http')
            ? item.locator.xpath
            : item.paper_id?.startsWith('arxiv:')
            ? `https://arxiv.org/abs/${item.paper_id.replace(/^arxiv:/, '')}`
            : null;

          return (
            <li
              key={item.passage_id}
              className={`evidence-card ${isActive ? 'active-target' : ''}`}
            >
              <div className="card-header">
                <span className={`badge ${isExternal ? 'badge-neutral' : 'badge-primary'}`}>
                  {isExternal ? 'External Paper' : `Rank #${item.rank}`}
                </span>
                <span className="section-heading" title={item.section_path}>
                  {item.section_heading}
                </span>
              </div>
              {item.text.length > 300 ? (
                <details className="evidence-excerpt">
                  <summary>{item.text.slice(0, 240)}… <span className="source-meta">Read full passage</span></summary>
                  <blockquote className="evidence-quote">"{item.text}"</blockquote>
                </details>
              ) : (
                <blockquote className="evidence-quote">"{item.text}"</blockquote>
              )}
              <div className="card-actions">
                {isExternal && externalUrl ? (
                  <a
                    href={externalUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn btn-secondary btn-sm"
                    aria-label={`Open external paper in new tab: ${item.section_heading}`}
                  >
                    Open paper
                  </a>
                ) : (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => onJump(item)}
                    aria-label={`Jump to passage in section ${item.section_heading}`}
                  >
                    Jump to source
                  </button>
                )}
                {onSave ? (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => onSave(item)}
                    aria-label={`Save quote from section ${item.section_heading}`}
                  >
                    Save quote
                  </button>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
};
