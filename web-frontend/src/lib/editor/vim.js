/**
 * Vim mappings for pkm-webapp.
 *
 * Slice 2 stub: leader + jk-escape.
 * Slice 4 (F4-5): ex commands + normal-mode mappings for navigation.
 *
 * The actual navigation is decoupled via `window.__pkmNav` hooks installed
 * by the route layer. Each ex command calls into the global hook so this
 * module stays free of route imports.
 *
 * Mappings are global on the Vim singleton, so install once.
 */
import * as cmvim from "@replit/codemirror-vim";
import { cmdkCoreCommandShortcuts } from "$lib/navigation/cmdk-command-shortcuts";
import { appNavPages } from "$lib/navigation/app-nav";

/** @type {any} */
const Vim = cmvim.Vim;

let installed = false;

/** @param {string} key */
function commandExName(key) {
  return `cmdk_${key.replace(/[^a-zA-Z0-9]/g, "_")}`;
}

/**
 * @param {string} key
 * @param {...string} args
 */
function callNav(key, ...args) {
  /** @type {any} */
  const nav = /** @type {any} */ (typeof window !== "undefined" ? window : {})
    .__pkmNav;
  const fn = nav?.[key];
  if (typeof fn === "function") fn(...args);
}

export function installVimMappings() {
  if (installed) return;
  installed = true;

  // Use Space as <leader> for leader-prefixed commands.
  Vim.map("<Space>", "<leader>", "normal");

  // Ergonomic escape: `jk` in insert mode returns to normal mode.
  Vim.map("jk", "<Esc>", "insert");

  // ----- Ex commands (handler receives (cm, params)). -----
  Vim.defineEx("gotoDaily", "", () => callNav("gotoDaily"));
  Vim.defineEx("nextNeighbor", "", () => callNav("nextNeighbor"));
  Vim.defineEx("prevNeighbor", "", () => callNav("prevNeighbor"));
  Vim.defineEx("followAtCursor", "", () => callNav("followAtCursor"));
  Vim.defineEx("openExternal", "", () => callNav("openExternal"));
  Vim.defineEx("openPalette", "", () => callNav("openPalette"));
  Vim.defineEx("openNoteSearch", "", () => callNav("openNoteSearch"));

  const cmdkCommands = [
    ...cmdkCoreCommandShortcuts,
    ...appNavPages.map((page) => ({
      id: `nav:${page.id}`,
      shortcut: page.commandShortcut,
    })),
  ];
  for (const command of cmdkCommands) {
    const exName = commandExName(command.id);
    Vim.defineEx(exName, "", () => callNav("runCmdKCommand", command.id));
    Vim.map(`<leader>${command.shortcut}`, `:${exName}<CR>`, "normal");
  }

  // ----- Normal-mode mappings -----
  Vim.map("gd", ":gotoDaily<CR>", "normal");
  Vim.map("gn", ":nextNeighbor<CR>", "normal");
  Vim.map("gp", ":prevNeighbor<CR>", "normal");
  Vim.map("gf", ":followAtCursor<CR>", "normal");
  Vim.map("gx", ":openExternal<CR>", "normal");
  Vim.map("<leader>k", ":openPalette<CR>", "normal");
}
