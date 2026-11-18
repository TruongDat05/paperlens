/**
 * Send HTTP requests from the side panel to FastAPI.
 *
 * Use the backend origin for the current build and the current session
 * token. Support aborting fetches and reuse request_id when retrying the
 * same operation.
 *
 * Normalize offline, authentication, quota, and provider errors for display
 * in the UI.
 */
