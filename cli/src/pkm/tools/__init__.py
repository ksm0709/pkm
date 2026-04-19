from pkm.tools.notes import add_note, search_notes
from pkm.tools.search import semantic_search
from pkm.tools.daily import add_daily_log, read_daily_log


def get_pkm_tools(scope: str = "all") -> list:
    """Get the list of PKM tools for the agent.

    Args:
        scope: The scope of tools to return. Currently only 'all' is supported.
    """
    return [add_note, search_notes, semantic_search, add_daily_log, read_daily_log]
