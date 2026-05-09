import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient, apiGet } from "$lib/api/client.js";
import {
  deleteAskCredential,
  loadConfigs,
  saveAskCredential,
  saveConfigSetting,
} from "./client";

vi.mock("$lib/api/client.js", () => ({
  apiClient: vi.fn(),
  apiGet: vi.fn(),
}));

describe("configs client", () => {
  beforeEach(() => {
    vi.mocked(apiClient).mockReset();
    vi.mocked(apiGet).mockReset();
  });

  it("loads the encoded vault configs endpoint", async () => {
    const configs = {
      settings: [
        {
          key: "model",
          section: "defaults",
          internal_key: "model",
          description: "LLM model",
          value: "auto",
          default_value: "",
          configured: true,
          source: "configured",
          input_type: "text",
          options: [],
        },
      ],
      ask_credentials: {
        providers: [
          {
            id: "openai",
            label: "OpenAI",
            env_key: "OPENAI_API_KEY",
            configured: true,
            fingerprint: "sk-...abcd",
          },
        ],
      },
    };
    vi.mocked(apiGet).mockResolvedValueOnce(configs);

    await expect(loadConfigs("work vault")).resolves.toBe(configs);
    expect(apiGet).toHaveBeenCalledWith("/api/v1/vault/work%20vault/configs");
  });

  it("saves an encoded config setting and returns the updated setting", async () => {
    const updated = {
      key: "graph-depth",
      section: "defaults",
      internal_key: "graph-depth",
      description: "Default graph traversal depth",
      value: "4",
      default_value: "",
      configured: true,
      source: "configured",
      input_type: "number",
      options: [],
    };
    vi.mocked(apiClient).mockResolvedValueOnce(
      new Response(JSON.stringify(updated), { status: 200 }),
    );

    await expect(
      saveConfigSetting("work vault", "graph-depth", "4"),
    ).resolves.toEqual(updated);
    expect(apiClient).toHaveBeenCalledWith(
      "/api/v1/vault/work%20vault/configs/settings/graph-depth",
      {
        method: "PATCH",
        body: JSON.stringify({ value: "4" }),
      },
    );
  });

  it("surfaces failed config setting saves with the response status", async () => {
    vi.mocked(apiClient).mockResolvedValueOnce(
      new Response("forbidden", { status: 403 }),
    );

    await expect(saveConfigSetting("main", "model", "bad")).rejects.toThrow(
      "PATCH config setting → 403",
    );
  });

  it("saves an ask credential with encoded vault and provider ids", async () => {
    vi.mocked(apiClient).mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );

    await saveAskCredential("work vault", "provider/slash", "secret-key");

    expect(apiClient).toHaveBeenCalledWith(
      "/api/v1/vault/work%20vault/configs/ask/credentials/provider%2Fslash",
      {
        method: "PUT",
        body: JSON.stringify({ api_key: "secret-key" }),
      },
    );
  });

  it("surfaces failed ask credential saves with the response status", async () => {
    vi.mocked(apiClient).mockResolvedValueOnce(
      new Response("bad", { status: 422 }),
    );

    await expect(
      saveAskCredential("main", "openai", "bad-key"),
    ).rejects.toThrow("PUT ask credential → 422");
  });

  it("deletes an ask credential and reports delete failures", async () => {
    vi.mocked(apiClient)
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(new Response("locked", { status: 409 }));

    await expect(
      deleteAskCredential("main", "openai"),
    ).resolves.toBeUndefined();
    expect(apiClient).toHaveBeenNthCalledWith(
      1,
      "/api/v1/vault/main/configs/ask/credentials/openai",
      { method: "DELETE" },
    );

    await expect(deleteAskCredential("main", "openai")).rejects.toThrow(
      "DELETE ask credential → 409",
    );
  });
});
