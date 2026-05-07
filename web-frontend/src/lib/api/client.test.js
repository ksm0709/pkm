import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient, apiGet } from "./client.js";

function createStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: vi.fn((key) => values.get(key) ?? null),
    removeItem: vi.fn((key) => values.delete(key)),
    setItem: vi.fn((key, value) => values.set(key, value)),
  };
}

describe("api client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends same-origin requests with a stored bearer token and caller headers", async () => {
    const localStorage = createStorage({ "pkm.token": "stored-token" });
    const sessionStorage = createStorage({ "pkm.token": "session-token" });
    const fetch = vi.fn(async () => new Response("{}", { status: 200 }));

    vi.stubGlobal("localStorage", localStorage);
    vi.stubGlobal("sessionStorage", sessionStorage);
    vi.stubGlobal("fetch", fetch);

    const response = await apiClient("/api/v1/vault/main/notes", {
      headers: { "X-Trace": "abc" },
      method: "POST",
    });

    expect(response.status).toBe(200);
    expect(fetch).toHaveBeenCalledWith("/api/v1/vault/main/notes", {
      credentials: "same-origin",
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Trace": "abc",
        Authorization: "Bearer stored-token",
      },
    });
  });

  it("lets an explicit token override stored browser tokens", async () => {
    const fetch = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal(
      "localStorage",
      createStorage({ "pkm.token": "stored-token" }),
    );
    vi.stubGlobal(
      "sessionStorage",
      createStorage({ "pkm.token": "session-token" }),
    );
    vi.stubGlobal("fetch", fetch);

    await apiClient("/api/v1/status", { token: "override-token" });

    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/status",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer override-token",
        }),
      }),
    );
  });

  it("clears stale tokens and redirects to login after an unauthorized response", async () => {
    const localStorage = createStorage({ "pkm.token": "bad-token" });
    const sessionStorage = createStorage({ "pkm.token": "fallback-token" });
    const fetch = vi.fn(
      async () => new Response("unauthorized", { status: 401 }),
    );
    const windowLocation = { href: "/vault/main" };

    vi.stubGlobal("localStorage", localStorage);
    vi.stubGlobal("sessionStorage", sessionStorage);
    vi.stubGlobal("fetch", fetch);
    vi.stubGlobal("window", { location: windowLocation });

    const response = await apiClient("/api/v1/private");

    expect(response.status).toBe(401);
    expect(localStorage.removeItem).toHaveBeenCalledWith("pkm.token");
    expect(sessionStorage.removeItem).toHaveBeenCalledWith("pkm.token");
    expect(windowLocation.href).toBe("/");
  });

  it("apiGet parses successful JSON and includes method GET", async () => {
    const fetch = vi.fn(
      async () => new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    vi.stubGlobal("localStorage", createStorage());
    vi.stubGlobal("sessionStorage", createStorage());
    vi.stubGlobal("fetch", fetch);

    await expect(apiGet("/api/v1/status")).resolves.toEqual({ ok: true });
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/status",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("apiGet reports the failing path and status for non-OK responses", async () => {
    vi.stubGlobal("localStorage", createStorage());
    vi.stubGlobal("sessionStorage", createStorage());
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("nope", { status: 503 })),
    );

    await expect(apiGet("/api/v1/unavailable")).rejects.toThrow(
      "GET /api/v1/unavailable → 503",
    );
  });
});
