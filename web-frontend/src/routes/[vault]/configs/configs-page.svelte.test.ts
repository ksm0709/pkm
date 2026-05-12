// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import Page from "./+page.svelte";

const mocks = vi.hoisted(() => ({
  deleteAskCredential: vi.fn(),
  loadConfigs: vi.fn(),
  saveAskCredential: vi.fn(),
  saveConfigSetting: vi.fn(),
}));

vi.mock("$app/stores", async () => {
  const { readable } = await import("svelte/store");
  return {
    page: readable({ params: { vault: "main" } }),
  };
});

vi.mock("$lib/configs/client", () => ({
  deleteAskCredential: mocks.deleteAskCredential,
  loadConfigs: mocks.loadConfigs,
  saveAskCredential: mocks.saveAskCredential,
  saveConfigSetting: mocks.saveConfigSetting,
}));

describe("configs page", () => {
  afterEach(() => {
    vi.clearAllMocks();
    document.body.innerHTML = "";
  });

  async function flush() {
    await Promise.resolve();
    await Promise.resolve();
    await tick();
  }

  function render() {
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(Page, { target });
    return { target, component };
  }

  it("renders ask model choices as a select and saves the selected model", async () => {
    mocks.loadConfigs.mockResolvedValue({
      settings: [
        {
          key: "model",
          section: "defaults",
          internal_key: "model",
          description: "LLM model",
          value: "auto",
          default_value: "auto",
          configured: false,
          source: "default",
          input_type: "select",
          options: ["auto", "gpt-5-nano"],
        },
      ],
      ask_credentials: { providers: [] },
    });
    mocks.saveConfigSetting.mockResolvedValue({
      key: "model",
      section: "defaults",
      internal_key: "model",
      description: "LLM model",
      value: "gpt-5-nano",
      default_value: "auto",
      configured: true,
      source: "configured",
      input_type: "select",
      options: ["auto", "gpt-5-nano"],
    });

    const { target, component } = render();
    await flush();

    const select = target.querySelector<HTMLSelectElement>(
      'select[aria-label="model value"]',
    );
    expect(select).not.toBeNull();
    expect(target.querySelector('input[aria-label="model value"]')).toBeNull();
    expect(Array.from(select!.options).map((option) => option.value)).toEqual([
      "auto",
      "gpt-5-nano",
    ]);

    select!.value = "gpt-5-nano";
    select!.dispatchEvent(new Event("change", { bubbles: true }));
    await tick();

    const saveButton = target.querySelector<HTMLButtonElement>(
      'button[aria-label="Save model"]',
    );
    expect(saveButton?.disabled).toBe(false);
    saveButton?.click();
    await flush();

    expect(mocks.saveConfigSetting).toHaveBeenCalledWith(
      "main",
      "model",
      "gpt-5-nano",
    );

    unmount(component);
  });

  it("dispatches config-change after saving window padding", async () => {
    const listener = vi.fn();
    window.addEventListener("pkm:config-change", listener);
    mocks.loadConfigs.mockResolvedValue({
      settings: [
        {
          key: "web-window-padding",
          section: "web",
          internal_key: "window_padding",
          description: "Web window padding",
          value: "32",
          default_value: "32",
          configured: false,
          source: "default",
          input_type: "number",
          options: [],
        },
      ],
      ask_credentials: { providers: [] },
    });
    mocks.saveConfigSetting.mockResolvedValue({
      key: "web-window-padding",
      section: "web",
      internal_key: "window_padding",
      description: "Web window padding",
      value: "64",
      default_value: "",
      configured: true,
      source: "configured",
      input_type: "number",
      options: [],
    });

    const { target, component } = render();
    await flush();

    const input = target.querySelector<HTMLInputElement>(
      'input[aria-label="web-window-padding value"]',
    );
    input!.value = "64";
    input!.dispatchEvent(new Event("input", { bubbles: true }));
    await tick();

    target
      .querySelector<HTMLButtonElement>(
        'button[aria-label="Save web-window-padding"]',
      )
      ?.click();
    await flush();

    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener.mock.calls[0][0].detail).toEqual({
      key: "web-window-padding",
      value: "64",
    });

    window.removeEventListener("pkm:config-change", listener);
    unmount(component);
  });

  it("dispatches config-change after resetting window padding", async () => {
    const listener = vi.fn();
    window.addEventListener("pkm:config-change", listener);
    mocks.loadConfigs.mockResolvedValue({
      settings: [
        {
          key: "web-window-padding",
          section: "web",
          internal_key: "window_padding",
          description: "Web window padding",
          value: "64",
          default_value: "",
          configured: true,
          source: "configured",
          input_type: "number",
          options: [],
        },
      ],
      ask_credentials: { providers: [] },
    });
    mocks.saveConfigSetting.mockResolvedValue({
      key: "web-window-padding",
      section: "web",
      internal_key: "window_padding",
      description: "Web window padding",
      value: "32",
      default_value: "32",
      configured: false,
      source: "default",
      input_type: "number",
      options: [],
    });

    const { target, component } = render();
    await flush();

    target
      .querySelector<HTMLButtonElement>(
        'button[aria-label="Reset web-window-padding"]',
      )
      ?.click();
    await flush();

    expect(mocks.saveConfigSetting).toHaveBeenCalledWith(
      "main",
      "web-window-padding",
      null,
    );
    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener.mock.calls[0][0].detail).toEqual({
      key: "web-window-padding",
      value: "32",
    });

    window.removeEventListener("pkm:config-change", listener);
    unmount(component);
  });
});
