import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient, apiGet } from "$lib/api/client.js";
import * as configsClient from "./client";
import { loadConfigs, saveConfigSetting } from "./client";

vi.mock("$lib/api/client.js", () => ({
  apiClient: vi.fn(),
  apiGet: vi.fn(),
}));

const graphDepthSetting = {
  key: "graph-depth",
  section: "defaults",
  internal_key: "graph-depth",
  description: "Default graph traversal depth",
  value: "4",
  default_value: "2",
  configured: true,
  source: "configured" as const,
  input_type: "number" as const,
  options: [],
};

describe("configs client", () => {
  beforeEach(() => {
    vi.mocked(apiClient).mockReset();
    vi.mocked(apiGet).mockReset();
  });

  it("exports only generic config load and setting mutation operations", () => {
    expect(Object.keys(configsClient).sort()).toEqual([
      "loadConfigs",
      "saveConfigSetting",
    ]);
  });

  it("loads the encoded vault configs endpoint", async () => {
    const configs = { settings: [graphDepthSetting] };
    vi.mocked(apiGet).mockResolvedValueOnce(configs);

    await expect(loadConfigs("work vault")).resolves.toBe(configs);
    expect(apiGet).toHaveBeenCalledWith("/api/v1/vault/work%20vault/configs");
  });

  it("saves an encoded config setting and returns the updated setting", async () => {
    vi.mocked(apiClient).mockResolvedValueOnce(
      new Response(JSON.stringify(graphDepthSetting), { status: 200 }),
    );

    await expect(
      saveConfigSetting("work vault", "graph-depth", "4"),
    ).resolves.toEqual(graphDepthSetting);
    expect(apiClient).toHaveBeenCalledWith(
      "/api/v1/vault/work%20vault/configs/settings/graph-depth",
      {
        method: "PATCH",
        body: JSON.stringify({ value: "4" }),
      },
    );
  });

  it("resets a generic config setting with null", async () => {
    const reset = {
      ...graphDepthSetting,
      value: "2",
      configured: false,
      source: "default" as const,
    };
    vi.mocked(apiClient).mockResolvedValueOnce(
      new Response(JSON.stringify(reset), { status: 200 }),
    );

    await expect(
      saveConfigSetting("main", "graph-depth", null),
    ).resolves.toEqual(reset);
    expect(apiClient).toHaveBeenCalledWith(
      "/api/v1/vault/main/configs/settings/graph-depth",
      {
        method: "PATCH",
        body: JSON.stringify({ value: null }),
      },
    );
  });

  it("surfaces failed config setting saves with the response status", async () => {
    vi.mocked(apiClient).mockResolvedValueOnce(
      new Response("forbidden", { status: 403 }),
    );

    await expect(
      saveConfigSetting("main", "graph-depth", "bad"),
    ).rejects.toThrow("PATCH config setting → 403");
  });
});
