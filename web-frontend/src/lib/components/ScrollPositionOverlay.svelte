<script lang="ts">
  import { onDestroy } from "svelte";

  interface ScrollOverlayInfo {
    progress: number;
    percent: number;
    scrollElement: HTMLElement;
  }

  interface Props {
    scrollElement: HTMLElement | null;
    testId?: string;
    idleMs?: number;
    getDetailLabel?: ((info: ScrollOverlayInfo) => string | null) | null;
  }

  let {
    scrollElement,
    testId = "scroll-position-overlay",
    idleMs = 900,
    getDetailLabel = null,
  }: Props = $props();

  let visible = $state(false);
  let label = $state("0%");
  let hideTimer: ReturnType<typeof setTimeout> | null = null;

  function clearHideTimer() {
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = null;
  }

  function scrollProgress(element: HTMLElement) {
    const maxScroll = element.scrollHeight - element.clientHeight;
    if (maxScroll <= 1) return null;
    return Math.min(Math.max(element.scrollTop / maxScroll, 0), 1);
  }

  function updateFromScroll(element: HTMLElement) {
    const progress = scrollProgress(element);
    if (progress === null) {
      visible = false;
      clearHideTimer();
      return;
    }

    const percent = Math.round(progress * 100);
    const detail = getDetailLabel?.({
      progress,
      percent,
      scrollElement: element,
    });
    label = detail ? `${percent}% · ${detail}` : `${percent}%`;
    visible = true;
    clearHideTimer();
    hideTimer = setTimeout(() => {
      visible = false;
      hideTimer = null;
    }, idleMs);
  }

  $effect(() => {
    const element = scrollElement;
    if (!element) {
      visible = false;
      clearHideTimer();
      return;
    }

    const handleScroll = () => updateFromScroll(element);
    element.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      element.removeEventListener("scroll", handleScroll);
      visible = false;
      clearHideTimer();
    };
  });

  onDestroy(clearHideTimer);
</script>

{#if visible}
  <div class="scroll-position-overlay" data-testid={testId} aria-hidden="true">
    {label}
  </div>
{/if}

<style>
  .scroll-position-overlay {
    position: fixed;
    z-index: 30;
    top: 50%;
    right: max(var(--space-4, 16px), var(--window-padding, 24px));
    transform: translateY(-50%);
    padding: 6px 10px;
    border: 1px solid color-mix(in srgb, var(--border) 68%, transparent);
    border-radius: 999px;
    color: var(--text);
    background: color-mix(in srgb, var(--surface, var(--bg)) 72%, transparent);
    box-shadow: 0 8px 22px color-mix(in srgb, #000 24%, transparent);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    line-height: 1.2;
    letter-spacing: 0.04em;
    pointer-events: none;
    user-select: none;
    backdrop-filter: blur(6px);
  }
</style>
