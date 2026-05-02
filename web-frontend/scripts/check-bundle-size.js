#!/usr/bin/env node
/**
 * check-bundle-size.js
 * Measures gzipped JS+CSS size of the production build.
 * Slice-4 budget: ≤ 330 KB gzipped (excludes fonts/woff2).
 *
 * Lineage:
 *   220 → 290 KB (slice 2) after CM6 stack landed at 284 KB.
 *   290 → 296 KB (slice 3) after CmdK + AskTranscript landed at 291.4 KB.
 *   296 → 330 KB (slice 4) for Maximalist additions (lazy KaTeX etc.).
 */

import { readdir, readFile } from 'node:fs/promises';
import { join, relative, sep } from 'node:path';
import { gzip } from 'node:zlib';
import { promisify } from 'node:util';

const gzipAsync = promisify(gzip);

const DIST_DIR = new URL('../dist', import.meta.url).pathname;
const BUDGET_KB = 330;

/**
 * Recursively list every file under {@link dir}.
 */
async function walk(dir /*: string */) /*: Promise<string[]> */ {
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
      const nested = await walk(full);
      out.push(...nested);
    } else if (entry.isFile()) {
      out.push(full);
    }
  }
  return out;
}

function isFontPath(file /*: string */) /*: boolean */ {
  const norm = file.split(sep).join('/');
  return norm.includes('/fonts/') || norm.endsWith('.woff2');
}

function isJsOrCss(file /*: string */) /*: boolean */ {
  return file.endsWith('.js') || file.endsWith('.css');
}

async function main() {
  const all = await walk(DIST_DIR);
  const targets = all.filter((f) => isJsOrCss(f) && !isFontPath(f));

  if (targets.length === 0) {
    console.error('No JS/CSS files found in dist/. Run `pnpm build` first.');
    process.exit(1);
  }

  /** @type {{ rel: string, kb: number }[]} */
  const rows = [];
  let totalBytes = 0;
  for (const file of targets) {
    const buf = await readFile(file);
    const gz = await gzipAsync(buf);
    totalBytes += gz.length;
    const rel = relative(DIST_DIR, file).split(sep).join('/');
    rows.push({ rel, kb: gz.length / 1024 });
  }

  rows.sort((a, b) => b.kb - a.kb);
  for (const row of rows) {
    console.log(`${row.rel} ${row.kb.toFixed(1)}`);
  }

  const totalKb = totalBytes / 1024;
  console.log('');
  console.log(`Total gzipped JS+CSS: ${totalKb.toFixed(1)} KB (budget: ${BUDGET_KB} KB)`);

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
