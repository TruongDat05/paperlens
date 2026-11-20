/**
 * Define messages between the side panel and the content script.
 *
 * Describe requests for page context, Analyze, and Jump, along with their
 * response types. Include the document identity and arXiv ID and version so
 * the recipient can verify the page.
 */

export enum PageType {
  HTML = 'html',
  ABSTRACT = 'abstract',
  UNSUPPORTED = 'unsupported',
}

export enum JumpStatus {
  VERIFIED = 'verified',
  SECTION_FALLBACK = 'section_fallback',
  UNAVAILABLE = 'unavailable',
}

export interface PageContext {
  pageType: PageType;
  arxivId: string | null;
  version: string | null;
  canonicalUrl: string;
  isSupported: boolean;
  htmlUrl: string | null;
}

export interface SectionNode {
  id: string;
  heading: string;
  path: string;
  order: number;
  sectionType?: string;
}

export interface ExtractedParagraph {
  id: string;
  sectionId: string;
  sectionPath: string;
  order: number;
  text: string;
  fingerprint: string;
  locator: {
    elementId?: string;
    selector?: string;
  };
  hasMath?: boolean;
  hasTable?: boolean;
}

export interface ParsedPaper {
  title: string;
  arxivId: string;
  version: string;
  canonicalUrl: string;
  parserVersion: string;
  sections: SectionNode[];
  paragraphs: ExtractedParagraph[];
}

export interface JumpTarget {
  elementId?: string;
  selector?: string;
  sectionId?: string;
  fingerprint: string;
  arxivId: string;
  version: string;
}

export interface JumpResult {
  status: JumpStatus;
  fallbackSectionId?: string;
  message?: string;
}

export type ExtensionMessage =
  | { type: 'GET_CONTEXT' }
  | { type: 'ANALYZE' }
  | { type: 'JUMP'; target: JumpTarget };

export type ExtensionResponse =
  | { type: 'CONTEXT_RESPONSE'; context: PageContext }
  | { type: 'ANALYZE_RESPONSE'; paper: ParsedPaper }
  | { type: 'JUMP_RESPONSE'; result: JumpResult }
  | { type: 'ERROR_RESPONSE'; error: string };
