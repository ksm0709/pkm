// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import GraphTypeFilters from "./GraphTypeFilters.svelte";

describe("GraphTypeFilters", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  function render() {
    const target = document.createElement("div");
    document.body.appendChild(target);
    const onNodeTypesChange = vi.fn();
    const onEdgeTypesChange = vi.fn();
    const component = mount(GraphTypeFilters, {
      target,
      props: {
        nodeTypes: ["note", "tag", "note_or_unresolved"],
        edgeTypes: ["wikilink", "tag_link"],
        selectedNodeTypes: new Set(["note", "tag"]),
        selectedEdgeTypes: new Set(["wikilink"]),
        onNodeTypesChange,
        onEdgeTypesChange,
      },
    });
    return { target, component, onNodeTypesChange, onEdgeTypesChange };
  }

  it("renders readable node and edge labels with active checkbox state", () => {
    const { target, component } = render();

    expect(
      target.querySelector<HTMLInputElement>(
        'input[aria-label="Show note nodes"]',
      )?.checked,
    ).toBe(true);
    expect(
      target.querySelector<HTMLInputElement>(
        'input[aria-label="Show unresolved nodes"]',
      )?.checked,
    ).toBe(false);
    expect(
      target.querySelector<HTMLInputElement>(
        'input[aria-label="Show tag link edges"]',
      )?.checked,
    ).toBe(false);
    expect(target.textContent).toContain("unresolved");
    expect(target.textContent).toContain("tag link");

    unmount(component);
  });

  it("emits toggled node and edge type sets without mutating the incoming selections", async () => {
    const { target, component, onNodeTypesChange, onEdgeTypesChange } =
      render();

    target
      .querySelector<HTMLInputElement>('input[aria-label="Show note nodes"]')!
      .click();
    await tick();
    expect([...onNodeTypesChange.mock.calls[0][0]].sort()).toEqual(["tag"]);

    target
      .querySelector<HTMLInputElement>(
        'input[aria-label="Show unresolved nodes"]',
      )!
      .click();
    await tick();
    expect([...onNodeTypesChange.mock.calls[1][0]].sort()).toEqual([
      "note",
      "note_or_unresolved",
      "tag",
    ]);

    target
      .querySelector<HTMLInputElement>(
        'input[aria-label="Show tag link edges"]',
      )!
      .click();
    await tick();
    expect([...onEdgeTypesChange.mock.calls[0][0]].sort()).toEqual([
      "tag_link",
      "wikilink",
    ]);

    unmount(component);
  });
});
