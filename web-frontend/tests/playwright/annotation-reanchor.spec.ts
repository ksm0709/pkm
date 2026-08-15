import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("re-anchors an externally edited note annotation", async ({ page }) => {
  const vaultName = "main";
  const noteId = "annotation-reanchor-regression";
  const noteEndpoint = `/api/v1/vault/${vaultName}/notes/${noteId}`;
  const annotationsEndpoint = `/api/v1/vault/${vaultName}/annotations/note/${noteId}`;
  const originalAnnotation = {
    id: "playwright-reanchor",
    kind: "note",
    anchor: {
      kind: "text_quote",
      quote: "old phrase",
      occurrence: 0,
      selector_version: 1,
      prefix: "Before ",
      suffix: " after.",
      start: 7,
      end: 17,
      heading_path: [],
    },
    status: "active",
    reanchor: { confidence: 1, reason: "exact" },
    comment: "Keep this accurate",
    created_at: "",
    updated_at: "",
  };
  let patchPayload: Record<string, unknown> | null = null;

  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/vaults") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{ name: vaultName, path: "/tmp/main" }]),
      });
      return;
    }
    if (path === `${noteEndpoint}/neighbors`) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          note_id: noteId,
          outbound: [],
          inbound: [],
          semantic: [],
        }),
      });
      return;
    }
    if (path === annotationsEndpoint) {
      if (route.request().method() === "PATCH") {
        patchPayload = route.request().postDataJSON() as Record<
          string,
          unknown
        >;
        const updates = patchPayload.updates as Record<string, unknown>[];
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({
            version: 2,
            source_key: `note:${noteId}`,
            source: { kind: "note", note_id: noteId },
            annotation_revision: 8,
            storage_mode: "v2",
            source_revision: patchPayload.source_revision,
            annotations: [{ ...originalAnnotation, ...updates[0] }],
          }),
        });
        return;
      }
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          version: 2,
          source_key: `note:${noteId}`,
          source: { kind: "note", note_id: noteId },
          annotation_revision: 7,
          storage_mode: "v2",
          source_revision: "fnv1a:00000000",
          annotations: [originalAnnotation],
        }),
      });
      return;
    }
    if (path === noteEndpoint) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          note_id: noteId,
          title: "Re-anchor regression",
          body: "Before revised phrase after.",
          content_hash: `sha256:${"c".repeat(64)}`,
          frontmatter: {},
          created: null,
          updated: null,
          tags: [],
          importance: null,
        }),
      });
      return;
    }
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "not part of this regression fixture" }),
    });
  });

  await page.goto(`/${vaultName}/notes/${noteId}`);

  await expect(page.locator(".annotation-source-marked")).toHaveText(
    "revised phrase",
  );
  await expect
    .poll(() => patchPayload)
    .toMatchObject({
      base_revision: 7,
      base_note_revision: `sha256:${"c".repeat(64)}`,
      updates: [
        {
          id: "playwright-reanchor",
          status: "active",
          anchor: { quote: "revised phrase", selector_version: 1 },
          reanchor: { confidence: 0.9, reason: "context" },
        },
      ],
    });

  await page.getByRole("button", { name: /^Annotations \(1\)$/ }).click();
  await expect(page.locator(".annotation-status--active")).toHaveText("Active");

  const editTrigger = page.getByTestId("note-annotation-card-edit");
  await editTrigger.click();
  const dialog = page.getByRole("dialog", { name: "Edit annotation" });
  const textarea = dialog.getByRole("textbox", { name: "Annotation text" });
  const saveButton = dialog.getByRole("button", { name: "Save annotation" });
  await expect(textarea).toBeFocused();

  const accessibility = await new AxeBuilder({ page })
    .include(".annotate-dialog")
    .analyze();
  expect(accessibility.violations).toEqual([]);

  await page.keyboard.press("Shift+Tab");
  await expect(saveButton).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(textarea).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(editTrigger).toBeFocused();
});
