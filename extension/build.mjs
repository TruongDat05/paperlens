/**
 * Package the Manifest V3 Chrome Extension with esbuild.
 *
 * Build dist/background.js from background/index.ts, dist/content.js from
 * content/index.ts, and dist/sidepanel/main.js from sidepanel/main.tsx.
 * Package the content script as a self-contained bundle.
 *
 * Copy the manifest, index.html, and styles.css to their declared paths.
 * Configure the backend origin and corresponding host permissions for local
 * or public builds.
 */
