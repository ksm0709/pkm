from pkm.tools.notes import add_note, search_notes, read_note, update_note
from pkm.tools.search import semantic_search, get_graph_context
from pkm.tools.daily import add_daily_log, read_daily_log


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
    ]
