# Dream — Deprecated Compatibility Alias

> **DEPRECATED:** `dream` is a compatibility alias for `refine-loop`.
> The canonical top-level workflows are now `zettel-loop` (knowledge production) and
> `refine-loop` (cleanup/reduction). Use those names going forward.
>
> This alias is retained for one transition cycle only and will be removed in a future release.

## Redirect

When the user invokes `dream`, execute `workflows/refine-loop.md` instead.

The old `dream` pipeline mapped to the following canonical split:

| Old dream step | New canonical home |
|----------------|--------------------|
| consolidate (mark) | `zettel-loop` step 1 |
| distill-daily (promote) | `zettel-loop` step 2 |
| auto-linking (new notes) | `zettel-loop` step 3 |
| auto-tagging (new notes) | `zettel-loop` step 4 |
| health-check | `refine-loop` step 1 |
| prune-merge-split | `refine-loop` step 4 |

If the user wants the full production + cleanup pipeline in one pass, run `zettel-loop` first,
then `refine-loop`.

## Migration Note

- `/pkm:dream` → use `/pkm:refine-loop` (cleanup) or `/pkm:zettel-loop` (production)
- Trigger word "dream" → routes to `refine-loop` (deprecated secondary trigger)
- All workflow indexes and tables now list `zettel-loop` and `refine-loop` as canonical
