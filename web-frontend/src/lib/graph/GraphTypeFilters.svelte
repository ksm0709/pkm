<script lang="ts">
  import { toggleGraphType } from "./filters";

  interface Props {
    nodeTypes: string[];
    edgeTypes: string[];
    selectedNodeTypes: ReadonlySet<string>;
    selectedEdgeTypes: ReadonlySet<string>;
    onNodeTypesChange?: (types: Set<string>) => void;
    onEdgeTypesChange?: (types: Set<string>) => void;
  }

  let {
    nodeTypes,
    edgeTypes,
    selectedNodeTypes,
    selectedEdgeTypes,
    onNodeTypesChange = () => {},
    onEdgeTypesChange = () => {},
  }: Props = $props();

  function nodeTypeLabel(type: string) {
    if (type === "note_or_unresolved") return "unresolved";
    return type.replaceAll("_", " ");
  }

  function toggleNodeType(type: string) {
    onNodeTypesChange(toggleGraphType(selectedNodeTypes, type));
  }

  function toggleEdgeType(type: string) {
    onEdgeTypesChange(toggleGraphType(selectedEdgeTypes, type));
  }
</script>

<section class="graph-type-filters" aria-label="Graph type filters">
  <div class="filter-group" aria-label="Node type filters">
    <p class="filter-label">nodes</p>
    <div class="filter-pills">
      {#each nodeTypes as type (type)}
        <label class="filter-pill" class:active={selectedNodeTypes.has(type)}>
          <input
            type="checkbox"
            checked={selectedNodeTypes.has(type)}
            aria-label={`Show ${nodeTypeLabel(type)} nodes`}
            onchange={() => toggleNodeType(type)}
          />
          <span>{nodeTypeLabel(type)}</span>
        </label>
      {/each}
    </div>
  </div>

  <div class="filter-group" aria-label="Edge type filters">
    <p class="filter-label">edges</p>
    <div class="filter-pills">
      {#each edgeTypes as type (type)}
        <label class="filter-pill" class:active={selectedEdgeTypes.has(type)}>
          <input
            type="checkbox"
            checked={selectedEdgeTypes.has(type)}
            aria-label={`Show ${type.replaceAll("_", " ")} edges`}
            onchange={() => toggleEdgeType(type)}
          />
          <span>{type.replaceAll("_", " ")}</span>
        </label>
      {/each}
    </div>
  </div>
</section>

<style>
  .graph-type-filters {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-4, 16px);
    align-items: start;
  }

  .filter-group {
    min-width: 0;
  }

  .filter-label {
    margin: 0 0 var(--space-2, 8px);
    color: var(--text-faint);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }

  .filter-pills {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2, 8px);
  }

  .filter-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 28px;
    padding: 0 var(--space-2, 8px);
    border: 1px solid var(--border);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    cursor: pointer;
    user-select: none;
  }

  .filter-pill.active {
    border-color: var(--accent);
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 8%, transparent);
  }

  .filter-pill input {
    width: 12px;
    height: 12px;
    margin: 0;
    accent-color: var(--accent);
  }

  @media (max-width: 760px) {
    .graph-type-filters {
      grid-template-columns: 1fr;
    }
  }
</style>
