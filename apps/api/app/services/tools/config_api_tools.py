"""Config API tool stubs — registered so the LLM knows they exist.

These will be fully implemented in Phase 4.
"""
from app.services.tools.registry import registry
from app.services.tools.tool_context import ToolContext


@registry.tool(
    name="config_api_fetch",
    description=(
        "Fetch configuration from a Capillary Configuration API. Call this when the "
        "user wants to pull configuration data for context generation."
    ),
    module="config_apis",
    requires_permission=("config_apis", "fetch"),
    annotations={"display": "Fetching configuration data..."},
)
async def config_api_fetch(ctx: ToolContext, api_type: str = "") -> str:
    """Fetch from a Configuration API.

    api_type: The type of configuration API to fetch from (e.g. 'loyalty_programs', 'points_config')
    """
    return (
        "Configuration API integration is not yet available. This feature will allow you "
        "to fetch structured configuration data and convert it into context documents."
    )


@registry.tool(
    name="config_api_list_available",
    description=(
        "List available Configuration API types. Call this when the user wants "
        "to see what configuration APIs can be used for context generation."
    ),
    module="config_apis",
    requires_permission=("config_apis", "view"),
    annotations={"display": "Listing available config APIs..."},
)
async def config_api_list_available(ctx: ToolContext) -> str:
    return (
        "Configuration API listing is not yet fully available. The following API types "
        "are planned:\n\n"
        "- **loyalty_programs**: Loyalty program configuration\n"
        "- **points_config**: Points and tiers configuration\n"
        "- **customer_segments**: Segment definitions\n"
        "- **rewards_catalog**: Rewards and promotions setup\n"
        "- **store_hierarchy**: Store and zone configuration\n\n"
        "These will be available once the Config API integration is complete."
    )
