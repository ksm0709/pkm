// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { readRememberedVault, rememberVault } from "./remembered-vault";

describe("remembered vault", () => {
  beforeEach(() => {
    localStorage.clear();
    document.cookie = "pkm_last_vault=; Max-Age=0; Path=/";
  });

  afterEach(() => {
    localStorage.clear();
    document.cookie = "pkm_last_vault=; Max-Age=0; Path=/";
  });

  it("writes local storage and a cookie for process-kill recovery", () => {
    rememberVault("bear");

    expect(localStorage.getItem("pkm.lastVault")).toBe("bear");
    expect(document.cookie).toContain("pkm_last_vault=bear");
  });

  it("falls back to the cookie when local storage is empty", () => {
    document.cookie = "pkm_last_vault=bear; Path=/";

    expect(readRememberedVault()).toBe("bear");
  });

  it("prefers local storage when both sources are present", () => {
    localStorage.setItem("pkm.lastVault", "research");
    document.cookie = "pkm_last_vault=bear; Path=/";

    expect(readRememberedVault()).toBe("research");
  });
});
