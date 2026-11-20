/**
 * Read source metadata and paragraphs from the arXiv DOM.
 *
 * Identify HTML, abstract, and unsupported pages. For an abstract page, read
 * the HTML link present on the page. Report when the version cannot be
 * determined.
 *
 * During Analyze, extract the title, canonical URL, version, section tree,
 * and paragraphs in document order. Attach the parser version and locators
 * using the fingerprint rules shared with navigation.ts.
 */

import {
  PageType,
  PageContext,
  ParsedPaper,
  SectionNode,
  ExtractedParagraph,
} from '../messages';

export const PARSER_VERSION = '1.2.0';

function escapeCssIdentifier(id: string): string {
  if (typeof CSS !== 'undefined' && typeof CSS.escape === 'function') {
    return CSS.escape(id);
  }
  return id.replace(/([ #;?%&,.+*~':"!^$[\]()=>|/@])/g, '\\$1');
}

export function sourceSelector(el: HTMLElement): string {
  const parts: string[] = [];
  let node: HTMLElement | null = el;
  while (node) {
    if (node.id) { parts.unshift(`#${escapeCssIdentifier(node.id)}`); break; }
    const tag = node.tagName.toLowerCase();
    const siblings = node.parentElement ? Array.from(node.parentElement.children).filter(child => child.tagName === node!.tagName) : [node];
    parts.unshift(`${tag}:nth-of-type(${siblings.indexOf(node) + 1})`);
    node = node.parentElement;
  }
  return parts.join(' > ');
}

export function extractSourceText(el: HTMLElement): string {
  const copy = el.cloneNode(true) as HTMLElement;
  copy.querySelectorAll('math, .ltx_Math').forEach(math => {
    const tex = math.getAttribute('alttext') || math.querySelector('annotation[encoding="application/x-tex"]')?.textContent;
    if (tex) math.replaceWith(document.createTextNode(` $${tex}$ `));
  });
  copy.querySelectorAll('annotation').forEach(node => node.remove());
  return normalizeParagraphText(copy.textContent || '');
}

export function normalizeParagraphText(text: string): string {
  return text
    .replace(/\s+/g, ' ')
    .trim();
}

export async function computeParagraphFingerprint(text: string): Promise<string> {
  const normalized = normalizeParagraphText(text);
  const encoder = new TextEncoder();
  const data = encoder.encode(normalized);

  if (typeof crypto !== 'undefined' && crypto.subtle) {
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
  }

  // Deterministic fallback hash for environments without SubtleCrypto
  let hash = 0x811c9dc5;
  for (let i = 0; i < data.length; i++) {
    hash ^= data[i];
    hash = Math.imul(hash, 0x01000193);
  }
  return ('00000000' + (hash >>> 0).toString(16)).slice(-8);
}

export function detectPageContext(url: string, doc: Document): PageContext {
  const parsedUrl = new URL(url);
  const pathname = parsedUrl.pathname;

  // Check for HTML paper: /html/<arxiv_id>(v<version>)?
  const htmlMatch = pathname.match(/^\/html\/([0-9]{4}\.[0-9]{4,5})(v[0-9]+)?/);
  if (htmlMatch) {
    const arxivId = htmlMatch[1];
    const version = htmlMatch[2] ? htmlMatch[2] : 'unknown';
    return {
      pageType: PageType.HTML,
      arxivId,
      version,
      canonicalUrl: `https://arxiv.org/html/${arxivId}${version !== 'unknown' ? version : ''}`,
      isSupported: true,
      htmlUrl: null,
    };
  }

  // Check for Abstract page: /abs/<arxiv_id>(v<version>)?
  const absMatch = pathname.match(/^\/abs\/([0-9]{4}\.[0-9]{4,5})(v[0-9]+)?/);
  if (absMatch) {
    const arxivId = absMatch[1];
    const version = absMatch[2] ? absMatch[2] : 'unknown';

    // Look for HTML link in document
    let htmlUrl: string | null = null;
    const htmlAnchor = doc.querySelector<HTMLAnchorElement>('a[href*="/html/"]');
    if (htmlAnchor && htmlAnchor.getAttribute('href')) {
      const rawHref = htmlAnchor.getAttribute('href')!;
      htmlUrl = new URL(rawHref, url).toString();
    }

    return {
      pageType: PageType.ABSTRACT,
      arxivId,
      version,
      canonicalUrl: `https://arxiv.org/abs/${arxivId}${version !== 'unknown' ? version : ''}`,
      isSupported: htmlUrl !== null,
      htmlUrl,
    };
  }

  return {
    pageType: PageType.UNSUPPORTED,
    arxivId: null,
    version: null,
    canonicalUrl: url,
    isSupported: false,
    htmlUrl: null,
  };
}

export async function parseArxivDocument(doc: Document, url: string): Promise<ParsedPaper> {
  const context = detectPageContext(url, doc);
  if (context.pageType !== PageType.HTML || !context.arxivId) {
    throw new Error('Document is not a supported arXiv HTML page');
  }

  // Extract paper title (prefer explicit h1 document title over head title)
  const titleEl =
    doc.querySelector('h1.ltx_title') ||
    doc.querySelector('.ltx_title_document') ||
    doc.querySelector('h1') ||
    doc.querySelector('title');
  const rawTitle = titleEl ? titleEl.textContent || '' : '';
  const title = rawTitle
    .replace(/^Title:\s*/i, '')
    .replace(/\s*\(arXiv:[^)]+\)/i, '')
    .trim() || 'Untitled Paper';

  const article = doc.querySelector<HTMLElement>('article.ltx_document, .ltx_document') || doc.body;

  // Extract sections
  const sections: SectionNode[] = [];
  const sectionElements = Array.from(article.querySelectorAll<HTMLElement>('.ltx_abstract, .ltx_section, .ltx_subsection, .ltx_subsubsection, .ltx_appendix, section[id]'));

  if (sectionElements.length === 0) {
    // If no explicit section elements, create a root section
    sections.push({
      id: 'sec-root',
      heading: 'Document Body',
      path: 'Document Body',
      order: 0,
    });
  } else {
    sectionElements.forEach((secEl, index) => {
      const id = secEl.id || `sec-${index}`;
      const headingEl = secEl.querySelector('.ltx_title, h2, h3, h4');
      const heading = secEl.classList.contains('ltx_abstract') ? 'Abstract' : (headingEl ? headingEl.textContent?.trim() || `Section ${index + 1}` : `Section ${index + 1}`);
      sections.push({
        id,
        heading,
        path: heading,
        order: index,
        sectionType: secEl.classList.contains('ltx_appendix') ? 'appendix' : 'section',
      });
    });
  }

  // Extract paragraphs
  const paragraphs: ExtractedParagraph[] = [];
  const paraElements = Array.from(
    article.querySelectorAll<HTMLElement>('.ltx_para, .ltx_p, p, .ltx_equation, .ltx_equationgroup, figure.ltx_figure, figure.ltx_table')
  );

  let pOrder = 0;
  for (const el of paraElements) {
    // Ignore elements inside headers, footers, navigation, or abstracts metadata
    if (el.closest('.ltx_header, .ltx_footer, header, footer, nav, .ltx_page_footer, .ltx_dates, .ltx_bibliography, .ltx_note, [role=dialog]')) {
      continue;
    }

    // If this element contains child paragraph elements, skip it to avoid duplicates
    if (!el.matches('.ltx_equation, .ltx_equationgroup, figure') && el.querySelector('.ltx_p, p, .ltx_equationgroup, .ltx_equation, figure') ||
        el.parentElement?.closest('figure, .ltx_equationgroup, .ltx_equation')) {
      continue;
    }

    const rawText = el.textContent || '';
    const text = extractSourceText(el);
    if (!text || text.length < 15) {
      // Skip trivial boilerplate / empty blocks
      continue;
    }

    // Determine parent section
    const parentSec = el.closest<HTMLElement>('.ltx_abstract, .ltx_section, .ltx_subsection, .ltx_subsubsection, .ltx_appendix, section[id]');
    const sectionId = parentSec?.id || (sections[0]?.id || 'sec-root');
    const matchingSection = sections.find((s) => s.id === sectionId);
    const sectionPath = matchingSection ? matchingSection.path : 'Document Body';

    const paraContainer = el.closest<HTMLElement>('.ltx_para');
    const children = paraContainer ? Array.from(paraContainer.querySelectorAll('.ltx_p, p')).filter(child => !child.querySelector('.ltx_p, p')) : [];
    const id = el.id || (paraContainer?.id ? `${paraContainer.id}${children.length > 1 ? `.${children.indexOf(el) + 1}` : ''}` : `${sectionId}.p${pOrder + 1}`);
    const targetElement = el;
    const fingerprint = await computeParagraphFingerprint(rawText);

    const hasMath = !!el.querySelector('.ltx_Math, math');
    const hasTable = !!el.querySelector('table, .ltx_tabular');

    paragraphs.push({
      id,
      sectionId,
      sectionPath,
      order: pOrder++,
      text,
      fingerprint,
      locator: {
        elementId: targetElement.id || undefined,
        selector: sourceSelector(targetElement),
      },
      hasMath,
      hasTable,
    });
  }

  return {
    title,
    arxivId: context.arxivId,
    version: context.version || 'unknown',
    canonicalUrl: context.canonicalUrl,
    parserVersion: PARSER_VERSION,
    sections,
    paragraphs,
  };
}
