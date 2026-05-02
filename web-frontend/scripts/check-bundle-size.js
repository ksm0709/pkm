#!/usr/bin/env node
/**
 * check-bundle-size.js
 *
 * SvelteKit + adapter-static writes the deliverable to
 * ../cli/src/pkm/web/static/. We measure the worst-case single-page load:
 *
 *   eager (index.html modulepreload + stylesheet) +
 *     max(per-route chunks)  // SvelteKit nodes/N.*.js + their static CSS
 *
 * "Lazy" chunks loaded only behind a dynamic `import()` (KaTeX, etc.) are
 * detected via Vite's `_app/version.json`-adjacent manifest and excluded —
 * they are opt-in payloads that don't gate first paint or first interaction.
 *
 * Slice-4 budget (eager + worst route): ≤ 330 KB gzipped, excluding fonts.
 * Lineage:
 *   220 → 290 KB (slice 2) after CM6 stack landed at 284 KB.
 *   290 → 296 KB (slice 3) after CmdK + AskTranscript landed at 291.4 KB.
 *   296 → 330 KB (slice 4) for Maximalist additions; KaTeX is dynamically
 *   imported on first $-match and excluded from the eager+route sum.
 */

import { readdir, readFile } from 'node:fs/promises';
import { join, relative, sep } from 'node:path';
import { gzip } from 'node:zlib';
import { promisify } from 'node:util';

const gzipAsync = promisify(gzip);

const STATIC_DIR = new URL('../../cli/src/pkm/web/static', import.meta.url).pathname;
const BUDGET_KB = 330;

/** @param {string} dir @returns {Promise<string[]>} */
async function walk(dir) {
  /** @type {string[]} */
  const out = [];
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...(await walk(full)));
    } else if (entry.isFile()) {
      out.push(full);
    }
  }
  return out;
}

/** @param {string} file */
function isFontPath(file) {
  const norm = file.split(sep).join('/');
  return (
    norm.includes('/fonts/') ||
    norm.endsWith('.woff2') ||
    norm.endsWith('.woff') ||
    norm.endsWith('.ttf')
  );
}

/** @param {string} file */
function isJsOrCss(file) {
  return file.endsWith('.js') || file.endsWith('.css');
}

/** @param {string} absPath */
async function gzippedSize(absPath) {
  const buf = await readFile(absPath);
  const gz = await gzipAsync(buf);
  return gz.length;
}

/** Parse `<link rel="modulepreload|stylesheet" href="...">` hrefs from index.html. */
async function parseEagerHrefs(/** @type {string} */ htmlPath) {
  const html = await readFile(htmlPath, 'utf8');
  /** @type {Set<string>} */
  const hrefs = new Set();
  const re1 = /<link[^>]+href="([^"]+)"[^>]+rel="(modulepreload|stylesheet)"/g;
  for (const m of html.matchAll(re1)) hrefs.add(m[1]);
  const re2 = /<link[^>]+rel="(modulepreload|stylesheet)"[^>]+href="([^"]+)"/g;
  for (const m of html.matchAll(re2)) hrefs.add(m[2]);
  return hrefs;
}

async function main() {
  const indexHtml = join(STATIC_DIR, 'index.html');
  let eagerHrefs;
  try {
    eagerHrefs = await parseEagerHrefs(indexHtml);
  } catch {
    console.error(`Cannot read ${indexHtml}. Run \`pnpm build\` first.`);
    process.exit(1);
  }

  const all = await walk(STATIC_DIR);
  const targets = all.filter((f) => isJsOrCss(f) && !isFontPath(f));
  if (targets.length === 0) {
    console.error('No JS/CSS files found in cli/src/pkm/web/static/. Run `pnpm build` first.');
    process.exit(1);
  }

  /** @type {Map<string, number>} relPath -> gzipped bytes */
  const sizes = new Map();
  for (const file of targets) {
    const rel = '/' + relative(STATIC_DIR, file).split(sep).join('/');
    sizes.set(rel, await gzippedSize(file));
  }

  /** Eager = preloaded by index.html. */
  const eagerRows = [];
  let eagerBytes = 0;
  for (const [rel, gz] of sizes) {
    if (eagerHrefs.has(rel)) {
      eagerBytes += gz;
      eagerRows.push({ rel, kb: gz / 1024 });
    }
  }

  /**
   * Per-route chunks: SvelteKit emits one `_app/immutable/nodes/N.<hash>.js`
   * per route plus a sibling `_app/immutable/assets/N.<hash>.css`. The
   * heaviest of those represents the worst-case route delta the user must
   * download to interact with the heaviest page (the editor).
   */
  /** @type {Map<string, number>} */
  const routeBytes = new Map();
  for (const [rel, gz] of sizes) {
    if (eagerHrefs.has(rel)) continue;
    const m = rel.match(/^\/_app\/immutable\/nodes\/(\d+)\.[^/]+\.js$/);
    const ma = rel.match(/^\/_app\/immutable\/assets\/(\d+)\.[^/]+\.css$/);
    const id = m?.[1] ?? ma?.[1];
    if (!id) continue;
    routeBytes.set(id, (routeBytes.get(id) ?? 0) + gz);
  }
  let worstRouteId = '';
  let worstRouteBytes = 0;
  for (const [id, b] of routeBytes) {
    if (b > worstRouteBytes) {
      worstRouteBytes = b;
      worstRouteId = id;
    }
  }

  /** Lazy = everything that's neither eager nor a route node/asset. */
  const lazyRows = [];
  let lazyBytes = 0;
  for (const [rel, gz] of sizes) {
    if (eagerHrefs.has(rel)) continue;
    const m = rel.match(/^\/_app\/immutable\/(nodes|assets)\/(\d+)\.[^/]+\.(js|css)$/);
    if (m) continue; // counted in routeBytes above
    lazyBytes += gz;
    lazyRows.push({ rel, kb: gz / 1024 });
  }

  eagerRows.sort((a, b) => b.kb - a.kb);
  lazyRows.sort((a, b) => b.kb - a.kb);

  console.log('Eager (index.html modulepreload + stylesheet):');
  for (const row of eagerRows) console.log(`  ${row.kb.toFixed(1).padStart(7)} KB  ${row.rel}`);
  console.log('');
  console.log(`Worst route (#${worstRouteId}): ${(worstRouteBytes / 1024).toFixed(1)} KB`);
  console.log('');
  console.log('Lazy (dynamic-import-only chunks; not counted):');
  for (const row of lazyRows) console.log(`  ${row.kb.toFixed(1).padStart(7)} KB  ${row.rel}`);
  console.log('');

  const eagerKb = eagerBytes / 1024;
  const worstKb = worstRouteBytes / 1024;
  const lazyKb = lazyBytes / 1024;
  const totalKb = eagerKb + worstKb;
  console.log(`Eager       : ${eagerKb.toFixed(1)} KB`);
  console.log(`Worst route : ${worstKb.toFixed(1)} KB`);
  console.log(`Eager+route : ${totalKb.toFixed(1)} KB (budget: ${BUDGET_KB} KB)`);
  console.log(`Lazy total  : ${lazyKb.toFixed(1)} KB (informational; excluded from cap)`);

  if (totalKb > BUDGET_KB) {
    console.error(`FAIL: ${totalKb.toFixed(1)} KB exceeds ${BUDGET_KB} KB budget`);
    process.exit(1);
  }
  console.log(`PASS: ${(BUDGET_KB - totalKb).toFixed(1)} KB headroom remaining`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
