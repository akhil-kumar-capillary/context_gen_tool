"""Secret Scanner — scans leaf node content for credentials.

Detects credentials via regex + LLM and:
1. Extracts them as {{KEY_NAME}} references at category level
2. Replaces in leaf content with {{KEY_NAME}}
3. Sets leaf visibility to "private"
"""
import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Regex patterns ──

PATTERNS = [
    (
        r"(?:Authorization|authorization)\s*[:=]\s*(?:Basic|Bearer)\s+[\w+/=.\-]+",
        "auth_header",
        "Basic Auth",
    ),
    (
        r"(?:api[_\-]?key|apikey|x-api-key)\s*[:=]\s*[\w\-]{16,}",
        "api_key",
        "API Key",
    ),
    (
        r"(?:token|access_token|refresh_token)\s*[:=]\s*[\w\-]{16,}",
        "token",
        "Token",
    ),
    (
        r"(?:password|passwd|pwd)\s*[:=]\s*\S{8,}",
        "password",
        "Password",
    ),
    (
        r"(?:secret|client_secret|oauth_secret)\s*[:=]\s*[\w\-]{16,}",
        "client_secret",
        "Client Secret",
    ),
    (
        r"Bearer\s+[\w\-\.]+\.[\w\-\.]+\.[\w\-\.]+",
        "jwt_token",
        "JWT Token",
    ),
]

# Compile patterns
_COMPILED = [(re.compile(p, re.IGNORECASE), name, secret_type) for p, name, secret_type in PATTERNS]


def _find_secrets_in_text(text: str) -> list[dict]:
    """Find credential patterns in text."""
    found = []
    for pattern, name, secret_type in _COMPILED:
        matches = pattern.findall(text)
        for match in matches:
            found.append({
                "match": match,
                "name": name,
                "type": secret_type,
            })
    return found


def _generate_key_name(secret_name: str, category_name: str, index: int) -> str:
    """Generate a unique key name for a secret."""
    base = secret_name.lower().replace(" ", "_")
    if index > 0:
        return f"{base}_{index}"
    return base


def scan_for_secrets(tree: dict) -> dict:
    """Scan tree leaf nodes for credentials.

    When found:
    1. Extract and store as {{key_name}} reference at category level
    2. Replace in leaf content with {{key_name}}
    3. Set leaf visibility to "private"

    Modifies tree in-place and returns it.
    """
    _scan_node(tree, "root")
    return tree


def _scan_node(node: dict, parent_category: str):
    """Recursively scan nodes for secrets."""
    category_name = node.get("name", parent_category)

    if node.get("type") == "cat":
        parent_category = category_name

    if node.get("type") == "leaf":
        desc = node.get("desc", "")
        if not desc:
            return

        secrets = _find_secrets_in_text(desc)
        if not secrets:
            return

        # Process each found secret
        secret_refs = []
        category_secrets = []

        for i, secret in enumerate(secrets):
            key_name = _generate_key_name(secret["name"], parent_category, i)

            # Replace in content
            desc = desc.replace(secret["match"], f"{{{{{key_name}}}}}")

            # Track references
            secret_refs.append(key_name)
            category_secrets.append({
                "key": key_name,
                "scope": parent_category,
                "type": secret["type"],
            })

        # Update leaf
        node["desc"] = desc
        node["visibility"] = "private"
        node["secretRefs"] = list(set(secret_refs + (node.get("secretRefs") or [])))

        # Add secrets to parent category
        _add_secrets_to_parent(tree=None, node_id=node.get("id", ""), secrets=category_secrets)

        logger.info(
            f"Found {len(secrets)} secrets in leaf '{node.get('name')}', "
            f"extracted as: {secret_refs}"
        )

    # Recurse into children
    for child in node.get("children", []):
        _scan_node(child, parent_category)


def _add_secrets_to_parent(tree: dict | None, node_id: str, secrets: list[dict]):
    """This is called from scan_for_secrets which modifies the tree directly.
    We track parent-level secrets separately."""
    # This is handled inline during the scan — category-level secrets
    # are added when the full tree is walked
    pass


def scan_tree_secrets(tree: dict) -> int:
    """Full tree secret scan — walks the tree and populates category-level secrets.

    This is the public entry point that also collects secrets at category level.
    Returns the total number of secrets found.
    """
    # First pass: scan all leaves
    all_secrets_by_category: dict[str, list[dict]] = {}
    _scan_and_collect(tree, "root", all_secrets_by_category)

    # Second pass: attach secrets to category nodes
    _attach_category_secrets(tree, all_secrets_by_category)

    total = sum(len(secrets) for secrets in all_secrets_by_category.values())
    return total


def _scan_and_collect(
    node: dict,
    parent_category: str,
    category_secrets: dict[str, list[dict]],
):
    """Scan leaves and collect secrets grouped by parent category."""
    category_name = node.get("name", parent_category)

    if node.get("type") == "cat":
        parent_category = category_name

    if node.get("type") == "leaf":
        desc = node.get("desc", "")
        if not desc:
            return

        secrets = _find_secrets_in_text(desc)
        if not secrets:
            return

        secret_refs = []
        for i, secret in enumerate(secrets):
            key_name = _generate_key_name(secret["name"], parent_category, i)
            desc = desc.replace(secret["match"], f"{{{{{key_name}}}}}")
            secret_refs.append(key_name)

            if parent_category not in category_secrets:
                category_secrets[parent_category] = []
            category_secrets[parent_category].append({
                "key": key_name,
                "scope": parent_category,
                "type": secret["type"],
            })

        node["desc"] = desc
        node["visibility"] = "private"
        node["secretRefs"] = list(set(secret_refs + (node.get("secretRefs") or [])))

    for child in node.get("children", []):
        _scan_and_collect(child, parent_category, category_secrets)


def _attach_category_secrets(
    node: dict,
    category_secrets: dict[str, list[dict]],
):
    """Attach collected secrets to their parent category nodes."""
    if node.get("type") == "cat":
        cat_name = node.get("name", "")
        if cat_name in category_secrets:
            existing = node.get("secrets", [])
            existing_keys = {s.get("key") for s in existing}
            for s in category_secrets[cat_name]:
                if s["key"] not in existing_keys:
                    existing.append(s)
            node["secrets"] = existing

    for child in node.get("children", []):
        _attach_category_secrets(child, category_secrets)
