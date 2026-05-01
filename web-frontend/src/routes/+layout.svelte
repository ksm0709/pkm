<script lang="ts">
  import '../app.css';
  import ThemeProvider from '$lib/components/ThemeProvider.svelte';
  import type { Snippet } from 'svelte';

  interface Props {
    children: Snippet;
  }

  let { children }: Props = $props();
</script>

<ThemeProvider>
  {@render children()}
</ThemeProvider>
