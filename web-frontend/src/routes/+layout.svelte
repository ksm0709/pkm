<script lang="ts">
  import "../app.css";
  import ThemeProvider from "$lib/components/ThemeProvider.svelte";
  import { onMount } from "svelte";
  import type { Snippet } from "svelte";

  interface Props {
    children: Snippet;
  }

  let { children }: Props = $props();

  onMount(() => {
    const orientation = globalThis.screen?.orientation;
    orientation?.lock?.("portrait").catch(() => {
      // Browsers can reject outside installed/fullscreen app contexts.
    });
  });
</script>

<ThemeProvider>
  {@render children()}
</ThemeProvider>
