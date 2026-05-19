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
      ["gd", ":gotoDaily<CR>", "normal"],
      ["gn", ":nextNeighbor<CR>", "normal"],
      ["gp", ":prevNeighbor<CR>", "normal"],
      ["gf", ":followAtCursor<CR>", "normal"],
      ["gx", ":openExternal<CR>", "normal"],
      ["<leader>k", ":openPalette<CR>", "normal"],
      ["<leader>/", ":openNoteSearch<CR>", "normal"],
    ]);
    expect(defineEx.mock.calls.map((call) => call[0])).toEqual([
      "gotoDaily",
      "nextNeighbor",
      "prevNeighbor",
      "followAtCursor",
      "openExternal",
      "openPalette",
      "openNoteSearch",
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
});
