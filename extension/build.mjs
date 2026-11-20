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

import * as esbuild from 'esbuild';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const isWatch = process.argv.includes('--watch');
const outDir = process.env.PAPERLENS_OUT_DIR || path.resolve(__dirname, 'dist');

async function build() {
  if (!fs.existsSync(outDir)) {
    fs.mkdirSync(outDir, { recursive: true });
  }
  const sidepanelDist = path.resolve(outDir, 'sidepanel');
  if (!fs.existsSync(sidepanelDist)) {
    fs.mkdirSync(sidepanelDist, { recursive: true });
  }

  // Read and adjust manifest for unpacked distribution package in dist/
  const manifestContent = fs.readFileSync(path.resolve(__dirname, 'manifest.json'), 'utf-8');
  const manifest = JSON.parse(manifestContent);
  if (manifest.background?.service_worker) {
    manifest.background.service_worker = manifest.background.service_worker.replace(/^dist\//, '');
  }
  if (Array.isArray(manifest.content_scripts)) {
    for (const cs of manifest.content_scripts) {
      if (Array.isArray(cs.js)) {
        cs.js = cs.js.map((p) => p.replace(/^dist\//, ''));
      }
    }
  }
  if (manifest.side_panel?.default_path) {
    manifest.side_panel.default_path = manifest.side_panel.default_path.replace(/^dist\//, '');
  }
  if (Array.isArray(manifest.web_accessible_resources)) {
    for (const war of manifest.web_accessible_resources) {
      if (Array.isArray(war.resources)) {
        war.resources = war.resources.map((p) => p.replace(/^dist\//, ''));
      }
    }
  }
  const backendOrigin = new URL(process.env.BACKEND_URL || 'http://localhost:8000').origin;
  manifest.host_permissions = [...new Set([...(manifest.host_permissions || []), `${backendOrigin}/*`])];
  fs.writeFileSync(
    path.resolve(outDir, 'manifest.json'),
    JSON.stringify(manifest, null, 2),
    'utf-8'
  );

  fs.copyFileSync(
    path.resolve(__dirname, 'src/sidepanel/index.html'),
    path.resolve(sidepanelDist, 'index.html')
  );
  fs.copyFileSync(
    path.resolve(__dirname, 'src/sidepanel/styles.css'),
    path.resolve(sidepanelDist, 'styles.css')
  );

  fs.copyFileSync(path.join(__dirname, 'node_modules/katex/dist/katex.min.css'), path.join(sidepanelDist, 'katex.min.css'));
  fs.cpSync(path.join(__dirname, 'node_modules/katex/dist/fonts'), path.join(sidepanelDist, 'fonts'), { recursive: true });

  const buildOptions = {
    bundle: true,
    sourcemap: true,
    target: ['chrome114'],
    define: {
      'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV || 'production'),
      'process.env.BACKEND_URL': JSON.stringify(process.env.BACKEND_URL || 'http://localhost:8000')
    }
  };

  const entryPoints = [
    { in: path.resolve(__dirname, 'src/background/index.ts'), out: 'background' },
    { in: path.resolve(__dirname, 'src/content/index.ts'), out: 'content' },
    { in: path.resolve(__dirname, 'src/sidepanel/main.tsx'), out: 'sidepanel/main' }
  ];

  await esbuild.build({
    ...buildOptions,
    entryPoints,
    outdir: outDir,
    format: 'esm'
  });

  console.log('Build complete -> dist/');
}

build().catch((err) => {
  console.error('Build failed:', err);
  process.exit(1);
});
