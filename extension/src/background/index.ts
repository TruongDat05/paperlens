/**
 * Register how the Chrome Extension opens its side panel.
 *
 * Configure the toolbar icon to open the panel during the service worker
 * lifecycle. FastAPI owns the lifecycle of indexing jobs and question runs.
 */

chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.error('Failed to set panel behavior:', error));
