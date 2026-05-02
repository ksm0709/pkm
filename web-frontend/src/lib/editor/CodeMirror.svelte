<script lang="ts">
  /**
   * CodeMirror 6 wrapper for pkm-webapp.
   *
   * Slice 2 (F2-1): markdown lang + vim mode + design-token theme.
   * Slice 2 (F2-2): live styling extension wired in below.
   * Slice 2 (F2-3): slash menu completion source wired in below.
   *
   * Two-way binding via Svelte 5 `$bindable()` for the doc value.
   * onMount creates the EditorView, onDestroy disposes it.
   */
  import { onMount, onDestroy } from 'svelte';
  import { EditorState, type Extension } from '@codemirror/state';
  import { EditorView, keymap, lineNumbers, highlightActiveLine } from '@codemirror/view';
  import { defaultKeymap, history, historyKeymap } from '@codemirror/commands';
  import { vim } from '@replit/codemirror-vim';
  import { pkmTheme } from './theme.js';
  import { installVimMappings } from './vim.js';
  import { liveStyling, liveStylingTheme } from './live-styling.js';
  import { slashCommands } from './slash-commands.js';
  import { markdownWithGfm } from './markdown-extensions.js';
  import { katexLazy, katexLazyTheme } from './katex-lazy.js';
  import { admonitions, admonitionsTheme } from './admonitions.js';
  import { footnotes, footnotesTheme } from './footnotes.js';
  import { checkboxes, checkboxesTheme } from './checkboxes.js';
  import { frontmatterByline, frontmatterBylineTheme } from './frontmatter-byline.js';
  import { tagPill, tagPillTheme } from './tag-pill.js';

  interface Props {
    doc?: string;
    extensions?: Extension[];
    readOnly?: boolean;
  }

  let {
    doc = $bindable(''),
    extensions = [],
    readOnly = false
  }: Props = $props();

  let host: HTMLDivElement | null = $state(null);
  let view: EditorView | null = null;
  // Track whether the next doc change came from the editor itself, so we
  // do not echo it back through the bindable assignment.
  let suppressNext = false;

  onMount(() => {
    installVimMappings();

    const baseExtensions: Extension[] = [
      // Vim must come first to bind keys before defaultKeymap claims them.
      vim(),
      history(),
      lineNumbers(),
      highlightActiveLine(),
      markdownWithGfm,
      keymap.of([...defaultKeymap, ...historyKeymap]),
      pkmTheme,
      liveStylingTheme,
      liveStyling,
      ...slashCommands,
      // F4-1: maximalist live styling. Themes first, then plugins.
      katexLazyTheme,
      admonitionsTheme,
      footnotesTheme,
      checkboxesTheme,
      katexLazy,
      admonitions,
      footnotes,
      checkboxes,
      // F4-3: frontmatter byline — placed AFTER live-styling AND maximalist
      // plugins so it has outer precedence on the YAML range.
      frontmatterBylineTheme,
      frontmatterByline,
      // F4-5: tag pill rendering.
      tagPillTheme,
      tagPill,
      EditorView.lineWrapping,
      EditorView.editable.of(!readOnly),
      EditorState.readOnly.of(readOnly),
      EditorView.updateListener.of((update) => {
        if (!update.docChanged) return;
        const next = update.state.doc.toString();
        if (next === doc) return;
        suppressNext = true;
        doc = next;
      }),
      ...extensions
    ];

    view = new EditorView({
      state: EditorState.create({ doc, extensions: baseExtensions }),
      parent: host!
    });
  });

  // React to external doc changes (e.g., parent loaded a different note).
  $effect(() => {
    if (!view) return;
    if (suppressNext) {
      suppressNext = false;
      return;
    }
    const current = view.state.doc.toString();
    if (current === doc) return;
    view.dispatch({
      changes: { from: 0, to: current.length, insert: doc }
    });
  });

  onDestroy(() => {
    view?.destroy();
    view = null;
  });
</script>

<div class="cm-host" bind:this={host}></div>

<style>
  .cm-host {
    width: 100%;
    height: 100%;
    min-height: 240px;
  }

  /* Strip CM6 default focus outline — we use --accent caret/selection instead. */
  .cm-host :global(.cm-editor) {
    outline: none;
    height: 100%;
  }
  .cm-host :global(.cm-editor.cm-focused) {
    outline: none;
  }
</style>
