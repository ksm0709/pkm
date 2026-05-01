<script lang="ts">
  const title = 'pkm';
</script>

<svelte:head>
  <title>{title}</title>
</svelte:head>

<main>
  <h1>{title}</h1>
  <p>Personal Knowledge Manager</p>
</main>

<style>
  main {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    font-family: 'IBM Plex Mono', ui-monospace, monospace;
  }

  h1 {
    font-family: 'Newsreader', ui-serif, serif;
    font-size: 32px;
    font-weight: 600;
    letter-spacing: -0.01em;
    margin: 0 0 8px;
  }

  p {
    font-size: 13px;
    margin: 0;
    opacity: 0.6;
  }
</style>
