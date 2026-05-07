import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient, apiGet } from "$lib/api/client.js";
import { deleteAskCredential, loadConfigs, saveAskCredential } from "./client";

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
