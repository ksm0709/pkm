import { expect, test, type Page, type Route } from "@playwright/test";

const vaultName = "alpha";
const otherVaultName = "beta";
const today = new Date().toISOString().slice(0, 10);
const longToken = "supercalifragilistic".repeat(18);
const projectPlanBody =
  "# Project Plan\n\nExpected rendered markdown body with #pkm and #work tags plus [highlight-only] bracket emphasis and [actual link](https://example.com).\n\n> Muted callout text for lower-priority context.\n\n- [ ] Draft task\n- [>] Active task\n- [x] Done task\n- [~] Paused task\n\nSee [[research-note]], [[research-note|aliased research]], and [[tag:pkm]].\n\nInline code `#pkm` and `[highlight-only]` remain plain.\n\n```md\n#work\n[highlight-only]\n- [ ] Code task stays literal\n[[research-note]]\n```";
const longContentBody = `# Long Content\n\n${longToken}\n\n\`${longToken}\`\n\n\`\`\`\n${longToken}\n\`\`\``;

const notes = [
  {
    note_id: "project-plan",
    title: "Project Plan",
    path: "notes/project-plan.md",
    tags: ["work", "pkm"],
    created_at: "2026-05-01",
    modified_at: "2026-05-01T10:00:00Z",
    description: "Project coordination summary and next actions.",
  },
  {
    note_id: "research-note",
    title: "Research Note",
    path: "notes/research-note.md",
    tags: ["pkm"],
    created_at: "2026-05-02",
    modified_at: "2026-05-03T12:00:00Z",
    description: "Research backlink context and related notes.",
  },
  {
    note_id: "long-content",
    title: "Long Content",
    path: "notes/long-content.md",
    tags: ["layout"],
    created_at: "2026-05-03",
    modified_at: "2026-05-02T12:00:00Z",
    description: "Long line wrapping stress note.",
  },
];

const graphFixture = {
  nodes: [
    {
      id: "project-plan",
      title: "Project Plan",
      type: "note",
      community: "planning",
      graph_tier: 1,
    },
    {
      id: "research-note",
      title: "Research Note",
      type: "note",
      community: "planning",
      graph_tier: 2,
    },
    { id: "tag:pkm", title: "#pkm", type: "tag", cluster: "tags" },
  ],
  links: [
    { source: "project-plan", target: "research-note", type: "wikilink" },
    { source: "project-plan", target: "tag:pkm", type: "has_tag" },
  ],
};

const betaNotes = [
  {
    note_id: "beta-home",
    title: "Beta Home",
    path: "notes/beta-home.md",
    tags: ["beta"],
    created_at: "2026-05-03",
  },
];

let notePutPayloads: { id: string; body: string }[] = [];

const noteBodies: Record<string, unknown> = {
  "project-plan": {
    note_id: "project-plan",
    title: "Project Plan",
    body: projectPlanBody,
    frontmatter: {},
    created: "2026-05-01",
    updated: "2026-05-02",
    tags: ["work", "pkm"],
    importance: 7,
  },
  "research-note": {
    note_id: "research-note",
    title: "Research Note",
    body: "# Research Note\n\nLinked neighbor content.",
    frontmatter: {},
    created: "2026-05-02",
    updated: null,
    tags: ["pkm"],
    importance: 5,
  },
  [today]: {
    note_id: today,
    title: "Today's Daily",
    body: `# ${today}\n\nDaily note for keyboard routing.\n\n## Logs\n- [09:15:00] Morning planning checkpoint.\n- [14:05] Afternoon implementation update.`,
    frontmatter: {},
    created: today,
    updated: null,
    tags: ["daily"],
    importance: 4,
  },
  [`${today}-standup`]: {
    note_id: `${today}-standup`,
    title: "Standup Subnote",
    body: "# Standup Subnote\n\nDaily subnote content.",
    frontmatter: {},
    created: today,
    updated: null,
    tags: ["daily", "meeting"],
    importance: 4,
  },
  "long-content": {
    note_id: "long-content",
    title: "Long Content",
    body: longContentBody,
    frontmatter: {},
    created: "2026-05-03",
    updated: null,
    tags: ["layout"],
    importance: 5,
  },
  "beta-home": {
    note_id: "beta-home",
    title: "Beta Home",
    body: "# Beta Home\n\nBeta vault landing content.",
    frontmatter: {},
    created: "2026-05-03",
    updated: null,
    tags: ["beta"],
    importance: 5,
  },
};

test.describe("generated routing and event contracts", () => {
  test.beforeEach(async ({ page }) => {
    resetMockNotes();
    notePutPayloads = [];
    await mockPkmApi(page);
  });

  test("root, vault, note, and neighbor routes render their expected states", async ({
    page,
  }) => {
    await page.addInitScript(() =>
      localStorage.setItem("pkm.lastVault", "alpha"),
    );
    await page.goto("/");

    await expect(page).toHaveURL(new RegExp(`/${vaultName}/logger$`));
    await expectTopbar(page, vaultName, "logger");
    await expect(page.getByRole("heading", { name: "Logger" })).toHaveCount(0);
    await expect(page.getByText("Morning planning checkpoint.")).toBeVisible();

    await page.goto(`/${vaultName}`);
    await expectTopbar(page, vaultName, "notes");
    await expect(page.getByRole("heading", { name: vaultName })).toHaveCount(0);
    await expect(page.getByText("3 notes")).toBeVisible();
    await expect(
      page.getByRole("link", { name: /Project Plan/ }),
    ).toBeVisible();
    await expect(page.locator(".note-title")).toHaveText([
      "Research Note",
      "Long Content",
      "Project Plan",
    ]);
    await expect(page.locator(".note-description")).toHaveText([
      "Research backlink context and related notes.",
      "Long line wrapping stress note.",
      "Project coordination summary and next actions.",
    ]);
    await expect(
      page.locator(".note-description", { hasText: "project-plan.md" }),
    ).toHaveCount(0);
    await expect(
      page.getByLabel("Tag summary").getByText("#pkm"),
    ).toBeVisible();

    await page.getByRole("link", { name: /Project Plan/ }).click();
    await expect(page).toHaveURL(
      new RegExp(`/${vaultName}/notes/project-plan$`),
    );
    await expectNoteHeaderId(page, "project-plan");
    await expect(
      page.getByText(/Expected rendered markdown body/),
    ).toBeVisible();
    await expect(page.getByText("SIGNAL ANALYZER")).toBeVisible();

    await page.getByRole("button", { name: "Edit" }).click();
    await expect(page.locator(".cm-editor")).toBeVisible();

    await page.getByRole("link", { name: /Research Note/ }).click();
    await expect(page).toHaveURL(
      new RegExp(`/${vaultName}/notes/research-note$`),
    );
    await expectNoteHeaderId(page, "research-note");
  });

  test("note content scroll keeps topbar and navigation drawer fixed", async ({
    page,
  }) => {
    noteBodies["long-content"] = {
      ...(noteBodies["long-content"] as Record<string, unknown>),
      body: `# Long Content\n\n${Array.from(
        { length: 90 },
        (_, index) =>
          `Scrollable note paragraph ${index + 1}. ${longToken.slice(0, 80)}`,
      ).join("\n\n")}`,
    };

    await page.addInitScript(() =>
      localStorage.setItem("pkm.appNavOpen", "true"),
    );
    await page.goto(`/${vaultName}/notes/long-content`);
    await expect(page.locator(".app-nav-drawer.open")).toBeVisible();
    const notesNavItem = page.locator(".app-nav-drawer.open .nav-item", {
      hasText: "Notes",
    });
    await expect(notesNavItem).toBeVisible();

    const topbarBefore = await page.locator(".topbar").boundingBox();
    const drawerBefore = await page.locator(".app-nav-drawer").boundingBox();
    expect(topbarBefore).not.toBeNull();
    expect(drawerBefore).not.toBeNull();

    const scrollMetrics = await page
      .locator(".vault-content")
      .evaluate((el) => {
        el.scrollTop = el.scrollHeight;
        return {
          scrollTop: el.scrollTop,
          scrollHeight: el.scrollHeight,
          clientHeight: el.clientHeight,
          pageScrollY: window.scrollY,
        };
      });

    expect(scrollMetrics.scrollHeight).toBeGreaterThan(
      scrollMetrics.clientHeight,
    );
    expect(scrollMetrics.scrollTop).toBeGreaterThan(0);
    expect(scrollMetrics.pageScrollY).toBe(0);
    await expect(notesNavItem).toBeVisible();

    const topbarAfter = await page.locator(".topbar").boundingBox();
    const drawerAfter = await page.locator(".app-nav-drawer").boundingBox();
    expect(Math.round(topbarAfter?.y ?? -1)).toBe(
      Math.round(topbarBefore?.y ?? -2),
    );
    expect(Math.round(drawerAfter?.y ?? -1)).toBe(
      Math.round(drawerBefore?.y ?? -2),
    );
  });

  test("read mode wikilinks render as note links without linking code blocks", async ({
    page,
  }) => {
    await page.goto(`/${vaultName}/notes/project-plan`);

    const noteBody = page.locator(".note-body");
    await expect(
      noteBody.getByText(/Expected rendered markdown body/),
    ).toBeVisible();

    await expect(
      noteBody.getByRole("link", { name: "research-note" }),
    ).toHaveAttribute("href", `/${vaultName}/notes/research-note`);
    await expect(
      noteBody.getByRole("link", { name: "aliased research" }),
    ).toHaveAttribute("href", `/${vaultName}/notes/research-note`);
    await expect(
      noteBody.getByRole("link", { name: "tag:pkm" }),
    ).toHaveAttribute("href", `/${vaultName}/notes/tag%3Apkm`);
    await expect(noteBody.locator("pre code")).toContainText(
      "[[research-note]]",
    );
    await expect(noteBody.locator("pre code a")).toHaveCount(0);

    await noteBody.getByRole("link", { name: "aliased research" }).click();
    await expect(page).toHaveURL(
      new RegExp(`/${vaultName}/notes/research-note$`),
    );
    await expectNoteHeaderId(page, "research-note");
  });

  test("unresolved note links auto-create a blank note in the app", async ({
    page,
  }) => {
    await page.goto(`/${vaultName}/notes/unresolved-auto-note`);

    await expect(page).toHaveURL(
      new RegExp(`/${vaultName}/notes/unresolved-auto-note$`),
    );
    await expectNoteHeaderId(page, "unresolved-auto-note");
    await expect(page.getByText("Note not found.")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Edit" })).toBeVisible();
    expect(noteBodies["unresolved-auto-note"]).toMatchObject({
      note_id: "unresolved-auto-note",
      title: "unresolved auto note",
      body: "",
    });
  });

  test("tag wikilink route renders tag hub neighbors when no tag note file exists", async ({
    page,
  }) => {
    await page.goto(`/${vaultName}/notes/project-plan`);

    await page
      .locator(".note-body")
      .getByRole("link", { name: "tag:pkm" })
      .click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/notes/tag%3Apkm$`));
    await expectTopbar(page, vaultName, "tag:pkm");
    await expect(page.getByRole("heading", { name: "#pkm" })).toHaveCount(0);
    await expect(page.getByText("Tag note not found.")).toBeVisible();
    await expect(page.getByText("SIGNAL ANALYZER")).toBeVisible();
    await expect(page.getByText("INBOUND")).toBeVisible();
    await expect(
      page.getByRole("link", { name: /Project Plan/ }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: /Research Note/ }),
    ).toBeVisible();
    await expect(
      page.getByText("Project coordination summary and next actions."),
    ).toBeVisible();
    await expect(
      page.getByText("Research backlink context and related notes."),
    ).toBeVisible();
    await expect(page.getByText("project-plan.md")).toHaveCount(0);
    await expect(page.getByText("research-note.md")).toHaveCount(0);
    await expectNoMissingPage(page, { allowTagNotFound: true });
  });

  test("read mode inline syntax renders tag chips, bracket highlights, and muted callouts", async ({
    page,
  }) => {
    await page.goto(`/${vaultName}/notes/project-plan`);

    const noteBody = page.locator(".note-body");
    const pkmChip = noteBody.locator('a.note-tag-chip[data-tag="pkm"]').first();
    const workChip = noteBody
      .locator('a.note-tag-chip[data-tag="work"]')
      .first();

    await expect(pkmChip).toHaveAttribute(
      "href",
      `/${vaultName}/notes/tag%3Apkm`,
    );
    await expect(workChip).toHaveAttribute(
      "href",
      `/${vaultName}/notes/tag%3Awork`,
    );
    await expect(pkmChip).toBeVisible();
    await expect(workChip).toBeVisible();
    await expect(pkmChip).toHaveCSS("border-radius", /999/);

    const headerPkmChip = page.locator(
      '.note-tags a.note-tag-chip[data-tag="pkm"]',
    );
    const headerWorkChip = page.locator(
      '.note-tags a.note-tag-chip[data-tag="work"]',
    );
    await expect(headerPkmChip).toHaveAttribute(
      "href",
      `/${vaultName}/notes/tag%3Apkm`,
    );
    await expect(headerWorkChip).toHaveAttribute(
      "href",
      `/${vaultName}/notes/tag%3Awork`,
    );
    await expect(headerPkmChip).toBeVisible();
    await expect(headerWorkChip).toBeVisible();

    const chipHues = await Promise.all([
      pkmChip.evaluate((el) =>
        getComputedStyle(el).getPropertyValue("--tag-hue"),
      ),
      workChip.evaluate((el) =>
        getComputedStyle(el).getPropertyValue("--tag-hue"),
      ),
    ]);
    expect(chipHues[0]).not.toBe(chipHues[1]);

    await expect(noteBody.locator("code a.note-tag-chip")).toHaveCount(0);
    await expect(noteBody.locator("pre a.note-tag-chip")).toHaveCount(0);
    await expect(noteBody.locator("code", { hasText: "#pkm" })).toBeVisible();
    await expect(noteBody.locator("pre code")).toContainText("#work");

    const bracketHighlight = noteBody.locator("span.note-bracket-highlight", {
      hasText: "[highlight-only]",
    });
    await expect(bracketHighlight).toBeVisible();
    await expect(
      noteBody.locator("a", { hasText: "[highlight-only]" }),
    ).toHaveCount(0);
    await expect(
      noteBody.locator("a", { hasText: "actual link" }),
    ).toHaveAttribute("href", "https://example.com");
    await expect(
      noteBody.locator("code span.note-bracket-highlight"),
    ).toHaveCount(0);
    await expect(
      noteBody.locator("pre span.note-bracket-highlight"),
    ).toHaveCount(0);
    await expect(
      noteBody.locator("p code", { hasText: /^\[highlight-only\]$/ }),
    ).toBeVisible();
    await expect(noteBody.locator("pre code")).toContainText(
      "[highlight-only]",
    );

    const calloutMetrics = await noteBody
      .locator("blockquote")
      .evaluate((el) => {
        const blockquoteStyle = getComputedStyle(el);
        const paragraph = document.querySelector(".note-body p");
        const paragraphStyle = paragraph ? getComputedStyle(paragraph) : null;
        return {
          backgroundColor: blockquoteStyle.backgroundColor,
          color: blockquoteStyle.color,
          paragraphColor: paragraphStyle?.color ?? "",
        };
      });

    expect(calloutMetrics.backgroundColor).not.toBe("rgba(0, 0, 0, 0)");
    expect(calloutMetrics.color).not.toBe(calloutMetrics.paragraphColor);
  });

  test("light theme keeps topbar, tag chips, and callouts readable", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      localStorage.setItem("pkm.theme", "light");
      document.documentElement.dataset.theme = "light";
    });
    await page.goto(`/${vaultName}/notes/project-plan`);
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await expect(page.locator(".topbar")).toBeVisible();
    await expect(
      page.locator(".note-body a.note-tag-chip").first(),
    ).toBeVisible();
    await expect(page.locator(".note-body blockquote")).toBeVisible();

    const themeMetrics = await readThemeMetrics(page);
    expect(
      themeMetrics.topbar.bgLum,
      "light theme topbar background",
    ).toBeGreaterThan(0.75);
    expect(
      themeMetrics.tag.contrast,
      "light theme tag chip contrast",
    ).toBeGreaterThanOrEqual(4.5);
    expect(
      themeMetrics.tag.fgLum,
      "light theme tag chip text is dark",
    ).toBeLessThan(0.35);
    expect(
      themeMetrics.callout.bgLum,
      "light theme callout background",
    ).toBeGreaterThan(0.7);
    expect(
      themeMetrics.callout.contrast,
      "light theme callout contrast",
    ).toBeGreaterThanOrEqual(4.5);
  });

  test("read mode task states render and cycle through saved markdown states", async ({
    page,
  }) => {
    await page.goto(`/${vaultName}/notes/project-plan`);

    const noteBody = page.locator(".note-body");
    const taskStates = noteBody.locator("button.note-task-state");
    await expect(taskStates).toHaveCount(4);
    await expect(taskStates.nth(0)).toHaveText("");
    await expect(taskStates.nth(1)).toHaveText(">");
    await expect(taskStates.nth(2)).toHaveText("✓");
    await expect(taskStates.nth(3)).toHaveText("~");
    await expect(taskStates.nth(0)).toHaveAttribute(
      "aria-label",
      "Task status todo",
    );
    await expect(taskStates.nth(1)).toHaveAttribute(
      "aria-label",
      "Task status in progress",
    );
    await expect(taskStates.nth(2)).toHaveAttribute(
      "aria-label",
      "Task status done",
    );
    await expect(taskStates.nth(3)).toHaveAttribute(
      "aria-label",
      "Task status canceled",
    );
    const taskStateStyles = await taskStates.evaluateAll((buttons) =>
      buttons.map((button) => {
        const style = getComputedStyle(button);
        const rect = button.getBoundingClientRect();
        return {
          width: Math.round(rect.width),
          height: Math.round(rect.height),
          borderRadius: style.borderRadius,
          backgroundColor: style.backgroundColor,
        };
      }),
    );
    for (const style of taskStateStyles) {
      expect(Math.abs(style.width - style.height)).toBeLessThanOrEqual(1);
      expect(style.borderRadius).not.toMatch(/999/);
    }
    expect(taskStateStyles[0].backgroundColor).toMatch(/rgb\(.*\)/);
    expect(taskStateStyles[0].backgroundColor).not.toBe(
      taskStateStyles[1].backgroundColor,
    );
    expect(taskStateStyles[1].backgroundColor).not.toBe(
      taskStateStyles[2].backgroundColor,
    );
    expect(taskStateStyles[2].backgroundColor).not.toBe(
      taskStateStyles[3].backgroundColor,
    );
    await expect(noteBody.getByText("Draft task")).toBeVisible();
    await expect(noteBody.locator("pre button.note-task-state")).toHaveCount(0);
    await expect(noteBody.locator("pre code")).toContainText(
      "- [ ] Code task stays literal",
    );

    await taskStates.nth(0).click();
    await expect(taskStates.nth(0)).toHaveText(">");
    expect(noteBodyFor("project-plan")).toContain("- [>] Draft task");

    await taskStates.nth(0).click();
    await expect(taskStates.nth(0)).toHaveText("✓");
    expect(noteBodyFor("project-plan")).toContain("- [x] Draft task");

    await taskStates.nth(3).click();
    await expect(taskStates.nth(3)).toHaveText("");
    expect(noteBodyFor("project-plan")).toContain("- [ ] Paused task");
  });

  test("drawer, command palette, daily keyboard routing, and nav routes behave consistently", async ({
    page,
  }) => {
    await page.goto(`/${vaultName}`);
    await page.waitForLoadState("networkidle").catch(() => {});
    await expect(
      page.getByRole("button", { name: "Open navigation drawer" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Open navigation drawer" }).click();
    await expect(
      page.locator('aside[aria-label="App navigation"]'),
    ).toHaveAttribute("aria-hidden", "false");

    await page.keyboard.press("Escape");
    await expect(
      page.locator('aside[aria-label="App navigation"]'),
    ).toHaveAttribute("aria-hidden", "true");

    await page.getByRole("button", { name: "Open navigation drawer" }).click();
    await page.getByRole("button", { name: "Search" }).click();
    await expectCommandPaletteFocused(page);
    await page.keyboard.press("Escape");

    await page.keyboard.press("Control+K");
    await expectCommandPaletteFocused(page);
    await page.getByRole("option", { name: /Jump to note/ }).click();
    await expectCommandPaletteFocused(page);
    await page.locator(".cmdk-input").fill("project");
    await expect(
      page.getByRole("option", { name: /Project Plan/ }),
    ).toBeVisible();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(
      new RegExp(`/${vaultName}/notes/project-plan$`),
    );

    await page.getByRole("button", { name: "Open navigation drawer" }).click();
    await page.getByRole("button", { name: "Daily" }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/daily$`));
    await expectTopbar(page, vaultName, "daily");
    await expect(page.getByRole("heading", { name: "Daily" })).toHaveCount(0);
    await expect(
      page.getByRole("link", { name: today, exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: /Standup Subnote/ }),
    ).toBeVisible();
    await expect(page.getByText("Today entry")).toHaveCount(0);
    await expect(page.getByText(/todo open/)).toHaveCount(0);
    await page.getByRole("link", { name: /Standup Subnote/ }).click();
    await expect(page).toHaveURL(
      new RegExp(`/${vaultName}/notes/${today}-standup$`),
    );
    await expectNoteHeaderId(page, `${today}-standup`);
    await expect(page.getByText("Daily subnote content.")).toBeVisible();

    await page.goto(`/${vaultName}/daily`);
    await page.getByRole("link", { name: today }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/notes/${today}$`));
    await expectNoteHeaderId(page, today);
    await expect(
      page.getByText("Daily note for keyboard routing."),
    ).toBeVisible();

    await page.goto(`/${vaultName}/daily`);
    await page.waitForLoadState("networkidle").catch(() => {});
    await expectTopbar(page, vaultName, "daily");
    await expect(page.getByRole("heading", { name: "Daily" })).toHaveCount(0);

    await page.getByRole("button", { name: "Open navigation drawer" }).click();
    await expect(
      page.locator('aside[aria-label="App navigation"]'),
    ).toHaveAttribute("aria-hidden", "false");
    await page.getByRole("button", { name: "Tags" }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/tags$`));
    await expect(page.getByText("3 tags")).toBeVisible();
    await page.getByRole("button", { name: "Open navigation drawer" }).click();
    await page.getByRole("button", { name: "Graph" }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/graph$`));
    await expect(page.getByText("3 nodes")).toBeVisible();

    await page.evaluate(() => {
      if (document.activeElement instanceof HTMLElement) {
        document.activeElement.blur();
      }
    });
    await expect
      .poll(() => page.evaluate(() => Boolean((window as any).__pkmNav)))
      .toBe(true);
    await page.keyboard.press("g");
    await page.keyboard.press("d");
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/notes/${today}$`));
    await expectNoteHeaderId(page, today);
  });

  test("tags page sorts tags by reference count and opens tag notes", async ({
    page,
  }) => {
    await page.goto(`/${vaultName}/tags`);
    await page.waitForLoadState("networkidle").catch(() => {});

    await expectTopbar(page, vaultName, "tags");
    await expect(page.getByText("3 tags")).toBeVisible();
    await expect(page.locator(".tag-name")).toHaveText([
      "#pkm",
      "#layout",
      "#work",
    ]);
    await expect(page.locator(".tag-count")).toHaveText(["2", "1", "1"]);

    await page.getByRole("link", { name: /#pkm/ }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/notes/tag%3Apkm$`));
    await expectTopbar(page, vaultName, "tag:pkm");
    await expect(page.getByText("2 linked notes")).toBeVisible();
  });

  test("logger route renders today logs and appends new timestamped entries", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 720 });
    await page.goto(`/${vaultName}`);
    await page.waitForLoadState("networkidle").catch(() => {});
    await page.getByRole("button", { name: "Open navigation drawer" }).click();
    await expect(
      page.locator('aside[aria-label="App navigation"]'),
    ).toHaveAttribute("aria-hidden", "false");
    await page
      .locator('button[aria-label="Logger"]')
      .evaluate((el) => (el as HTMLElement).click());

    await expect(page).toHaveURL(new RegExp(`/${vaultName}/logger$`));
    await expectTopbar(page, vaultName, "logger");
    await expect(page.getByRole("heading", { name: "Logger" })).toHaveCount(0);
    await expect(page.getByText(today)).toBeVisible();
    await expect(page.getByText("09:15:00")).toBeVisible();
    await expect(page.getByText("Morning planning checkpoint.")).toBeVisible();
    await expect(page.getByText("09:00")).toBeVisible();
    await expect(page.getByText("14:05")).toBeVisible();
    await expect(
      page.getByText("Afternoon implementation update."),
    ).toBeVisible();
    await expect(page.getByText("14:00")).toBeVisible();

    const input = page.getByPlaceholder(/Add log/);
    const addLogButton = page.getByRole("button", { name: "Add log" });
    await expect(addLogButton).toHaveText("⌘↵");
    const loggerInputBox = await page.locator(".logger-input").boundingBox();
    expect(loggerInputBox).not.toBeNull();
    const loggerViewportWidth = await page.evaluate(() => window.innerWidth);
    expect(Math.abs((loggerInputBox?.x ?? -1) - 32)).toBeLessThanOrEqual(1);
    expect(
      Math.abs(
        (loggerInputBox?.x ?? 0) +
          (loggerInputBox?.width ?? 0) -
          (loggerViewportWidth - 32),
      ),
    ).toBeLessThanOrEqual(1);
    expect(
      Math.abs((loggerInputBox?.y ?? 0) + (loggerInputBox?.height ?? 0) - 720),
    ).toBeLessThanOrEqual(2);
    const loggerTextareaStyle = await input.evaluate((el) => {
      const style = getComputedStyle(el as HTMLElement);
      return {
        borderTopWidth: style.borderTopWidth,
        borderRightWidth: style.borderRightWidth,
        borderBottomWidth: style.borderBottomWidth,
        borderLeftWidth: style.borderLeftWidth,
      };
    });
    expect(loggerTextareaStyle).toEqual({
      borderTopWidth: "0px",
      borderRightWidth: "0px",
      borderBottomWidth: "0px",
      borderLeftWidth: "0px",
    });
    const addLogButtonStyle = await addLogButton.evaluate((el) => {
      const style = getComputedStyle(el as HTMLElement);
      return {
        borderWidth: style.borderWidth,
        backgroundColor: style.backgroundColor,
      };
    });
    expect(addLogButtonStyle.borderWidth).toBe("0px");
    await input.fill("Shipped logger UI");
    await addLogButton.click();

    await expect(page.getByText("16:45:12")).toBeVisible();
    await expect(page.getByText("Shipped logger UI")).toBeVisible();
    await expect(input).toHaveValue("");
    await expectNoMissingPage(page);

    await page.goto(`/${vaultName}/notes/project-plan`);
    await page.waitForLoadState("networkidle").catch(() => {});
    await page.getByLabel("Open vault logger").click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/logger$`));
    await expectTopbar(page, vaultName, "logger");
    await expect(page.getByRole("heading", { name: "Logger" })).toHaveCount(0);
  });

  test("logger input suggests notes and tags while typing inline wikilinks", async ({
    page,
  }) => {
    await page.goto(`/${vaultName}/logger`);

    const input = page.locator(".logger-textarea");
    await input.fill("Captured [[res");
    const suggest = page.getByRole("listbox", { name: "Inline suggestions" });
    await expect(suggest.getByRole("option").first()).toContainText(
      "research-note",
    );
    await input.press("Enter");
    await expect(input).toHaveValue("Captured [[research-note]]");

    await input.fill("Captured #wo");
    await expect(suggest.getByRole("option", { name: /#work/ })).toBeVisible();
    await input.press("Enter");
    await expect(input).toHaveValue("Captured #work");
  });

  test("note body wraps long content within the viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 900 });
    await page.goto(`/${vaultName}/notes/long-content`);

    await expectNoteHeaderId(page, "long-content");
    await expect(page.getByText(longToken).first()).toBeVisible();

    const bodyMetrics = await page.locator(".note-body").evaluate((el) => ({
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
      pageScrollWidth: document.documentElement.scrollWidth,
      pageClientWidth: document.documentElement.clientWidth,
    }));

    expect(bodyMetrics.scrollWidth).toBeLessThanOrEqual(
      bodyMetrics.clientWidth + 1,
    );
    expect(bodyMetrics.pageScrollWidth).toBeLessThanOrEqual(
      bodyMetrics.pageClientWidth + 1,
    );
  });

  test("note reading surface removes side rules and uses practical page width", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(`/${vaultName}/notes/project-plan`);

    await expectNoteHeaderId(page, "project-plan");

    const metrics = await page.locator(".note-body").evaluate((el) => {
      const bodyStyle = getComputedStyle(el);
      const header = document.querySelector(".note-header");
      const headerStyle = header ? getComputedStyle(header) : null;
      const rect = el.getBoundingClientRect();
      return {
        width: rect.width,
        borderLeftWidth: bodyStyle.borderLeftWidth,
        borderRightWidth: bodyStyle.borderRightWidth,
        headerBorderLeftWidth: headerStyle?.borderLeftWidth ?? "",
      };
    });

    expect(metrics.width).toBeGreaterThan(900);
    expect(metrics.borderLeftWidth).toBe("0px");
    expect(metrics.borderRightWidth).toBe("0px");
    expect(metrics.headerBorderLeftWidth).toBe("0px");
  });

  test("note edit mode suggests notes and tags while typing inline wikilinks", async ({
    page,
  }) => {
    await page.goto(`/${vaultName}/notes/project-plan`);
    await page.getByRole("button", { name: "Edit" }).click();
    const editor = page.locator(".cm-content");
    await editor.click();
    await page.keyboard.press("i");
    await page.keyboard.press(
      process.platform === "darwin" ? "Meta+A" : "Control+A",
    );
    await page.keyboard.press("Backspace");
    await page.keyboard.type("See [[res");

    await expect(page.getByRole("option").first()).toContainText(
      "research-note",
    );
    await page.getByRole("option").first().click();
    await expect(editor).toContainText("See [[research-note]]");

    await page.keyboard.press(
      process.platform === "darwin" ? "Meta+A" : "Control+A",
    );
    await page.keyboard.press("Backspace");
    await page.keyboard.type("Tag #pk");
    await expect(page.getByRole("option", { name: /#pkm/ })).toBeVisible();
    await page.getByRole("option", { name: /#pkm/ }).click();
    await expect(editor).toContainText("Tag #pkm");
  });

  test("note edit mode saves normal and daily notes with button and keyboard shortcuts", async ({
    page,
  }) => {
    const modifier = process.platform === "darwin" ? "Meta" : "Control";

    await page.goto(`/${vaultName}/notes/project-plan`);
    await page.getByRole("button", { name: "Edit" }).click();
    await page.getByRole("button", { name: "Plain" }).click();

    const editor = page.locator(".cm-content");
    await editor.click();
    await page.keyboard.press(`${modifier}+A`);
    await page.keyboard.type("Saved from plain mode.");

    const saveButton = page.getByRole("button", { name: "Save note" });
    await expect(saveButton).toBeEnabled();
    await expect(page.getByText("Unsaved", { exact: true })).toBeVisible();
    await saveButton.click();

    await expect(page.getByText("Saved", { exact: true })).toBeVisible();
    expect(notePutPayloads.at(-1)).toEqual({
      id: "project-plan",
      body: "Saved from plain mode.",
    });
    await page.getByRole("button", { name: "Read" }).click();
    await expect(page.getByText("Saved from plain mode.")).toBeVisible();

    await page.goto(`/${vaultName}/notes/${today}`);
    await page.getByRole("button", { name: "Edit" }).click();
    await page.getByRole("button", { name: "Plain" }).click();
    await page.locator(".cm-content").click();
    await page.keyboard.press(`${modifier}+A`);
    await page.keyboard.type("Daily saved with keyboard shortcut.");
    await page.keyboard.press(`${modifier}+S`);

    await expect(page.getByText("Saved", { exact: true })).toBeVisible();
    expect(notePutPayloads.at(-1)).toEqual({
      id: today,
      body: "Daily saved with keyboard shortcut.",
    });
  });

  test("note editor supports vim visual selection and plain-mode shortcut isolation", async ({
    page,
  }) => {
    await page.goto(`/${vaultName}/notes/project-plan`);
    await page.getByRole("button", { name: "Edit" }).click();

    const editor = page.locator(".cm-content");
    await editor.click();
    await page.keyboard.press("Escape");
    await page.keyboard.press("v");
    await page.keyboard.press("l");
    await page.keyboard.press("l");
    await page.keyboard.press("j");
    await expect
      .poll(() =>
        page.evaluate(
          () => (window.getSelection()?.toString() ?? "").length > 0,
        ),
      )
      .toBe(true);

    await page.getByRole("button", { name: "Plain" }).click();
    await page.locator(".cm-content").click();
    await page.keyboard.press(
      process.platform === "darwin" ? "Meta+K" : "Control+K",
    );
    await expect(
      page.getByRole("dialog", { name: "Command palette" }),
    ).toHaveCount(0);
    await page.keyboard.press("g");
    await page.keyboard.press("d");
    await expect(page).toHaveURL(
      new RegExp(`/${vaultName}/notes/project-plan$`),
    );
  });

  test("command palette static commands never route to missing pages and render target content", async ({
    page,
  }) => {
    await page.goto(`/${vaultName}`);
    await page.waitForLoadState("networkidle").catch(() => {});

    await openCommandPalette(page);
    await page.getByRole("option", { name: /Jump to note/ }).click();
    await expectCommandPaletteFocused(page);
    await page.keyboard.press("Escape");

    await openCommandPalette(page);
    await page.getByRole("option", { name: /Open today's daily note/ }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/notes/${today}$`));
    await expectNoteHeaderId(page, today);
    await expectNoMissingPage(page);

    await page.goto(`/${vaultName}`);
    await openCommandPalette(page);
    await page.getByRole("option", { name: /Switch vault/ }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}$`));
    await expectTopbar(page, vaultName, "notes");
    await expect(
      page.locator('[role="dialog"][aria-label="Command palette"]'),
    ).toBeVisible();
    await expect(
      page.getByRole("option", { name: new RegExp(`^${vaultName}`) }),
    ).toBeVisible();
    await expect(
      page.getByRole("option", { name: new RegExp(`^${otherVaultName}`) }),
    ).toBeVisible();
    await page
      .getByRole("option", { name: new RegExp(`^${otherVaultName}`) })
      .click();
    await expect(page).toHaveURL(new RegExp(`/${otherVaultName}/logger$`));
    await expectTopbar(page, otherVaultName, "logger");
    await expect(page.getByRole("heading", { name: "Logger" })).toHaveCount(0);
    await expect(page.getByText("Morning planning checkpoint.")).toBeVisible();
    await expectNoMissingPage(page);

    await page.goto(`/${vaultName}`);
    await page.evaluate(() => localStorage.removeItem("pkm.theme"));
    await openCommandPalette(page);
    await page.getByRole("option", { name: /Toggle theme/ }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await expect(page).toHaveURL(new RegExp(`/${vaultName}$`));
    await expectNoMissingPage(page);

    await openCommandPalette(page);
    await expect(
      page.getByRole("option", { name: /Open logger/ }),
    ).toBeVisible();
    await page.getByRole("option", { name: /Open logger/ }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/logger$`));
    await expectTopbar(page, vaultName, "logger");
    await expect(page.getByRole("heading", { name: "Logger" })).toHaveCount(0);
    await expect(page.getByText("Morning planning checkpoint.")).toBeVisible();
    await expectNoMissingPage(page);

    await page.goto(`/${vaultName}`);
    await page.getByRole("button", { name: "Open navigation drawer" }).click();
    await expect(page.locator('button[aria-label="Graph"]')).toBeVisible();

    await openCommandPalette(page);
    await page.getByRole("option", { name: /Open graph/ }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/graph$`));
    await expect(page.getByText("3 nodes")).toBeVisible();
    await expect(
      page.locator('[role="dialog"][aria-label="Command palette"]'),
    ).toBeHidden();
    await expectNoMissingPage(page);
  });

  test("command palette search, tag search, and empty states render deterministic content", async ({
    page,
  }) => {
    await page.goto(`/${vaultName}`);
    await page.waitForLoadState("networkidle").catch(() => {});

    await openSearchPalette(page);
    await page.locator(".cmdk-input").fill("research");
    await expect(
      page.getByRole("option", { name: /Research Note/ }),
    ).toBeVisible();
    await page.getByRole("option", { name: /Research Note/ }).click();
    await expect(page).toHaveURL(
      new RegExp(`/${vaultName}/notes/research-note$`),
    );
    await expectNoteHeaderId(page, "research-note");
    await expect(page.getByText("Linked neighbor content.")).toBeVisible();
    await expectNoMissingPage(page);

    await page.goto(`/${vaultName}`);
    await openSearchPalette(page);
    await page.locator(".cmdk-input").fill("neighbor");
    await expect(
      page.getByRole("option", { name: /Research Note/ }),
    ).toBeVisible();
    await expect(page.getByText("Linked neighbor content.")).toBeVisible();
    await page.getByRole("option", { name: /Research Note/ }).click();
    await expect(page).toHaveURL(
      new RegExp(`/${vaultName}/notes/research-note$`),
    );
    await expect(page.getByText("Linked neighbor content.")).toBeVisible();
    await expectNoMissingPage(page);

    await page.goto(`/${vaultName}`);
    await openSearchPalette(page);
    await page.locator(".cmdk-input").fill("#work");
    await expect(
      page.getByRole("option", { name: /Project Plan/ }),
    ).toBeVisible();
    await page.getByRole("option", { name: /Project Plan/ }).click();
    await expect(page).toHaveURL(
      new RegExp(`/${vaultName}/notes/project-plan$`),
    );
    await expect(
      page.getByText(/Expected rendered markdown body/),
    ).toBeVisible();
    await expectNoMissingPage(page);

    await page.goto(`/${vaultName}`);
    await openSearchPalette(page);
    await page.locator(".cmdk-input").fill("#missing-tag");
    await expect(page.getByText("No matches.")).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}$`));
    await expectNoMissingPage(page);
  });
});

async function mockPkmApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = decodeURIComponent(url.pathname);

    if (path === "/api/v1/vaults") {
      await json(route, [
        { name: vaultName, path: "/tmp/alpha", is_default: false },
        { name: otherVaultName, path: "/tmp/beta", is_default: true },
      ]);
      return;
    }

    const listMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/notes$/);
    if (listMatch) {
      await json(route, listMatch[1] === otherVaultName ? betaNotes : notes);
      return;
    }

    const dailyMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/daily$/);
    if (dailyMatch) {
      await json(route, [
        {
          note_id: today,
          date: today,
          kind: "daily",
          title: "Today's Daily",
          todo_count: 1,
          snippet: "Today entry",
        },
        {
          note_id: `${today}-standup`,
          date: today,
          kind: "subnote",
          title: "Standup Subnote",
          todo_count: 0,
          snippet: "Daily subnote content.",
        },
        {
          note_id: "2026-05-02",
          date: "2026-05-02",
          kind: "daily",
          title: "Yesterday",
          todo_count: 0,
          snippet: "Yesterday entry",
        },
      ]);
      return;
    }

    const configsMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/configs$/);
    if (configsMatch && route.request().method() === "GET") {
      await json(route, configPayload());
      return;
    }

    const dailyDateMatch = path.match(
      /^\/api\/v1\/vault\/([^/]+)\/daily\/(\d{4}-\d{2}-\d{2})$/,
    );
    if (dailyDateMatch) {
      const note = noteBodies[dailyDateMatch[2]];
      if (note) {
        await json(route, note);
      } else {
        await route.fulfill({ status: 404, body: "not found" });
      }
      return;
    }

    const searchMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/search$/);
    if (searchMatch) {
      const vaultNotes = searchMatch[1] === otherVaultName ? betaNotes : notes;
      const q = url.searchParams.get("q")?.toLowerCase() ?? "";
      if (!q) {
        await route.fulfill({ status: 400, body: "missing q" });
        return;
      }
      const results = vaultNotes
        .filter((note) => {
          const body = noteBodyFor(note.note_id);
          return [note.note_id, note.title, note.path, ...note.tags, body].some(
            (value) => value.toLowerCase().includes(q),
          );
        })
        .map((note) => {
          const body = noteBodyFor(note.note_id);
          return {
            note_id: note.note_id,
            title: note.title,
            snippet: snippetFor(q, body) || note.path,
            score: 0.99,
          };
        });
      await json(route, {
        query: q,
        count: results.length,
        results,
      });
      return;
    }

    const tagMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/tags\/search$/);
    if (tagMatch) {
      const vaultNotes = tagMatch[1] === otherVaultName ? betaNotes : notes;
      const pattern = url.searchParams.get("pattern")?.toLowerCase() ?? "";
      const results = vaultNotes.filter((note) =>
        note.tags.some((tag) => tag.toLowerCase().includes(pattern)),
      );
      await json(route, {
        pattern,
        mode: "glob",
        count: results.length,
        results,
      });
      return;
    }

    const tagListMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/tags$/);
    if (tagListMatch) {
      const vaultNotes = tagListMatch[1] === otherVaultName ? betaNotes : notes;
      const counts = new Map<string, number>();
      for (const note of vaultNotes) {
        for (const tag of note.tags) {
          counts.set(tag, (counts.get(tag) ?? 0) + 1);
        }
      }
      await json(route, {
        tags: Array.from(counts.entries()).map(([tag, count]) => ({
          tag,
          count,
        })),
        count: counts.size,
      });
      return;
    }

    const graphMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/graph$/);
    if (graphMatch) {
      await json(route, graphFixture);
      return;
    }

    const dailyTodayMatch = path.match(
      /^\/api\/v1\/vault\/([^/]+)\/daily\/today$/,
    );
    if (dailyTodayMatch) {
      if (route.request().method() === "GET") {
        await json(route, noteBodies[today]);
        return;
      }
      if (route.request().method() === "POST") {
        const payload = route.request().postDataJSON() as {
          content?: string;
          type?: string;
        };
        const content = payload.content ?? "";
        await json(route, { entry: `- [16:45:12] ${content}\n` }, 201);
        return;
      }
    }

    const graphEgoMatch = path.match(
      /^\/api\/v1\/vault\/([^/]+)\/graph\/ego\/(.+)$/,
    );
    if (graphEgoMatch) {
      const id = graphEgoMatch[2];
      await json(route, {
        nodes: [
          { id, title: String(id) },
          { id: "research-note", title: "Research Note" },
        ],
        links: [{ source: id, target: "research-note" }],
      });
      return;
    }

    const neighborMatch = path.match(
      /^\/api\/v1\/vault\/([^/]+)\/notes\/(.+)\/neighbors$/,
    );
    if (neighborMatch) {
      const id = neighborMatch[2];
      if (id === "tag:pkm") {
        await json(route, {
          note_id: id,
          outbound: [],
          inbound: [
            {
              note_id: "project-plan",
              title: "Project Plan",
              type: "note",
              description: "Project coordination summary and next actions.",
            },
            {
              note_id: "research-note",
              title: "Research Note",
              type: "note",
              description: "Research backlink context and related notes.",
            },
          ],
          semantic: [],
        });
        return;
      }
      await json(route, {
        note_id: id,
        outbound: [
          {
            note_id: "research-note",
            title: "Research Note",
            type: "wikilink",
            description: "Research backlink context and related notes.",
          },
        ],
        inbound: [],
        semantic: [
          {
            note_id: "project-plan",
            title: "Project Plan",
            type: "semantic",
            confidence: 0.91,
            description: "Project coordination summary and next actions.",
          },
        ],
      });
      return;
    }

    const noteMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/notes\/(.+)$/);
    if (noteMatch) {
      const id = noteMatch[2];
      if (id.endsWith("/ensure") && route.request().method() === "POST") {
        const ensuredId = id.replace(/\/ensure$/, "");
        const created = {
          note_id: ensuredId,
          title: ensuredId.replace(/-/g, " "),
          body: "",
          frontmatter: {
            id: ensuredId,
            title: ensuredId.replace(/-/g, " "),
            tags: [],
          },
          created: null,
          updated: null,
          tags: [],
          importance: null,
        };
        noteBodies[ensuredId] = created;
        await json(route, created, 201);
        return;
      }
      const note = noteBodies[id];
      if (note) {
        if (route.request().method() === "PUT") {
          const payload = route.request().postDataJSON() as { body?: string };
          const body =
            payload.body ?? String((note as { body?: unknown }).body ?? "");
          notePutPayloads.push({ id, body });
          if (typeof note === "object" && "body" in note) {
            noteBodies[id] = {
              ...note,
              body,
            };
          }
          await json(route, noteBodies[id]);
          return;
        }
        await json(route, note);
      } else {
        await route.fulfill({ status: 404, body: "not found" });
      }
      return;
    }

    await route.fulfill({ status: 404, body: `Unhandled mock route: ${path}` });
  });
}

async function expectCommandPaletteFocused(page: Page) {
  await expect(
    page.locator('[role="dialog"][aria-label="Command palette"]'),
  ).toBeVisible();
  await expect(page.locator(".cmdk-input")).toBeFocused();
}

async function openCommandPalette(page: Page) {
  await page.waitForLoadState("networkidle").catch(() => {});
  await expect(
    page.getByRole("button", { name: "Open command palette" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Open command palette" }).click();
  await expectCommandPaletteFocused(page);
}

async function openSearchPalette(page: Page) {
  await openCommandPalette(page);
  await page.getByRole("option", { name: /Jump to note/ }).click();
  await expectCommandPaletteFocused(page);
}

async function expectNoteHeaderId(page: Page, noteId: string) {
  const noteHeader = page.locator(".note-header");
  await expect(noteHeader.locator(".meta-rail")).toContainText("NOTE");
  await expect(noteHeader.locator(".meta-rail")).toContainText(noteId);
  await expect(noteHeader.getByRole("heading")).toHaveCount(0);
}

async function expectTopbar(page: Page, vault: string, pageName: string) {
  const topbar = page.locator(".topbar");
  await expect(topbar.getByText(vault, { exact: true })).toBeVisible();
  await expect(topbar.getByText(pageName, { exact: true })).toBeVisible();
  await expect(topbar.getByText("station", { exact: true })).toHaveCount(0);
  await expect(topbar.getByText("signal desk", { exact: true })).toHaveCount(0);
  await expect(topbar.getByText(/vim:/)).toHaveCount(0);
}

async function readThemeMetrics(page: Page) {
  return page.evaluate(() => {
    const topbar = document.querySelector(".topbar");
    const tag = document.querySelector(".note-body a.note-tag-chip");
    const callout = document.querySelector(".note-body blockquote");
    if (!topbar || !tag || !callout) {
      throw new Error("theme metric targets missing");
    }

    return {
      topbar: styleMetrics(topbar),
      tag: styleMetrics(tag),
      callout: styleMetrics(callout),
    };

    function styleMetrics(el: Element) {
      const style = getComputedStyle(el);
      const bgLum = luminance(parseColor(style.backgroundColor));
      const fgLum = luminance(parseColor(style.color));
      return {
        background: style.backgroundColor,
        color: style.color,
        bgLum,
        fgLum,
        contrast: contrastRatio(bgLum, fgLum),
      };
    }

    function parseColor(value: string): [number, number, number] {
      const match = value.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
      if (match) return [Number(match[1]), Number(match[2]), Number(match[3])];

      const srgb = value.match(/color\(srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)/);
      if (srgb) {
        return [
          Math.round(Number(srgb[1]) * 255),
          Math.round(Number(srgb[2]) * 255),
          Math.round(Number(srgb[3]) * 255),
        ];
      }

      return [0, 0, 0];
    }

    function luminance([r, g, b]: [number, number, number]) {
      const channels = [r, g, b].map((channel) => {
        const normalized = channel / 255;
        return normalized <= 0.03928
          ? normalized / 12.92
          : Math.pow((normalized + 0.055) / 1.055, 2.4);
      });
      return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
    }

    function contrastRatio(a: number, b: number) {
      const lighter = Math.max(a, b);
      const darker = Math.min(a, b);
      return (lighter + 0.05) / (darker + 0.05);
    }
  });
}

async function expectNoMissingPage(
  page: Page,
  options: { allowTagNotFound?: boolean } = {},
) {
  await expect(page.getByText(/^404$/)).toHaveCount(0);
  if (!options.allowTagNotFound) {
    await expect(page.getByText(/not found/i)).toHaveCount(0);
  }
}

function noteBodyFor(noteId: string): string {
  const note = noteBodies[noteId];
  if (note && typeof note === "object" && "body" in note) {
    return String((note as { body?: unknown }).body ?? "");
  }
  return "";
}

function resetMockNotes() {
  const projectNote = noteBodies["project-plan"];
  if (projectNote && typeof projectNote === "object") {
    noteBodies["project-plan"] = {
      ...projectNote,
      body: projectPlanBody,
    };
  }
  const longNote = noteBodies["long-content"];
  if (longNote && typeof longNote === "object") {
    noteBodies["long-content"] = {
      ...longNote,
      body: longContentBody,
    };
  }
}

function configPayload() {
  return {
    settings: [
      {
        key: "default-vault",
        section: "defaults",
        internal_key: "vault",
        description: "Default vault name used when --vault is not specified",
        value: vaultName,
        default_value: "",
        configured: true,
        source: "configured",
        input_type: "text",
        options: [],
      },
      {
        key: "graph-depth",
        section: "defaults",
        internal_key: "graph-depth",
        description:
          "Default graph traversal depth for search and show commands",
        value: "2",
        default_value: "",
        configured: true,
        source: "configured",
        input_type: "number",
        options: [],
      },
    ],
  };
}

function snippetFor(query: string, body: string): string {
  const foldedQuery = query.toLowerCase();
  const match = body
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line && line.toLowerCase().includes(foldedQuery));
  return match ?? "";
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}
