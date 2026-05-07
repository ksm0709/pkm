<script lang="ts">
  import { onMount } from "svelte";
  import type { Snippet } from "svelte";

  interface Props {
    children?: Snippet;
  }

  let { children }: Props = $props();

  type Theme = "light" | "dark" | "auto";

  function applyTheme(theme: Theme) {
    const root = document.documentElement;
    if (theme === "auto") {
      root.removeAttribute("data-theme");
    } else {
      root.setAttribute("data-theme", theme);
    }
  }

  function getStoredTheme(): Theme {
    try {
      const stored = localStorage.getItem("pkm.theme");
      if (stored === "light" || stored === "dark" || stored === "auto") {
        return stored;
      }
    } catch {
      // localStorage unavailable (SSR or private browsing)
    }
    return "auto";
  }

  onMount(() => {
    const theme = getStoredTheme();
    applyTheme(theme);

    // Listen for theme changes from ⌘K palette (custom event)
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<{ theme: Theme }>).detail;
      applyTheme(detail.theme);
      try {
        localStorage.setItem("pkm.theme", detail.theme);
      } catch {
        // ignore
      }
    };

    window.addEventListener("pkm:theme-change", handler);
    return () => window.removeEventListener("pkm:theme-change", handler);
  });
</script>

{#if children}
  {@render children()}
{/if}
