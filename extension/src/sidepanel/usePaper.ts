/**
 * Manage the open paper and its indexing status.
 *
 * Track the tab and document. After consent, ask the content script to
 * parse, send the ingest request through the API client, and poll
 * index_status for lexical_ready and semantic_ready.
 *
 * Apply results only when they match the current tab, document, version, and
 * operation. Send Jump requests to the document that was analyzed.
 */
