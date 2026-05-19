import { beforeEach, describe, expect, it, vi } from "vitest";

describe("vim mappings", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllGlobals();
  });

  it("installs navigation ex commands and normal-mode shortcuts once", async () => {
    const map = vi.fn();
    const defineEx = vi.fn();
    vi.doMock("@replit/codemirror-vim", () => ({ Vim: { map, defineEx } }));

    const { installVimMappings } = await import("./vim.js");

    installVimMappings();
    installVimMappings();

    expect(map.mock.calls).toEqual([
      ["<Space>", "<leader>", "normal"],
      ["jk", "<Esc>", "insert"],
      ["<leader>/", ":cmdk_cmd_jump<CR>", "normal"],
      ["<leader>y", ":cmdk_cmd_daily<CR>", "normal"],
      ["<leader>s", ":cmdk_cmd_daily_subnote<CR>", "normal"],
      ["<leader>i", ":cmdk_cmd_index_vault<CR>", "normal"],
      ["<leader>q", ":cmdk_cmd_ask<CR>", "normal"],
      ["<leader>v", ":cmdk_cmd_switch<CR>", "normal"],
      ["<leader>h", ":cmdk_cmd_theme<CR>", "normal"],
      ["<leader>n", ":cmdk_nav_notes<CR>", "normal"],
      ["<leader>t", ":cmdk_nav_tags<CR>", "normal"],
      ["<leader>g", ":cmdk_nav_graph<CR>", "normal"],
      ["<leader>a", ":cmdk_nav_ask<CR>", "normal"],
      ["<leader>l", ":cmdk_nav_logger<CR>", "normal"],
      ["<leader>w", ":cmdk_nav_workflows<CR>", "normal"],
      ["<leader>d", ":cmdk_nav_daily<CR>", "normal"],
      ["<leader>c", ":cmdk_nav_configs<CR>", "normal"],
      ["gd", ":gotoDaily<CR>", "normal"],
      ["gn", ":nextNeighbor<CR>", "normal"],
      ["gp", ":prevNeighbor<CR>", "normal"],
      ["gf", ":followAtCursor<CR>", "normal"],
      ["gx", ":openExternal<CR>", "normal"],
      ["<leader>k", ":openPalette<CR>", "normal"],
    ]);
    expect(defineEx.mock.calls.map((call) => call[0])).toEqual([
      "gotoDaily",
      "nextNeighbor",
      "prevNeighbor",
      "followAtCursor",
      "openExternal",
      "openPalette",
      "openNoteSearch",
      "cmdk_cmd_jump",
      "cmdk_cmd_daily",
      "cmdk_cmd_daily_subnote",
      "cmdk_cmd_index_vault",
      "cmdk_cmd_ask",
      "cmdk_cmd_switch",
      "cmdk_cmd_theme",
      "cmdk_nav_notes",
      "cmdk_nav_tags",
      "cmdk_nav_graph",
      "cmdk_nav_ask",
      "cmdk_nav_logger",
      "cmdk_nav_workflows",
      "cmdk_nav_daily",
      "cmdk_nav_configs",
    ]);
  });

  it("routes ex command handlers through the window navigation hook", async () => {
    const defineEx = vi.fn();
    vi.doMock("@replit/codemirror-vim", () => ({
      Vim: {
        map: vi.fn(),
        defineEx,
      },
    }));
    const gotoDaily = vi.fn();
    vi.stubGlobal("window", { __pkmNav: { gotoDaily } });

    const { installVimMappings } = await import("./vim.js");
    installVimMappings();
    const handler = defineEx.mock.calls.find(
      (call) => call[0] === "gotoDaily",
    )?.[2];

    handler?.();

    expect(gotoDaily).toHaveBeenCalledTimes(1);
  });

  it("routes leader command handlers through the command shortcut hook", async () => {
    const defineEx = vi.fn();
    vi.doMock("@replit/codemirror-vim", () => ({
      Vim: {
        map: vi.fn(),
        defineEx,
      },
    }));
    const runCmdKCommand = vi.fn();
    vi.stubGlobal("window", { __pkmNav: { runCmdKCommand } });

    const { installVimMappings } = await import("./vim.js");
    installVimMappings();
    const handler = defineEx.mock.calls.find(
      (call) => call[0] === "cmdk_nav_graph",
    )?.[2];

    handler?.();

    expect(runCmdKCommand).toHaveBeenCalledWith("nav:graph");
  });
});
