import React from 'react';
import katex from 'katex';

export interface MarkdownRendererProps {
  content: string;
  onCitationClick?: (citationId: string) => void;
  activeCitationId?: string | null;
  className?: string;
  citationLabels?: Record<string, number>;
}

/**
 * Clean any accidental internal artifacts (raw JSON, system tags, reasoning tags)
 * so only human-facing response text is rendered.
 */
export function cleanMarkdownContent(raw: string): string {
  if (!raw) return '';
  let text = raw.trim();

  // 1. Strip internal reasoning, thinking, or tool_call tags first
  text = text.replace(/<reasoning>[\s\S]*?<\/reasoning>/gi, '');
  text = text.replace(/<thought>[\s\S]*?<\/thought>/gi, '');
  text = text.replace(/<tool_call>[\s\S]*?<\/tool_call>/gi, '');
  text = text.replace(/<function_call>[\s\S]*?<\/function_call>/gi, '');
  text = text.trim();

  // 2. If text contains a json code fence wrapping answer_blocks or response json, unwrap it
  const jsonFenceMatch = text.match(/```(?:json)?\s*(\{[\s\S]*?\})\s*```/);
  if (jsonFenceMatch) {
    try {
      const parsed = JSON.parse(jsonFenceMatch[1]);
      if (Array.isArray(parsed.answer_blocks)) {
        const extracted = parsed.answer_blocks.map((b: any) => b.text || '').join('\n\n');
        text = text.replace(jsonFenceMatch[0], extracted).trim();
      } else if (parsed.text) {
        text = text.replace(jsonFenceMatch[0], parsed.text).trim();
      }
    } catch {
      // Not valid JSON
    }
  }

  // 3. If the entire text is a raw JSON blob (e.g. {"answer_blocks": ...}), extract text
  if (text.startsWith('{') && text.endsWith('}')) {
    try {
      const parsed = JSON.parse(text);
      if (Array.isArray(parsed.answer_blocks)) {
        text = parsed.answer_blocks.map((b: any) => b.text || '').join('\n\n');
      } else if (parsed.text) {
        text = parsed.text;
      }
    } catch {
      // Continue
    }
  }

  // 4. Also check if there's any stray {"answer_blocks": ...} anywhere in the text
  const rawBlocksMatch = text.match(/\{[\s\S]*?"answer_blocks"\s*:\s*(\[[\s\S]*?\])[\s\S]*?\}/);
  if (rawBlocksMatch) {
    try {
      const blocks = JSON.parse(rawBlocksMatch[1]);
      if (Array.isArray(blocks)) {
        const extracted = blocks.map((b: any) => b.text || '').join('\n\n');
        text = text.replace(rawBlocksMatch[0], extracted).trim();
      }
    } catch {
      // Continue
    }
  }

  return text.trim();
}

function renderMath(source: string, displayMode: boolean, key: string) {
  return <span key={key} className={displayMode ? 'md-math-display' : 'md-math-inline'}
    dangerouslySetInnerHTML={{__html: katex.renderToString(source, {displayMode, throwOnError: false,
      trust: false, strict: 'ignore', maxExpand: 1000, maxSize: 12, output: 'htmlAndMathml'})}} />;
}

/**
 * Parse and render inline elements: Bold, Italic, Code, Math, Citations.
 */
function renderInline(
  text: string,
  onCitationClick?: (id: string) => void,
  activeCitationId?: string | null,
  citationLabels: Record<string, number> = {}
): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let remaining = text;
  let keyIndex = 0;

  // Pattern matching inline tokens:
  // 1. Inline code: `code`
  // 2. Math inline: $math$
  // 3. Bold-Italic: ***text***
  // 4. Bold: **text** or __text__
  // 5. Italic: *text* or _text_
  // 6. Strikethrough: ~~text~~
  // 7. Citation: [p1], [S1.p2], [C1], [1], [2], etc.
  const inlineRegex = /(`[^`]+`|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]|\$\$[\s\S]*?\$\$|\$[^$]+\$|\*\*\*[^*]+\*\*\*|\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*|(?<![\p{L}\p{N}])_[^_]+_(?![\p{L}\p{N}])|~~[^~]+~~|\[[^\]]+\]\(https?:\/\/[^\s)]+\)|https?:\/\/[^\s<]+[^<.,:;"')\]\s]|\[(?:p\d+|[A-Za-z0-9_.-]+)\])/u;

  while (remaining.length > 0) {
    const match = remaining.match(inlineRegex);
    if (!match || match.index === undefined) {
      nodes.push(remaining);
      break;
    }

    const matchIndex = match.index;
    if (matchIndex > 0) {
      nodes.push(remaining.slice(0, matchIndex));
    }

    const token = match[0];
    const key = `inline_${keyIndex++}`;

    if (token.startsWith('`') && token.endsWith('`')) {
      // Inline code
      nodes.push(
        <code key={key} className="md-inline-code">
          {token.slice(1, -1)}
        </code>
      );
    } else if (token.startsWith('$') || token.startsWith('\\(') || token.startsWith('\\[')) {
      const display = token.startsWith('$$') || token.startsWith('\\[');
      const delimiter = token.startsWith('\\') || token.startsWith('$$') ? 2 : 1;
      nodes.push(renderMath(token.slice(delimiter, -delimiter), display, key));
    } else if (token.startsWith('***') && token.endsWith('***')) {
      // Bold Italic
      nodes.push(
        <strong key={key}>
          <em>{renderInline(token.slice(3, -3), onCitationClick, activeCitationId, citationLabels)}</em>
        </strong>
      );
    } else if (
      (token.startsWith('**') && token.endsWith('**')) ||
      (token.startsWith('__') && token.endsWith('__'))
    ) {
      // Bold
      nodes.push(
        <strong key={key}>
          {renderInline(token.slice(2, -2), onCitationClick, activeCitationId, citationLabels)}
        </strong>
      );
    } else if (
      (token.startsWith('*') && token.endsWith('*')) ||
      (token.startsWith('_') && token.endsWith('_'))
    ) {
      // Italic
      nodes.push(
        <em key={key}>
          {renderInline(token.slice(1, -1), onCitationClick, activeCitationId, citationLabels)}
        </em>
      );
    } else if (token.startsWith('~~') && token.endsWith('~~')) {
      // Strikethrough
      nodes.push(
        <del key={key}>
          {renderInline(token.slice(2, -2), onCitationClick, activeCitationId, citationLabels)}
        </del>
      );
    } else if (token.startsWith('[') && token.includes('](') && token.endsWith(')')) {
      const linkMatch = token.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/);
      if (linkMatch) {
        const linkText = linkMatch[1];
        const url = linkMatch[2];
        nodes.push(
          <a
            key={key}
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="external-paper-link"
            title={`Open: ${linkText}`}
          >
            {linkText}
          </a>
        );
      } else {
        nodes.push(token);
      }
    } else if (token.startsWith('http://') || token.startsWith('https://')) {
      nodes.push(
        <a
          key={key}
          href={token}
          target="_blank"
          rel="noopener noreferrer"
          className="external-paper-link"
          title={`Open: ${token}`}
        >
          {token}
        </a>
      );
    } else if (token.startsWith('[') && token.endsWith(']')) {
      // Citation note: e.g. [p1], [S1.p2], [1], [C1]
      const citationId = token.slice(1, -1);
      if (!(citationId in citationLabels)) {
        nodes.push(token);
        remaining = remaining.slice(matchIndex + token.length);
        continue;
      }
      const isActive = activeCitationId === citationId;
      if (onCitationClick) {
        nodes.push(
          <button
            key={key}
            type="button"
            className={`citation-link ${isActive ? 'active' : ''}`}
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onCitationClick(citationId);
            }}
            aria-expanded={isActive}
            aria-label={`View citation for evidence ${citationId}`}
          >
            {citationLabels[citationId] ?? citationId}
          </button>
        );
      } else {
        nodes.push(
          <span key={key} className="citation-link">
            {citationLabels[citationId] ?? citationId}
          </span>
        );
      }
    } else {
      nodes.push(token);
    }

    remaining = remaining.slice(matchIndex + token.length);
  }

  return nodes;
}

/**
 * Modern Markdown Renderer that renders web-standard formatted text,
 * headers, lists, code blocks, tables, and clickable citation notes.
 */
export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({
  content,
  onCitationClick,
  activeCitationId,
  className = '',
  citationLabels = {},
}) => {
  const cleaned = cleanMarkdownContent(content);
  if (!cleaned) return null;

  // Split into lines for block-level parsing
  const lines = cleaned.split('\n');
  const elements: React.ReactNode[] = [];
  let blockKey = 0;

  let inCodeBlock = false;
  let codeBlockLang = '';
  let codeBlockLines: string[] = [];

  let inList: 'ul' | 'ol' | null = null;
  let listItems: React.ReactNode[] = [];

  let tableLines: string[] = [];

  const flushList = () => {
    if (inList && listItems.length > 0) {
      const Tag = inList;
      elements.push(
        <Tag key={`list_${blockKey++}`} className={`md-list md-${inList}`}>
          {listItems.map((item, idx) => (
            <li key={idx} className="md-list-item">
              {item}
            </li>
          ))}
        </Tag>
      );
      inList = null;
      listItems = [];
    }
  };

  const flushTable = () => {
    if (tableLines.length >= 2) {
      const headerLine = tableLines[0];
      const bodyLines = tableLines.slice(2); // Skip separator line |---|---|

      const parseCells = (row: string) =>
        row
          .trim()
          .replace(/^\|/, '')
          .replace(/\|$/, '')
          .split('|')
          .map((c) => c.trim());

      const headers = parseCells(headerLine);
      const rows = bodyLines.map(parseCells);

      elements.push(
        <div key={`table_${blockKey++}`} className="md-table-wrapper">
          <table className="md-table">
            <thead>
              <tr>
                {headers.map((h, i) => (
                  <th key={i}>{renderInline(h, onCitationClick, activeCitationId, citationLabels)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, rIdx) => (
                <tr key={rIdx}>
                  {r.map((cell, cIdx) => (
                    <td key={cIdx}>{renderInline(cell, onCitationClick, activeCitationId, citationLabels)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    tableLines = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // 1. Fenced Code Block Handler (```lang ... ```)
    if (trimmed.startsWith('```')) {
      if (!inCodeBlock) {
        flushList();
        flushTable();
        inCodeBlock = true;
        codeBlockLang = trimmed.slice(3).trim();
        codeBlockLines = [];
      } else {
        inCodeBlock = false;
        const codeText = codeBlockLines.join('\n');
        elements.push(
          <div key={`code_${blockKey++}`} className="md-code-block-container">
            {codeBlockLang ? (
              <div className="md-code-header">
                <span className="md-code-lang">{codeBlockLang}</span>
              </div>
            ) : null}
            <pre className="md-code-pre">
              <code>{codeText}</code>
            </pre>
          </div>
        );
        codeBlockLines = [];
        codeBlockLang = '';
      }
      continue;
    }

    if (inCodeBlock) {
      codeBlockLines.push(line);
      continue;
    }

    // Display math is consumed as a unit before Markdown can interpret _ or |.
    if (trimmed.startsWith('$$') || trimmed.startsWith('\\[')) {
      flushList(); flushTable();
      const open = trimmed.startsWith('$$') ? '$$' : '\\[';
      const close = open === '$$' ? '$$' : '\\]';
      let source = trimmed.slice(2);
      while (!source.includes(close) && i + 1 < lines.length) source += '\n' + lines[++i];
      const end = source.indexOf(close);
      elements.push(renderMath(end >= 0 ? source.slice(0, end) : source, true, `math_${blockKey++}`));
      if (end >= 0 && source.slice(end + close.length).trim()) elements.push(<p key={`after_math_${blockKey++}`}>{renderInline(source.slice(end + close.length).trim(), onCitationClick, activeCitationId, citationLabels)}</p>);
      continue;
    }

    // 2. Table row detection (| Cell | Cell |)
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      flushList();
      tableLines.push(trimmed);
      continue;
    } else if (tableLines.length > 0) {
      flushTable();
    }

    // 3. Blank line
    if (!trimmed) {
      flushList();
      flushTable();
      continue;
    }

    // 4. Headings (#, ##, ###, ####)
    if (trimmed.startsWith('#')) {
      flushList();
      flushTable();
      const match = trimmed.match(/^(#{1,6})\s+(.*)$/);
      if (match) {
        const level = match[1].length;
        const headingText = match[2];
        const inlineContent = renderInline(headingText, onCitationClick, activeCitationId, citationLabels);

        if (level === 1) {
          elements.push(
            <h3 key={`h_${blockKey++}`} className="md-heading md-h1">
              {inlineContent}
            </h3>
          );
        } else if (level === 2) {
          elements.push(
            <h4 key={`h_${blockKey++}`} className="md-heading md-h2">
              {inlineContent}
            </h4>
          );
        } else if (level === 3) {
          elements.push(
            <h5 key={`h_${blockKey++}`} className="md-heading md-h3">
              {inlineContent}
            </h5>
          );
        } else {
          elements.push(
            <h6 key={`h_${blockKey++}`} className="md-heading md-h4">
              {inlineContent}
            </h6>
          );
        }
        continue;
      }
    }

    // 5. Blockquote (> quote)
    if (trimmed.startsWith('>')) {
      flushList();
      flushTable();
      const quoteText = trimmed.replace(/^>\s*/, '');
      elements.push(
        <blockquote key={`quote_${blockKey++}`} className="md-blockquote">
          {renderInline(quoteText, onCitationClick, activeCitationId, citationLabels)}
        </blockquote>
      );
      continue;
    }

    // 6. Horizontal Rule (---, ***, ___)
    if (/^(\*\*\*|---|___)$/.test(trimmed)) {
      flushList();
      flushTable();
      elements.push(<hr key={`hr_${blockKey++}`} className="md-hr" />);
      continue;
    }

    // 7. Unordered List Items (- Item, * Item, + Item)
    const ulMatch = trimmed.match(/^[-*+]\s+(.*)$/);
    if (ulMatch) {
      if (inList !== 'ul') {
        flushList();
        inList = 'ul';
      }
      listItems.push(renderInline(ulMatch[1], onCitationClick, activeCitationId, citationLabels));
      continue;
    }

    // 8. Ordered List Items (1. Item, 2. Item)
    const olMatch = trimmed.match(/^\d+\.\s+(.*)$/);
    if (olMatch) {
      if (inList !== 'ol') {
        flushList();
        inList = 'ol';
      }
      listItems.push(renderInline(olMatch[1], onCitationClick, activeCitationId, citationLabels));
      continue;
    }

    // 9. Standard Paragraph
    flushList();
    flushTable();
    elements.push(
      <p key={`p_${blockKey++}`} className="md-paragraph">
        {renderInline(trimmed, onCitationClick, activeCitationId, citationLabels)}
      </p>
    );
  }

  flushList();
  flushTable();

  if (inCodeBlock && codeBlockLines.length > 0) {
    elements.push(
      <pre key={`code_unf_${blockKey++}`} className="md-code-pre">
        <code>{codeBlockLines.join('\n')}</code>
      </pre>
    );
  }

  return <div className={`md-formatted-content ${className}`}>{elements}</div>;
};
