<script lang="ts">
  const title = 'pkm';
</script>

<svelte:head>
  <title>{title}</title>
</svelte:head>

<main class="reading-column" style="min-height: 100vh; display: flex; flex-direction: column; justify-content: center; padding-top: var(--space-8); padding-bottom: var(--space-8);">
  <h1>{title}</h1>
  <p class="text-muted" style="margin-top: var(--space-2); font-size: var(--type-chrome-size);">Personal Knowledge Manager</p>
</main>
