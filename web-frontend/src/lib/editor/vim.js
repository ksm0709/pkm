/**
 * Basic vim mappings stub for slice 2.
 * Full mappings (leader-based, custom motions) land in slice 4.
 *
 * Mappings are global on the Vim singleton, so install once.
 */
import * as cmvim from '@replit/codemirror-vim';

/** @type {any} */
const Vim = cmvim.Vim;

let installed = false;

export function installVimMappings() {
  if (installed) return;
  installed = true;

  // Use Space as <leader> for future slice 4 leader-prefixed commands.
  Vim.map('<Space>', '<leader>', 'normal');

  // Ergonomic escape: `jk` in insert mode returns to normal mode.
  Vim.map('jk', '<Esc>', 'insert');
}
