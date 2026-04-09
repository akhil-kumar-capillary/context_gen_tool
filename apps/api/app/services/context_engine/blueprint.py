"""Shared blueprint loading for the context engine."""
from pathlib import Path

import aiofiles
import aiofiles.os

BLUEPRINT_PATH = Path(__file__).parent.parent.parent / "resources" / "blueprint.md"


async def load_blueprint(custom_text: str | None = None) -> str:
    """Load the restructuring/sanitization blueprint.

    Priority:
    1. Custom text provided by the caller
    2. Default blueprint.md file
    """
    if custom_text and custom_text.strip():
        return custom_text.strip()

    if await aiofiles.os.path.exists(BLUEPRINT_PATH):
        async with aiofiles.open(BLUEPRINT_PATH, encoding="utf-8") as f:
            return await f.read()

    raise FileNotFoundError(
        f"Blueprint file not found at {BLUEPRINT_PATH} and no custom blueprint provided."
    )


def build_refactor_preamble(context_count: int) -> str:
    """Build the shared preamble for refactor/sanitize user messages.

    This includes the JSON output format instructions and the
    Zero Information Loss Protocol checklist.
    """
    return (
        "Below are ALL the context documents for this organization. "
        "Please restructure them according to the blueprint instructions.\n\n"
        f"There are {context_count} context document(s). "
        "Restructure and compress without losing critical information.\n\n"
        "Return your response as a JSON array where each element has:\n"
        '- "name": the context document name (max 100 chars, only alphanumeric, spaces, _:#()-,)\n'
        '- "content": the restructured context content in markdown\n\n'
        "Respond ONLY with the JSON array, no additional text before or after it.\n\n"
        "## CRITICAL: Zero Information Loss Protocol\n"
        "You MAY merge, split, rename, or reorganize documents freely — the "
        "output count does NOT need to match the input count. However, every "
        "piece of INFORMATION from every input must survive in the output.\n\n"
        "Before finalizing your response, run this self-validation checklist:\n"
        "1. For each input document, verify every rule, table, SQL snippet, "
        "mapping, and KPI definition is present somewhere in your output.\n"
        "2. If you merge documents, ALL information from ALL merged inputs "
        "must appear in the merged output — merging means combining, not choosing.\n"
        "3. Never skip content because the output is getting long. A longer "
        "complete output is always better than a shorter incomplete one.\n"
        "4. Re-read your output and confirm no information was lost. "
        "Fix any gaps before responding.\n\n"
        "---\n\n"
    )
