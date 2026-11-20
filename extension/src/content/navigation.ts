/**
 * Verify the source paragraph and scroll to the citation.
 *
 * Define the text-normalization and fingerprinting rules shared by parsing
 * and Jump. Verify the document and version, then check the fingerprint when
 * resolving an element ID or a selector produced by the parser.
 *
 * Highlight only a verified paragraph. When the location is stale or
 * ambiguous, return a verified section link if available.
 */

import {
  JumpTarget,
  JumpResult,
  JumpStatus,
} from '../messages';
import {
  normalizeParagraphText,
  computeParagraphFingerprint,
  detectPageContext,
} from './parser';

export { normalizeParagraphText, computeParagraphFingerprint };

export const HIGHLIGHT_CLASS = 'paperlens-highlight';

export async function verifyParagraphTarget(
  doc: Document,
  target: JumpTarget
): Promise<{ verified: boolean; element?: HTMLElement }> {
  // If active document has an arXiv URL, verify that arxivId matches target
  if (doc.location?.href && target.arxivId) {
    try {
      const url = doc.location.href;
      if (url.includes('/html/') || url.includes('/abs/')) {
        const ctx = detectPageContext(url, doc);
        if (ctx.arxivId && (ctx.arxivId !== target.arxivId || target.version !== 'unknown' && ctx.version !== 'unknown' && ctx.version !== target.version)) {
          return { verified: false };
        }
      }
    } catch {
      // Ignore URL parsing errors
    }
  }

  let el: HTMLElement | null = null;

  if (target.elementId) {
    el = doc.getElementById(target.elementId);
  }
  if (!el && target.selector) {
    try {
      el = doc.querySelector<HTMLElement>(target.selector);
    } catch {
      // Invalid selector fallback
      el = null;
    }
  }

  if (!el) {
    return { verified: false };
  }

  const currentText = el.textContent || '';
  const currentFingerprint = await computeParagraphFingerprint(currentText);

  if (currentFingerprint === target.fingerprint) {
    return { verified: true, element: el };
  }

  // Older cached citations used a wrapper ID but fingerprinted its leaf paragraph.
  // Recover only an exact fingerprint match, never an approximate text guess.
  const leaves = Array.from(el.querySelectorAll<HTMLElement>('.ltx_p, p')).filter(node => !node.querySelector('.ltx_p, p'));
  for (const leaf of leaves.slice(0, 80)) {
    if (await computeParagraphFingerprint(leaf.textContent || '') === target.fingerprint) {
      return { verified: true, element: leaf };
    }
  }

  return { verified: false, element: el };
}

export async function jumpToParagraph(
  doc: Document,
  target: JumpTarget
): Promise<JumpResult> {
  if (doc.location?.href && target.arxivId) {
    try {
      const url = doc.location.href;
      if (url.includes('/html/') || url.includes('/abs/')) {
        const ctx = detectPageContext(url, doc);
        if (ctx.arxivId && (ctx.arxivId !== target.arxivId || target.version !== 'unknown' && ctx.version !== 'unknown' && ctx.version !== target.version)) {
          return {
            status: JumpStatus.UNAVAILABLE,
            message: 'Active document arXiv ID does not match citation target.',
          };
        }
      }
    } catch {
      // Ignore
    }
  }

  const { verified, element } = await verifyParagraphTarget(doc, target);

  if (!doc.getElementById('paperlens-source-highlight-style')) {
    const style = doc.createElement('style');
    style.id = 'paperlens-source-highlight-style';
    style.textContent = '.paperlens-highlight{background:#fef3c7!important;color:#0f172a!important;outline:2px solid #d97706!important;outline-offset:5px;scroll-margin-top:80px;border-radius:3px;}';
    doc.head.appendChild(style);
  }

  // Clear existing highlights across document
  const existing = doc.querySelectorAll(`.${HIGHLIGHT_CLASS}`);
  existing.forEach((node) => node.classList.remove(HIGHLIGHT_CLASS));

  if (verified && element) {
    element.classList.add(HIGHLIGHT_CLASS);
    if (typeof element.scrollIntoView === 'function') {
      element.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    return { status: JumpStatus.VERIFIED };
  }

  // Fallback to verified section anchor if paragraph is missing or modified
  if (target.sectionId) {
    const secEl = doc.getElementById(target.sectionId);
    if (secEl) {
      if (typeof secEl.scrollIntoView === 'function') {
        secEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
      return {
        status: JumpStatus.SECTION_FALLBACK,
        fallbackSectionId: target.sectionId,
        message: 'Paragraph location changed; navigated to enclosing section header.',
      };
    }
  }

  return {
    status: JumpStatus.UNAVAILABLE,
    message: 'Source paragraph and enclosing section could not be verified in the active document.',
  };
}
