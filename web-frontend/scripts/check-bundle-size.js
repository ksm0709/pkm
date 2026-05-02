#!/usr/bin/env node
/**
 * check-bundle-size.js
 * Measures gzipped JS+CSS size of the production build.
 * Slice-2 budget: ≤ 290 KB gzipped (excluding fonts).
 * Renegotiated from 220 KB after CM6 + @replit/codemirror-vim + lang-markdown
 * landed at 284 KB. Total cap (slice 4 with Maximalist incl. lazy KaTeX) stays
 * at 330 KB, so slice-4 headroom for non-lazy Maximalist additions is 40 KB.
 */

import { readFileSync, readdirSync, statSync } from 'fs';
import { join, extname } from 'path';
import { gzipSync } from 'zlib';

const DIST_DIR = new URL('../dist', import.meta.url).pathname;
const BUDGET_KB = 290;

function walkDir(dir, files = []) {
  try {
    const entries = readdirSync(dir);
    for (const entry of entries) {
      const fullPath = join(dir, entry);
      const stat = statSync(fullPath);
      if (stat.isDirectory()) {
        walkDir(fullPath, files);
      } else {
        files.push(fullPath);
      }
    }
  } catch {
    // dist may not exist yet
  }
  return files;
}

const allFiles = walkDir(DIST_DIR);
const jsAndCss = allFiles.filter((f) => {
  const ext = extname(f);
  const isFont = f.includes('/fonts/') || f.endsWith('.woff2') || f.endsWith('.woff') || f.endsWith('.ttf');
  return !isFont && (ext === '.js' || ext === '.css');
});

if (jsAndCss.length === 0) {
  console.error('No JS/CSS files found in dist/. Run `pnpm build` first.');
  process.exit(1);
}

let totalGzipBytes = 0;
for (const file of jsAndCss) {
  const content = readFileSync(file);
  const gzipped = gzipSync(content);
  totalGzipBytes += gzipped.length;
  const kb = (gzipped.length / 1024).toFixed(1);
  console.log(`  ${kb.padStart(7)} KB  ${file.replace(DIST_DIR, 'dist')}`);
}

const totalKb = totalGzipBytes / 1024;
console.log('');
console.log(`Total gzipped JS+CSS: ${totalKb.toFixed(1)} KB (budget: ${BUDGET_KB} KB)`);

if (totalKb > BUDGET_KB) {
  console.error(`FAIL: ${totalKb.toFixed(1)} KB exceeds ${BUDGET_KB} KB budget`);
  process.exit(1);
} else {
  console.log(`PASS: ${(BUDGET_KB - totalKb).toFixed(1)} KB headroom remaining`);
}
