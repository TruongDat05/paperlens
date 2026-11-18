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
