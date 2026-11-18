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
