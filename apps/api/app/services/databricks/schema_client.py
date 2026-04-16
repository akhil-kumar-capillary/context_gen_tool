"""Thrift schema client — fetches ground-truth DB schema from Capillary's ask-aira API.

Returns structured schema (tables, columns, types, FKs, display names, descriptions)
that enriches the doc generation pipeline with verified metadata.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


# ── Data classes ──


@dataclass
class ThriftColumn:
    name: str
    data_type: str
    display_name: str | None = None
    description: str | None = None
    foreign_key: str | None = None
    standard_filter: str | None = None
    column_type: str | None = None  # MEASURE, DIMENSION, DUMP_DATA (for fact tables)


@dataclass
class ThriftTable:
    name: str
    table_type: str  # DIMENSION, BASE_FACT, CUSTOM_TABLE, VIEW, SUMMARY
    namespace: str
    columns: list[ThriftColumn] = field(default_factory=list)
    primary_keys: list[str] = field(default_factory=list)
    partition_columns: list[str] = field(default_factory=list)
    description: str | None = None
    view_sql: str | None = None


@dataclass
class ThriftSchema:
    tables: dict[str, ThriftTable] = field(default_factory=dict)

    @property
    def fact_tables(self) -> list[str]:
        return [t.name for t in self.tables.values() if t.table_type == "BASE_FACT"]

    @property
    def dimension_tables(self) -> list[str]:
        return [t.name for t in self.tables.values() if t.table_type == "DIMENSION"]

    @property
    def custom_tables(self) -> list[str]:
        return [t.name for t in self.tables.values() if t.table_type == "CUSTOM_TABLE"]

    @property
    def views(self) -> list[str]:
        return [t.name for t in self.tables.values() if t.table_type == "VIEW"]

    def get_table(self, name: str) -> Optional[ThriftTable]:
        return self.tables.get(name)

    def get_column(self, table_name: str, column_name: str) -> Optional[ThriftColumn]:
        table = self.tables.get(table_name)
        if not table:
            return None
        for col in table.columns:
            if col.name == column_name:
                return col
        return None

    def table_exists(self, name: str) -> bool:
        return name in self.tables

    def column_exists(self, table_name: str, column_name: str) -> bool:
        return self.get_column(table_name, column_name) is not None

    @property
    def all_table_names(self) -> set[str]:
        return set(self.tables.keys())

    @property
    def table_count(self) -> int:
        return len(self.tables)

    @property
    def column_count(self) -> int:
        return sum(len(t.columns) for t in self.tables.values())


# ── Parsing helpers (ported from Thrift APIs notebook) ──


def _parse_header(content: str) -> dict:
    """Extract YAML-like key: value pairs from doc header."""
    header = {}
    header_block = re.split(r'\n## |\n\|', content, maxsplit=1)[0]
    for m in re.finditer(r'^([A-Za-z_ ]+):\s*(.+)$', header_block, re.MULTILINE):
        key = m.group(1).strip().lower().replace(' ', '_')
        header[key] = m.group(2).strip()
    title_m = re.match(r'^#\s+(\S+)', content)
    if title_m:
        header['title'] = title_m.group(1)
    return header


def _parse_fact_columns(content: str) -> list[dict]:
    """Parse BASE_FACT column blocks (## section per column)."""
    cols = []
    for block in re.split(r'\n## ', content)[1:]:
        lines = block.strip().split('\n')
        col = {'column_logical_name': lines[0].strip()}
        for line in lines[1:]:
            kv = re.match(r'^([A-Za-z_ ]+):\s*(.+)$', line)
            if kv:
                col[kv.group(1).strip().lower().replace(' ', '_')] = kv.group(2).strip()
        cols.append(col)
    return cols


def _parse_md_table(content: str) -> list[dict]:
    """Parse markdown table with any number of columns into list of dicts."""
    result = []
    lines = content.split("\n")
    header = None
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        # Split on | and filter empty parts from leading/trailing pipes
        # Split on | preserving empty cells for column alignment
        parts = stripped.split("|")
        if parts and parts[0].strip() == "":
            parts = parts[1:]
        if parts and parts[-1].strip() == "":
            parts = parts[:-1]
        cells = [c.strip() for c in parts]
        if not cells or all(c == "" for c in cells):
            continue
        # Skip separator rows (e.g., |---|---|---|)
        if all(set(c) <= {"-", ":", " "} for c in cells):
            continue
        if header is None:
            header = [c.lower().replace(" ", "_") for c in cells]
        else:
            row = dict(zip(header, cells))
            result.append(row)
    return result


def _extract_view_sql(content: str) -> str:
    """Extract CREATE VIEW statement."""
    m = re.search(r'(CREATE VIEW .+)', content, re.DOTALL)
    return m.group(1).strip() if m else ''


def _parse_pk_list(raw: str) -> list[str]:
    """Parse comma-separated primary key string."""
    if not raw:
        return []
    return [k.strip() for k in raw.split(',') if k.strip()]


# ── Document parser ──


def parse_thrift_docs(documents: list[dict]) -> ThriftSchema:
    """Parse raw Thrift API documents into structured ThriftSchema.

    Args:
        documents: List of {name, source_id, namespace, content} dicts from API.

    Returns:
        ThriftSchema with all tables and columns populated.
    """
    schema = ThriftSchema()

    for doc in documents:
        content = doc.get("content", "")
        if not content:
            continue

        hdr = _parse_header(content)
        doc_type = hdr.get("type", "UNKNOWN")
        table_name = hdr.get("table_name", doc.get("source_id", ""))
        namespace = doc.get("namespace", "").rstrip("/")

        if not table_name or doc_type == "UNKNOWN":
            continue

        table = ThriftTable(
            name=table_name,
            table_type=doc_type,
            namespace=namespace,
            description=hdr.get("description"),
            primary_keys=_parse_pk_list(hdr.get("primary_keys", hdr.get("primary_key", ""))),
            partition_columns=_parse_pk_list(hdr.get("partition_columns", "")),
        )

        if doc_type == "BASE_FACT":
            for c in _parse_fact_columns(content):
                table.columns.append(ThriftColumn(
                    name=c.get("column_name", c.get("column_logical_name", "")),
                    data_type=c.get("data_type", ""),
                    display_name=c.get("column_logical_name"),
                    description=c.get("description"),
                    foreign_key=c.get("foreign_key"),
                    standard_filter=c.get("standard_filter"),
                    column_type=c.get("type"),  # MEASURE, DIMENSION, DUMP_DATA
                ))

        elif doc_type in ("DIMENSION", "CUSTOM_TABLE"):
            for c in _parse_md_table(content):
                table.columns.append(ThriftColumn(
                    name=c.get("column_name", ""),
                    data_type=c.get("data_type", ""),
                    display_name=c.get("display_name"),
                ))

        elif doc_type == "VIEW":
            table.view_sql = _extract_view_sql(content)

        schema.tables[table_name] = table

    logger.info(
        f"Parsed Thrift schema: {schema.table_count} tables, "
        f"{schema.column_count} columns "
        f"({len(schema.fact_tables)} fact, {len(schema.dimension_tables)} dim, "
        f"{len(schema.custom_tables)} custom, {len(schema.views)} view)"
    )
    return schema


# ── API client ──


async def fetch_thrift_schema(
    base_url: str,
    capillary_token: str,
    org_id: str | int,
) -> ThriftSchema:
    """Fetch and parse ground-truth schema from the ask-aira Thrift docs API.

    Args:
        base_url: Capillary Intouch base URL (e.g. https://apac2.intouch.capillarytech.com)
        capillary_token: Bearer token from user's Capillary session
        org_id: Organization ID

    Returns:
        ThriftSchema with all tables and columns for the org.

    Raises:
        httpx.HTTPStatusError: If the API returns a non-2xx status.
        ValueError: If the response format is unexpected.
    """
    url = f"{base_url}/ask-aira/rag/thrift_docs"
    headers = {
        "Authorization": f"Bearer {capillary_token}",
        "x-cap-api-auth-org-id": str(org_id),
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    documents = data.get("documents", [])
    if not documents:
        logger.warning(f"Thrift API returned 0 documents for org {org_id}")
        return ThriftSchema()

    logger.info(f"Fetched {len(documents)} Thrift docs for org {org_id}")
    return parse_thrift_docs(documents)
