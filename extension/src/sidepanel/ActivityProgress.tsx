import React, { useState } from 'react';
import { ToolActivity } from './useAgentRun';
import {
  IconSearch,
  IconBookOpen,
  IconPen,
  IconChevronDown,
  IconChevronUp,
} from './Icons';

interface ActivityProgressProps {
  activityState?: string | null;
  toolActivities?: ToolActivity[];
  isStreaming?: boolean;
}

export const ActivityProgress: React.FC<ActivityProgressProps> = ({
  activityState,
  toolActivities = [],
  isStreaming = false,
}) => {
  const [expanded, setExpanded] = useState(false);

  // Return nothing if neither in-flight activity nor tools to display
  if (!activityState && toolActivities.length === 0) {
    return null;
  }

  const getPhaseIcon = (state: string) => {
    const s = state.toLowerCase();
    if (s.includes('search') || s.includes('retriev') || s.includes('literature')) {
      return <IconSearch size={14} className="activity-icon" />;
    }
    if (s.includes('read') || s.includes('source') || s.includes('outline')) {
      return <IconBookOpen size={14} className="activity-icon" />;
    }
    return <IconPen size={14} className="activity-icon" />;
  };

  const getToolLabel = (toolName?: string) => {
    if (!toolName) return 'Tool Action';
    switch (toolName) {
      case 'search_evidence':
        return 'Search Paper';
      case 'search_external_papers':
        return 'Search External Literature';
      case 'read_section':
        return 'Read Section';
      case 'get_paper_outline':
        return 'Paper Outline';
      default:
        return toolName.replace(/_/g, ' ');
    }
  };

  return (
    <div className="activity-container" role="status" aria-live="polite">
      {/* Active Phase Row */}
      {activityState ? (
        <div className="activity-phase-row">
          <span className="activity-pulse-dot" aria-hidden="true" />
          <span className="activity-phase-text">
            {getPhaseIcon(activityState)}
            {activityState}
          </span>
        </div>
      ) : null}

      {/* Real Executed Tool Activity Chips/Rows */}
      {toolActivities.length > 0 ? (
        <div className="tool-activity-section">
          <div className="tool-summary-bar">
            <span className="tool-count-meta">
              {toolActivities.length} tool {toolActivities.length === 1 ? 'action' : 'actions'}
            </span>
            <button
              type="button"
              className="tool-toggle-btn"
              onClick={() => setExpanded(!expanded)}
              aria-expanded={expanded}
              aria-label={expanded ? 'Hide tool execution details' : 'Show tool execution details'}
            >
              <span>{expanded ? 'Hide details' : 'View details'}</span>
              {expanded ? <IconChevronUp size={12} /> : <IconChevronDown size={12} />}
            </button>
          </div>

          <div className={`tool-chips-list ${expanded ? 'expanded' : 'collapsed'}`}>
            {toolActivities.map((tool) => {
              const query = tool.arguments?.query;
              const section = tool.arguments?.heading || tool.arguments?.section_id;
              const target = query ? `"${query}"` : section ? `§ ${section}` : '';
              return (
                <div key={tool.id} className={`tool-chip tool-state-${tool.state}`}>
                  <div className="tool-chip-header">
                    <span className="tool-name">{getToolLabel(tool.toolName)}</span>
                    {target ? <span className="tool-target" title={target}>{target}</span> : null}
                    <span className="tool-chip-status">
                      {tool.state === 'running' ? 'Running' : tool.summary || 'Done'}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
};
