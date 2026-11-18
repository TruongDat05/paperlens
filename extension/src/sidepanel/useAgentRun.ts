/**
 * Manage question runs and Evidence Mode in the side panel.
 *
 * Send Ask or a follow-up with at most 3 history turns for the same paper
 * version. Manage request_id, run_id, polling, cancellation, and polling
 * recovery from chrome.storage.session within the current session.
 *
 * Apply responses only when they match the owner, tab, document, and active
 * run. Use the retrieve endpoint for direct evidence results.
 */
