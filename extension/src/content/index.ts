/**
 * Receive messages in the top frame of an arXiv page.
 *
 * Verify the document context before calling the parser or navigation code.
 * Return page information, paragraphs, or Jump results in the corresponding
 * response.
 */

import {
  ExtensionMessage,
  ExtensionResponse,
} from '../messages';
import {
  detectPageContext,
  parseArxivDocument,
} from './parser';
import {
  jumpToParagraph,
} from './navigation';
import { initOverlay } from './overlay';

// Ensure content script only runs in top window frame
if (window.top === window.self) {
  // Initialize the in-page Floating Launcher & Resizable Overlay
  try {
    initOverlay();
  } catch (err) {
    console.error('Failed to initialize PaperLens in-page overlay:', err);
  }

  chrome.runtime.onMessage.addListener(
    (
      message: ExtensionMessage,
      _sender: chrome.runtime.MessageSender,
      sendResponse: (response: ExtensionResponse) => void
    ) => {
      handleMessage(message)
        .then(sendResponse)
        .catch((err: Error) => {
          sendResponse({
            type: 'ERROR_RESPONSE',
            error: err.message || 'Unknown content script error',
          });
        });
      return true; // Keep channel open for async response
    }
  );
}

async function handleMessage(message: ExtensionMessage): Promise<ExtensionResponse> {
  const url = window.location.href;

  switch (message.type) {
    case 'GET_CONTEXT': {
      const context = detectPageContext(url, document);
      return { type: 'CONTEXT_RESPONSE', context };
    }

    case 'ANALYZE': {
      const paper = await parseArxivDocument(document, url);
      return { type: 'ANALYZE_RESPONSE', paper };
    }

    case 'JUMP': {
      const result = await jumpToParagraph(document, message.target);
      if (result.status === 'verified' || result.status === 'section_fallback') window.dispatchEvent(new Event('paperlens-reveal-source'));
      return { type: 'JUMP_RESPONSE', result };
    }

    default:
      throw new Error(`Unhandled message type`);
  }
}
