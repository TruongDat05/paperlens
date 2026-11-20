/**
 * Initialize React on the side panel page.
 *
 * Mount App in the root element of index.html. App manages presentation
 * state and interactions with the paper.
 */

import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';

const container = document.getElementById('root');
if (container) {
  const root = createRoot(container);
  root.render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
}
