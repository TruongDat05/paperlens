/**
 * @vitest-environment jsdom
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  detectPageContext,
  parseArxivDocument,
  normalizeParagraphText,
  computeParagraphFingerprint,
} from '../src/content/parser';
import {
  jumpToParagraph,
  verifyParagraphTarget,
} from '../src/content/navigation';
import {
  PageType,
  JumpStatus,
} from '../src/messages';

describe('arXiv DOM Parser and Navigation', () => {
  describe('Page Context Detection', () => {
    it('detects supported HTML page with version', () => {
      const url = 'https://arxiv.org/html/2401.12345v2';
      const context = detectPageContext(url, document);
      expect(context.pageType).toBe(PageType.HTML);
      expect(context.arxivId).toBe('2401.12345');
      expect(context.version).toBe('v2');
      expect(context.isSupported).toBe(true);
    });

    it('detects unversioned HTML page with unknown version state', () => {
      const url = 'https://arxiv.org/html/2401.12345';
      const context = detectPageContext(url, document);
      expect(context.pageType).toBe(PageType.HTML);
      expect(context.arxivId).toBe('2401.12345');
      expect(context.version).toBe('unknown');
    });

    it('detects abstract page and extracts HTML link when present', () => {
      document.body.innerHTML = `
        <div class="extra-services">
          <a class="abs-button" href="/html/2401.12345v1">HTML (experimental)</a>
        </div>
      `;
      const url = 'https://arxiv.org/abs/2401.12345v1';
      const context = detectPageContext(url, document);
      expect(context.pageType).toBe(PageType.ABSTRACT);
      expect(context.arxivId).toBe('2401.12345');
      expect(context.htmlUrl).toBe('https://arxiv.org/html/2401.12345v1');
    });

    it('detects abstract page with missing HTML link', () => {
      document.body.innerHTML = `
        <div class="extra-services">
          <a class="abs-button" href="/pdf/2401.12345.pdf">Download PDF</a>
        </div>
      `;
      const url = 'https://arxiv.org/abs/2401.12345v1';
      const context = detectPageContext(url, document);
      expect(context.pageType).toBe(PageType.ABSTRACT);
      expect(context.htmlUrl).toBeNull();
      expect(context.isSupported).toBe(false);
    });
  });

  describe('Document Parsing', () => {
    beforeEach(() => {
      document.body.innerHTML = `
        <header class="ltx_header">Nav Header</header>
        <article class="ltx_document">
          <h1 class="ltx_title ltx_title_document">Attention Is All You Need</h1>
          <section id="S1" class="ltx_section">
            <h2 class="ltx_title ltx_title_section">1 Introduction</h2>
            <div id="S1.p1" class="ltx_para">
              <p class="ltx_p">Recurrent neural networks have been firmly established as state of the art.</p>
            </div>
            <div id="S1.p2" class="ltx_para">
              <p class="ltx_p">In this work we propose the Transformer, a model architecture eschewing recurrence.</p>
            </div>
          </section>
          <section id="S2" class="ltx_section">
            <h2 class="ltx_title ltx_title_section">2 Background</h2>
            <div id="S2.p1" class="ltx_para">
              <p class="ltx_p">The goal of reducing sequential computation also forms the foundation of the Extended Neural GPU.</p>
            </div>
          </section>
        </article>
        <footer class="ltx_footer">Footer boilerplate</footer>
      `;
    });

    it('extracts title, sections, and paragraphs in document order', async () => {
      const url = 'https://arxiv.org/html/2401.12345v1';
      const parsed = await parseArxivDocument(document, url);

      expect(parsed.title).toBe('Attention Is All You Need');
      expect(parsed.arxivId).toBe('2401.12345');
      expect(parsed.version).toBe('v1');
      expect(parsed.sections).toHaveLength(2);
      expect(parsed.sections[0].heading).toBe('1 Introduction');
      expect(parsed.sections[0].id).toBe('S1');

      expect(parsed.paragraphs).toHaveLength(3);
      expect(parsed.paragraphs[0].id).toBe('S1.p1');
      expect(parsed.paragraphs[0].sectionId).toBe('S1');
      expect(parsed.paragraphs[0].text).toContain('Recurrent neural networks');
      expect(parsed.paragraphs[0].fingerprint).toBeDefined();
    });

    it('computes deterministic fingerprints across whitespace variations', async () => {
      const t1 = '  Recurrent  neural networks\n have been firmly established.  ';
      const t2 = 'Recurrent neural networks have been firmly established.';
      expect(normalizeParagraphText(t1)).toBe(normalizeParagraphText(t2));
      const fp1 = await computeParagraphFingerprint(t1);
      const fp2 = await computeParagraphFingerprint(t2);
      expect(fp1).toBe(fp2);
    });

    it('parses realistic multi-section HTML fixture correctly', async () => {
      const fs = await import('node:fs');
      const path = await import('node:path');
      const fixtureHtml = fs.readFileSync(
        path.resolve(__dirname, 'fixtures/sample_arxiv_paper.html'),
        'utf-8'
      );
      document.body.innerHTML = fixtureHtml;
      const url = 'https://arxiv.org/html/1706.03762v7';
      const parsed = await parseArxivDocument(document, url);

      expect(parsed.title).toBe('Attention Is All You Need');
      expect(parsed.arxivId).toBe('1706.03762');
      expect(parsed.version).toBe('v7');
      expect(parsed.sections).toHaveLength(4);
      expect(parsed.sections[3].sectionType).toBe('appendix');
      expect(parsed.paragraphs.length).toBeGreaterThanOrEqual(5);
    });
  });

  describe('Jump and Navigation Verification', () => {
    beforeEach(() => {
      document.body.innerHTML = `
        <article class="ltx_document">
          <section id="S1" class="ltx_section">
            <h2 class="ltx_title ltx_title_section">1 Introduction</h2>
            <div id="S1.p1" class="ltx_para">
              <p class="ltx_p">Paragraph one original text.</p>
            </div>
          </section>
        </article>
      `;
    });

    it('verifies and highlights target when element and fingerprint match', async () => {
      const p1Elem = document.getElementById('S1.p1')!;
      const originalText = 'Paragraph one original text.';
      const fingerprint = await computeParagraphFingerprint(originalText);

      const target = {
        elementId: 'S1.p1',
        sectionId: 'S1',
        fingerprint,
        arxivId: '2401.12345',
        version: 'v1',
      };

      const result = await jumpToParagraph(document, target);
      expect(result.status).toBe(JumpStatus.VERIFIED);
      expect(p1Elem.classList.contains('paperlens-highlight')).toBe(true);
    });

    it('falls back to section anchor when paragraph content changed/mismatched', async () => {
      const target = {
        elementId: 'S1.p1',
        sectionId: 'S1',
        fingerprint: 'non-matching-fingerprint-hash',
        arxivId: '2401.12345',
        version: 'v1',
      };

      const result = await jumpToParagraph(document, target);
      expect(result.status).toBe(JumpStatus.SECTION_FALLBACK);
      expect(result.fallbackSectionId).toBe('S1');
      const p1Elem = document.getElementById('S1.p1')!;
      // Must NOT apply wrong highlight
      expect(p1Elem.classList.contains('paperlens-highlight')).toBe(false);
    });

    it('returns UNAVAILABLE when both paragraph and section cannot be verified', async () => {
      const target = {
        elementId: 'missing-p',
        sectionId: 'missing-s',
        fingerprint: 'some-fingerprint',
        arxivId: '2401.12345',
        version: 'v1',
      };

      const result = await jumpToParagraph(document, target);
      expect(result.status).toBe(JumpStatus.UNAVAILABLE);
    });

    it('returns UNAVAILABLE when jump target arxivId mismatches active document URL', async () => {
      window.history.pushState({}, '', '/html/2401.99999v1');

      const p1Elem = document.getElementById('S1.p1')!;
      const originalText = 'Paragraph one original text.';
      const fingerprint = await computeParagraphFingerprint(originalText);

      const target = {
        elementId: 'S1.p1',
        sectionId: 'S1',
        fingerprint,
        arxivId: '2401.12345', // different arxivId
        version: 'v1',
      };

      const result = await jumpToParagraph(document, target);
      expect(result.status).toBe(JumpStatus.UNAVAILABLE);
      expect(p1Elem.classList.contains('paperlens-highlight')).toBe(false);
    });
  });
});

it('excludes arXiv footer text and preserves abstract context', async () => {
  document.body.innerHTML = `<article class="ltx_document">
    <h1 class="ltx_title_document">T-RAG</h1>
    <div id="abstract1" class="ltx_abstract"><h6>Abstract</h6><p>We introduce a hierarchical table retrieval framework.</p></div>
    <section id="S1" class="ltx_section"><h2>Introduction</h2><p>This paper studies retrieval over many tables.</p></section>
  </article><footer class="arxiv-html-footer"><p>Our team has already identified the following issues.</p></footer>`;
  const paper = await parseArxivDocument(document, 'https://arxiv.org/html/2504.01346v4');
  expect(paper.paragraphs.some(p => p.text.includes('Our team'))).toBe(false);
  const abstract = paper.paragraphs.find(p => p.text.includes('hierarchical'))!;
  expect(abstract.sectionPath).toBe('Abstract');
});
