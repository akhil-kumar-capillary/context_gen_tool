"""
SQL extraction from notebook cells — AST-based and regex-based.

Ported from reference: services/sql_extractor.py
All functions are pure (no I/O dependencies) — direct port with zero logic changes.
"""

import re
import ast
import hashlib
from datetime import datetime
from typing import Optional

import sqlglot

# --- Constants ---
CRUD_KEYWORDS = frozenset(
    {"DROP", "CREATE", "INSERT", "UPDATE", "DELETE", "ALTER", "TRUNCATE", "MERGE"}
)
VALID_SQL_KEYWORDS = frozenset(
    {"SELECT", "WITH", "USE", "SHOW", "DESCRIBE", "DESC", "EXPLAIN"}
)
ORG_DB_PATTERN = re.compile(r"\b(read_api|write_db)_(\d+)\b", re.IGNORECASE)


# --- Utility Functions ---


def epoch_ms_to_str(epoch_ms) -> Optional[str]:
    """Convert epoch milliseconds to a formatted datetime string."""
    if epoch_ms:
        return datetime.fromtimestamp(epoch_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
    return None


def sha256_hash(text: str) -> Optional[str]:
    """Return SHA-256 hex digest of stripped text, or None if empty."""
    if not text:
        return None
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def extract_user_from_path(path: str) -> str:
    """Extract the owner username from a Databricks workspace path."""
    if not path:
        return "Unknown"
    parts = path.strip("/").split("/")
    if len(parts) >= 3 and parts[0] == "Workspace" and parts[1] == "Users":
        return parts[2]
    if len(parts) >= 2 and parts[0] == "Users":
        return parts[1]
    if len(parts) >= 2 and parts[0] == "Repos":
        return parts[1]
    if len(parts) >= 1 and parts[0] == "Shared":
        return "Shared"
    return parts[1] if len(parts) > 1 else "Unknown"


def redact_pii(text: str) -> str:
    """Redact emails, phone numbers, credit cards, and long tokens from text."""
    if not text:
        return text
    text = re.sub(
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "<EMAIL_REDACTED>",
        text,
    )
    text = re.sub(
        r"(?:\+91[\-\s]?)?(?:91[\-\s]?)?[6-9]\d{9}",
        "<MOBILE_REDACTED>",
        text,
    )
    text = re.sub(
        r"\+\d{1,3}[\-\s]?\(?\d{1,4}\)?[\-\s]?\d{3,4}[\-\s]?\d{3,4}",
        "<PHONE_REDACTED>",
        text,
    )
    text = re.sub(
        r"\b\d{4}[\-\s]?\d{4}[\-\s]?\d{4}[\-\s]?\d{1,7}\b",
        "<CC_REDACTED>",
        text,
    )
    text = re.sub(
        r"['\"][a-zA-Z0-9]{32,}['\"]",
        "'<TOKEN_REDACTED>'",
        text,
    )
    return text


# --- SQL Comment Removal ---


def remove_sql_comments(sql: str) -> str:
    """Remove SQL comments (-- and /* */) while preserving quoted strings."""
    if not sql:
        return sql
    result = []
    i = 0
    n = len(sql)
    while i < n:
        if sql[i] == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'" and j + 1 < n and sql[j + 1] == "'":
                    j += 2
                elif sql[j] == "'":
                    j += 1
                    break
                else:
                    j += 1
            result.append(sql[i:j])
            i = j
        elif sql[i : i + 2] == "/*":
            end = sql.find("*/", i + 2)
            if end == -1:
                break
            i = end + 2
        elif sql[i : i + 2] == "--":
            end = sql.find("\n", i)
            if end == -1:
                break
            i = end
        else:
            result.append(sql[i])
            i += 1
    return "".join(result).strip()


# --- Cell Comment Detection ---


def is_cell_commented_out(content: str, file_type: str) -> bool:
    """Check if the entire cell is commented out (no active code)."""
    lines = content.strip().split("\n")
    non_empty_lines = [line for line in lines if line.strip()]
    if not non_empty_lines:
        return True

    if file_type.lower() in ("python", "py"):
        stripped_content = content.strip()
        for quote in ('"""', "'''"):
            if (
                stripped_content.startswith(quote)
                and stripped_content.endswith(quote)
                and len(stripped_content) > 6
            ):
                return True
        for line in non_empty_lines:
            stripped = line.strip()
            if stripped.startswith("# DBTITLE"):
                continue
            if stripped.startswith("# MAGIC"):
                return False
            if not stripped.startswith("#"):
                return False
        return True

    elif file_type.lower() == "sql":
        for line in non_empty_lines:
            stripped = line.strip()
            if stripped.startswith("-- DBTITLE"):
                continue
            if stripped.startswith("-- MAGIC"):
                return False
            if not stripped.startswith("--"):
                return False
        return True

    return False


# --- AST-based SQL Extraction ---


class SQLExtractor(ast.NodeVisitor):
    """AST visitor that extracts SQL strings from spark.sql() calls."""

    def __init__(self):
        self.sql_queries: list[str] = []
        self.string_variables: dict[str, str] = {}

    def visit_Assign(self, node):
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            var_name = node.targets[0].id
            string_value = self._extract_string_value(node.value)
            if string_value:
                self.string_variables[var_name] = string_value
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "sql":
            if node.args:
                arg = node.args[0]
                string_value = self._extract_string_value(arg)
                if string_value:
                    self.sql_queries.append(string_value)
                elif isinstance(arg, ast.Name):
                    var_name = arg.id
                    if var_name in self.string_variables:
                        self.sql_queries.append(self.string_variables[var_name])
        self.generic_visit(node)

    def _extract_string_value(self, node) -> Optional[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        elif isinstance(node, ast.JoinedStr):
            parts = []
            for part in node.values:
                if isinstance(part, ast.Constant):
                    parts.append(str(part.value))
                elif isinstance(part, ast.FormattedValue):
                    parts.append("{...}")
            return "".join(parts)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = self._extract_string_value(node.left)
            right = self._extract_string_value(node.right)
            if left and right:
                return left + right
        return None


def extract_sql_from_python_ast(code: str) -> list:
    """Extract SQL queries from Python code using AST parsing."""
    try:
        tree = ast.parse(code)
        extractor = SQLExtractor()
        extractor.visit(tree)
        return extractor.sql_queries
    except SyntaxError:
        return extract_sql_from_python_regex(code)
    except Exception:
        return []


def extract_sql_from_python_regex(code: str) -> list:
    """Fallback: extract SQL queries from Python code using regex."""
    sql_queries = []
    triple_pattern = re.compile(
        r'\.sql\s*\(\s*"{3}(.*?)"{3}\s*\)|\.sql\s*\(\s*\'{3}(.*?)\'{3}\s*\)',
        re.DOTALL,
    )
    for m in triple_pattern.finditer(code):
        sql_queries.append(m.group(1) or m.group(2))
    if sql_queries:
        return sql_queries
    single_pattern = re.compile(
        r"\.sql\s*\(\s*\"([^\"]+)\"\s*\)|\.sql\s*\(\s*'([^']+)'\s*\)",
        re.DOTALL,
    )
    for m in single_pattern.finditer(code):
        sql_queries.append(m.group(1) or m.group(2))
    return sql_queries


# --- SQL Validation and Formatting ---


def validate_and_format_sql(sql: str) -> tuple[bool, Optional[str]]:
    """Validate a SQL statement and return (is_valid, formatted_sql).

    Uses sqlglot to parse and pretty-print Spark SQL. Filters out DDL/DML
    (DROP, UPDATE, etc.) while extracting SELECT subqueries from CREATE/INSERT.
    """
    if not sql or not sql.strip():
        return False, None
    cleaned_sql = sql.strip()
    first_word = cleaned_sql.split()[0].upper() if cleaned_sql.split() else ""

    if first_word in VALID_SQL_KEYWORDS:
        try:
            parsed = sqlglot.parse_one(cleaned_sql, read="spark")
            if parsed:
                return True, parsed.sql(dialect="spark")
        except Exception:
            pass
        return True, cleaned_sql

    if first_word in ("CREATE", "INSERT"):
        try:
            parsed = sqlglot.parse_one(cleaned_sql, read="spark")
            if parsed and hasattr(parsed, "expression") and parsed.expression:
                embedded_sql = parsed.expression.sql(dialect="spark")
                if embedded_sql and embedded_sql.strip():
                    upper_embedded = embedded_sql.strip().upper()
                    if upper_embedded.startswith("SELECT") or upper_embedded.startswith(
                        "WITH"
                    ):
                        return True, embedded_sql
        except Exception:
            pass
        match = re.search(
            r"\bAS\s+(WITH\s+.+|SELECT\s+.+)$",
            cleaned_sql,
            re.IGNORECASE | re.DOTALL,
        )
        if match:
            return True, match.group(1).strip()
        return False, None

    if first_word in CRUD_KEYWORDS:
        return False, None

    return False, None


def extract_valid_sql_statements(sql: str) -> list:
    """Parse a multi-statement SQL string and return list of valid SELECT/WITH queries."""
    if not sql:
        return []
    results = []
    try:
        statements = sqlglot.parse(sql, read="spark")
        for stmt in statements:
            if stmt is None:
                continue
            sql_str = stmt.sql(dialect="spark")
            if not sql_str:
                continue
            upper_sql = sql_str.strip().upper()
            if any(upper_sql.startswith(kw) for kw in VALID_SQL_KEYWORDS):
                results.append(sql_str)
            elif upper_sql.startswith("CREATE") or upper_sql.startswith("INSERT"):
                if hasattr(stmt, "expression") and stmt.expression:
                    try:
                        embedded = stmt.expression.sql(dialect="spark")
                        if embedded and embedded.strip().upper().startswith("SELECT"):
                            results.append(embedded)
                    except Exception:
                        pass
    except Exception:
        matches = re.findall(
            r"\b(SELECT\s+.+?)(?:;|$)", sql, re.IGNORECASE | re.DOTALL
        )
        results.extend([m.strip() for m in matches if m.strip()])
    return results


# --- Cell Content Extractors ---


def extract_magic_sql_from_python_cell(content: str) -> Optional[str]:
    """Extract SQL from # MAGIC %sql blocks in a Python cell."""
    lines = content.split("\n")
    sql_lines = []
    in_sql_block = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# DBTITLE"):
            continue
        if "# MAGIC %sql" in stripped:
            in_sql_block = True
            continue
        if in_sql_block and stripped.startswith("# MAGIC"):
            sql_part = re.sub(r"^#\s*MAGIC\s*", "", stripped)
            if sql_part.startswith("%"):
                continue
            sql_lines.append(sql_part)
    return "\n".join(sql_lines).strip() if sql_lines else None


def extract_sql_from_sql_cell(content: str) -> Optional[str]:
    """Extract SQL from a native SQL cell, skipping Databricks directives."""
    lines = content.split("\n")
    sql_lines = []
    skip_prefixes = (
        "-- Databricks notebook source",
        "-- DBTITLE",
        "-- MAGIC",
        "-- COMMAND",
    )
    for line in lines:
        stripped = line.strip()
        if any(stripped.startswith(p) for p in skip_prefixes):
            continue
        sql_lines.append(line)
    return "\n".join(sql_lines).strip() if sql_lines else None


def extract_embedded_python_from_sql_cell(content: str) -> Optional[str]:
    """Extract embedded Python code from -- MAGIC %python blocks in a SQL cell."""
    lines = content.split("\n")
    python_lines = []
    in_python_block = False
    for line in lines:
        stripped = line.strip()
        if "-- MAGIC %python" in stripped:
            in_python_block = True
            continue
        if in_python_block and stripped.startswith("-- MAGIC"):
            py_part = re.sub(r"^--\s*MAGIC\s*", "", stripped)
            python_lines.append(py_part)
    return "\n".join(python_lines).strip() if python_lines else None


# --- Main Cell Extraction Logic ---


def extract_sql_from_cell(
    raw_content: str, file_type: str
) -> tuple[Optional[str], bool]:
    """Extract and validate SQL from a single notebook cell.

    Args:
        raw_content: Raw cell content string.
        file_type: Cell language — "python", "py", or "sql".

    Returns:
        (formatted_sql, is_valid) — the best SQL found, or (None, False).
    """
    if not raw_content or not raw_content.strip():
        return None, False
    content = raw_content.strip()

    # Skip markdown, pip, and shell cells
    if "# MAGIC %md" in content or "-- MAGIC %md" in content:
        return None, False
    if "%pip" in content or "%sh" in content:
        return None, False
    if is_cell_commented_out(content, file_type):
        return None, False

    extracted_sqls: list[str] = []

    if file_type.lower() in ("python", "py"):
        # Check for MAGIC SQL blocks
        if "# MAGIC %sql" in content:
            sql_content = extract_magic_sql_from_python_cell(content)
            if sql_content:
                extracted_sqls.append(sql_content)
        # Check for spark.sql() calls
        if "spark.sql" in content or ".sql(" in content:
            code_lines = [
                line
                for line in content.split("\n")
                if not line.strip().startswith("#")
            ]
            if code_lines:
                sqls = extract_sql_from_python_ast("\n".join(code_lines))
                extracted_sqls.extend(sqls)

    elif file_type.lower() == "sql":
        if "-- MAGIC %python" in content:
            python_code = extract_embedded_python_from_sql_cell(content)
            if python_code:
                sqls = extract_sql_from_python_ast(python_code)
                extracted_sqls.extend(sqls)
        else:
            sql_content = extract_sql_from_sql_cell(content)
            if sql_content:
                extracted_sqls.append(sql_content)

    # Validate and return the first valid SQL found
    for sql in extracted_sqls:
        if sql and sql.strip():
            cleaned = remove_sql_comments(sql).strip()
            if not cleaned:
                continue
            redacted = redact_pii(cleaned)
            is_valid, formatted = validate_and_format_sql(redacted)
            if formatted:
                return formatted, is_valid
            elif is_valid:
                return redacted, is_valid

    return None, False


# --- Org ID Extraction ---


def extract_org_id_from_sql(sql: str) -> Optional[str]:
    """Extract org ID from read_api_NNN or write_db_NNN patterns in SQL."""
    if not sql:
        return None
    matches = ORG_DB_PATTERN.findall(sql)
    return matches[0][1] if matches else None


def extract_notebook_default_org_id(content: str) -> Optional[str]:
    """Extract the default org ID from USE read_api_NNN / write_db_NNN statements."""
    if not content:
        return None
    matches = re.findall(
        r"\buse\s+(read_api|write_db)_(\d+)\b", content, re.IGNORECASE
    )
    return matches[0][1] if matches else None


def get_org_id_for_sql(
    sql: str, notebook_default: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    """Determine org ID for a SQL query — inline takes precedence over notebook default.

    Returns:
        (org_id, source) where source is "In-Query", "Notebook", or None.
    """
    inline_org = extract_org_id_from_sql(sql)
    if inline_org:
        return inline_org, "In-Query"
    if notebook_default:
        return notebook_default, "Notebook"
    return None, None
