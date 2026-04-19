from pkm.tools.notes import add_note, search_notes, read_note, update_note
from pkm.tools.search import semantic_search, get_graph_context
from pkm.tools.daily import add_daily_log, read_daily_log
from pkm.tools.maintenance import vault_stats, list_stale_notes, list_orphans
from pkm.tools.links import find_backlinks_for_note
from pkm.tools.tags import list_tags, tag_search
from pkm.tools.consolidate import list_consolidation_candidates, mark_consolidated
from pkm.tools.log import read_recent_note_activity


def get_pkm_tools(scope: str = "all") -> list:
    """Get the list of PKM tools for the agent.

    Args:
        scope: The scope of tools to return. Currently only 'all' is supported.
    """
    return [
        add_note,
        search_notes,
        read_note,
        update_note,
        semantic_search,
        get_graph_context,
        add_daily_log,
        read_daily_log,
        vault_stats,
        list_stale_notes,
        list_orphans,
        find_backlinks_for_note,
        list_tags,
        tag_search,
        list_consolidation_candidates,
        mark_consolidated,
        read_recent_note_activity,
    ]
