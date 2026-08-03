"""Strict, read-only equivalence checks for the frozen baseline schema."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, PrimaryKeyConstraint
from sqlalchemy import UniqueConstraint, inspect
from sqlalchemy.engine import Connection

from migrations.baseline_schema import BASELINE_TABLE_NAMES, build_baseline_metadata


_CHECK_TOKEN = re.compile(
    r"'(?:''|[^'])*'|<=|>=|!=|<>|=|<|>|"
    r"[a-z_][a-z0-9_]*|\d+(?:\.\d+)?|[^\s]",
    flags=re.IGNORECASE,
)
CheckSignature = tuple[Any, ...]


@dataclass(frozen=True)
class SchemaValidation:
    matches: bool
    is_empty: bool
    business_table_count: int
    mismatches: tuple[str, ...]


def _normalize_sql(value: object, *, table_name: str = "") -> str:
    text = str("" if value is None else value).strip()
    parts = re.split(r"('(?:''|[^'])*')", text)
    for index in range(0, len(parts), 2):
        unquoted = parts[index].lower().replace('"', "").replace("`", "")
        unquoted = re.sub(
            r"::(?:character\s+varying|[a-z_][a-z0-9_]*)(?:\[\])?",
            "",
            unquoted,
        )
        if table_name:
            unquoted = re.sub(rf"\b{re.escape(table_name.lower())}\.", "", unquoted)
        previous = None
        while previous != unquoted:
            previous = unquoted
            unquoted = re.sub(
                r"(?<![a-z0-9_])\(\s*([a-z_][a-z0-9_]*|\d+)\s*\)",
                r"\1",
                unquoted,
            )
        parts[index] = re.sub(r"\s+", " ", unquoted)
    text = "".join(parts).strip()
    while text.startswith("(") and text.endswith(")"):
        candidate = text[1:-1].strip()
        if _parentheses_balanced(candidate):
            text = candidate
        else:
            break
    return text


def _parentheses_balanced(value: str) -> bool:
    depth = 0
    in_literal = False
    index = 0
    while index < len(value):
        character = value[index]
        if character == "'":
            if in_literal and index + 1 < len(value) and value[index + 1] == "'":
                index += 2
                continue
            in_literal = not in_literal
        elif not in_literal and character == "(":
            depth += 1
        elif not in_literal and character == ")":
            depth -= 1
            if depth < 0:
                return False
        index += 1
    return depth == 0 and not in_literal


def _strip_outer_tokens(tokens: tuple[str, ...]) -> tuple[str, ...]:
    result = tokens
    while len(result) >= 2 and result[0] == "(" and result[-1] == ")":
        depth = 0
        encloses_all = True
        for index, token in enumerate(result):
            if token == "(":
                depth += 1
            elif token == ")":
                depth -= 1
                if depth == 0 and index != len(result) - 1:
                    encloses_all = False
                    break
        if not encloses_all or depth != 0:
            break
        result = result[1:-1]
    return result


def _split_logical(tokens: tuple[str, ...], operator: str) -> list[tuple[str, ...]]:
    parts: list[tuple[str, ...]] = []
    depth = 0
    start = 0
    for index, token in enumerate(tokens):
        if token in {"(", "["}:
            depth += 1
        elif token in {")", "]"}:
            depth -= 1
        elif depth == 0 and token == operator:
            parts.append(tokens[start:index])
            start = index + 1
    if parts:
        parts.append(tokens[start:])
    return parts


def _canonical_predicate(tokens: tuple[str, ...]) -> tuple[str, ...]:
    semantic = [
        "trim" if token == "btrim" else token
        for token in tokens
        if token not in {"(", ")", "[", "]", ","}
    ]
    if "trim" in semantic:
        semantic = [token for token in semantic if token not in {"both", "from"}]

    # PostgreSQL deparses IN as = ANY(ARRAY[...]) and NOT IN as <> ALL(...).
    if "array" in semantic:
        array_index = semantic.index("array")
        for quantifier, comparison, membership in (
            ("any", "=", ("in",)),
            ("all", "!=", ("not", "in")),
            ("all", "<>", ("not", "in")),
        ):
            if quantifier not in semantic[:array_index]:
                continue
            quantifier_index = semantic.index(quantifier)
            if quantifier_index == 0 or semantic[quantifier_index - 1] != comparison:
                continue
            semantic = [
                *semantic[: quantifier_index - 1],
                *membership,
                *semantic[array_index + 1 :],
            ]
            break
    return tuple("!=" if token == "<>" else token for token in semantic)


def _canonical_check_tokens(tokens: tuple[str, ...]) -> CheckSignature:
    stripped = _strip_outer_tokens(tokens)
    for operator in ("or", "and"):
        parts = _split_logical(stripped, operator)
        if parts:
            return (operator, *(_canonical_check_tokens(part) for part in parts))
    if stripped and stripped[0] == "not":
        return ("not", _canonical_check_tokens(stripped[1:]))
    return ("predicate", *_canonical_predicate(stripped))


def _check_signature(value: object, *, table_name: str) -> CheckSignature:
    normalized = _normalize_sql(value, table_name=table_name)
    tokens = tuple(
        token if token.startswith("'") else token.lower()
        for token in _CHECK_TOKEN.findall(normalized)
    )
    return _canonical_check_tokens(tokens)


def _expected_check_constraints(
    table: sa.Table,
    connection: Connection,
) -> dict[str, CheckSignature]:
    result: dict[str, CheckSignature] = {}
    for constraint in table.constraints:
        if not isinstance(constraint, CheckConstraint):
            continue
        rendered = constraint.sqltext.compile(
            dialect=connection.dialect,
            compile_kwargs={"literal_binds": True},
        )
        result[constraint.name or ""] = _check_signature(
            rendered,
            table_name=table.name,
        )
    return result


def _actual_check_constraints(
    inspector: sa.Inspector,
    table_name: str,
) -> dict[str, CheckSignature]:
    return {
        str(item.get("name") or ""): _check_signature(
            item.get("sqltext"),
            table_name=table_name,
        )
        for item in inspector.get_check_constraints(table_name)
    }


def _expected_primary_key(table: sa.Table) -> tuple[str, ...]:
    constraint = next(
        item for item in table.constraints if isinstance(item, PrimaryKeyConstraint)
    )
    return tuple(column.name for column in constraint.columns)


def _expected_foreign_keys(table: sa.Table) -> set[tuple[Any, ...]]:
    result: set[tuple[Any, ...]] = set()
    for constraint in table.constraints:
        if not isinstance(constraint, ForeignKeyConstraint):
            continue
        result.add(
            (
                constraint.name or "",
                tuple(column.name for column in constraint.columns),
                tuple(element.target_fullname for element in constraint.elements),
                (constraint.ondelete or "").upper(),
                (constraint.onupdate or "").upper(),
            )
        )
    return result


def _actual_foreign_keys(inspector: sa.Inspector, table_name: str) -> set[tuple[Any, ...]]:
    result: set[tuple[Any, ...]] = set()
    for item in inspector.get_foreign_keys(table_name):
        remote = tuple(
            f"{item['referred_table']}.{column}"
            for column in item.get("referred_columns") or ()
        )
        options = item.get("options") or {}
        result.add(
            (
                str(item.get("name") or ""),
                tuple(item.get("constrained_columns") or ()),
                remote,
                str(options.get("ondelete") or "").upper(),
                str(options.get("onupdate") or "").upper(),
            )
        )
    return result


def _foreign_keys_equivalent(
    expected: set[tuple[Any, ...]],
    actual: set[tuple[Any, ...]],
) -> bool:
    def canonical(item: tuple[Any, ...], expected_names: set[str]) -> tuple[Any, ...]:
        name, *rest = item
        return (name if name in expected_names else "", *rest)

    names = {str(item[0]) for item in expected if item[0]}
    return {canonical(item, names) for item in expected} == {
        canonical(item, names) for item in actual
    }


def _expected_unique_keys(
    table: sa.Table,
    dialect_name: str,
) -> set[tuple[str, tuple[str, ...]]]:
    constraints = {
        (constraint.name or "", tuple(column.name for column in constraint.columns))
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    indexes = {
        (index.name or "", tuple(expression.name for expression in index.expressions))
        for index in table.indexes
        if index.unique
        and not _normalize_sql(
            index.dialect_options[dialect_name].get("where"),
            table_name=table.name,
        )
    }
    return constraints | indexes


def _actual_unique_keys(
    inspector: sa.Inspector,
    table_name: str,
    dialect_name: str,
) -> set[tuple[str, tuple[str, ...]]]:
    constraints = {
        (str(item.get("name") or ""), tuple(item.get("column_names") or ()))
        for item in inspector.get_unique_constraints(table_name)
    }
    indexes = {
        (str(item.get("name") or ""), tuple(item.get("column_names") or ()))
        for item in inspector.get_indexes(table_name)
        if item.get("unique")
        and not _normalize_sql(
            (item.get("dialect_options") or {}).get(f"{dialect_name}_where"),
            table_name=table_name,
        )
    }
    # A named full unique index and a named unique constraint are equivalent
    # enforcement primitives across historical SQLite/PostgreSQL upgrades.
    return constraints | indexes


def _expected_indexes(table: sa.Table, dialect_name: str) -> set[tuple[Any, ...]]:
    result: set[tuple[Any, ...]] = set()
    for index in table.indexes:
        where = index.dialect_options[dialect_name].get("where")
        normalized_where = _normalize_sql(where, table_name=table.name)
        if index.unique and not normalized_where:
            continue
        result.add(
            (
                index.name or "",
                tuple(expression.name for expression in index.expressions),
                bool(index.unique),
                normalized_where,
            )
        )
    return result


def _actual_indexes(
    inspector: sa.Inspector,
    table_name: str,
    dialect_name: str,
) -> set[tuple[Any, ...]]:
    result: set[tuple[Any, ...]] = set()
    for item in inspector.get_indexes(table_name):
        if item.get("duplicates_constraint"):
            continue
        dialect_options = item.get("dialect_options") or {}
        where = dialect_options.get(f"{dialect_name}_where")
        normalized_where = _normalize_sql(where, table_name=table_name)
        if item.get("unique") and not normalized_where:
            continue
        result.add(
            (
                str(item.get("name") or ""),
                tuple(item.get("column_names") or ()),
                bool(item.get("unique")),
                normalized_where,
            )
        )
    return result


def _supplemental_mismatches(
    connection: Connection,
    metadata: sa.MetaData,
) -> list[str]:
    inspector = inspect(connection)
    mismatches: list[str] = []
    for table_name in sorted(BASELINE_TABLE_NAMES):
        table = metadata.tables[table_name]
        actual_pk = tuple(inspector.get_pk_constraint(table_name).get("constrained_columns") or ())
        if actual_pk != _expected_primary_key(table):
            mismatches.append(f"PRIMARY_KEY:{table_name}")
        if not _foreign_keys_equivalent(
            _expected_foreign_keys(table),
            _actual_foreign_keys(inspector, table_name),
        ):
            mismatches.append(f"FOREIGN_KEY:{table_name}")
        if _actual_unique_keys(
            inspector,
            table_name,
            connection.dialect.name,
        ) != _expected_unique_keys(table, connection.dialect.name):
            mismatches.append(f"UNIQUE:{table_name}")
        if _actual_indexes(inspector, table_name, connection.dialect.name) != _expected_indexes(
            table,
            connection.dialect.name,
        ):
            mismatches.append(f"INDEX:{table_name}")
        if _actual_check_constraints(inspector, table_name) != _expected_check_constraints(
            table,
            connection,
        ):
            mismatches.append(f"CHECK:{table_name}")
    if connection.dialect.name == "postgresql":
        installed = connection.execute(
            sa.text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        ).scalar_one()
        if not installed:
            mismatches.append("PGVECTOR_EXTENSION")
    return mismatches


def _alembic_mismatches(diffs: list[Any]) -> list[str]:
    """Keep column/type/default drift; supplemental checks own key/index drift."""

    supplemental_operations = {
        "add_constraint",
        "add_fk",
        "add_index",
        "remove_constraint",
        "remove_fk",
        "remove_index",
    }
    result: list[str] = []
    for diff in diffs:
        if isinstance(diff, list):
            result.extend(_alembic_mismatches(diff))
            continue
        operation = str(diff[0]) if isinstance(diff, tuple) and diff else "GROUP"
        if operation not in supplemental_operations:
            result.append(f"ALEMBIC:{operation}")
    return result


def validate_baseline_schema(connection: Connection) -> SchemaValidation:
    """Compare tables, columns, types, keys, indexes, and checks without writes."""

    inspector = inspect(connection)
    actual_tables = set(inspector.get_table_names()) - {"alembic_version"}
    if not actual_tables:
        return SchemaValidation(
            matches=False,
            is_empty=True,
            business_table_count=0,
            mismatches=("SCHEMA_EMPTY",),
        )
    if actual_tables != set(BASELINE_TABLE_NAMES):
        return SchemaValidation(
            matches=False,
            is_empty=False,
            business_table_count=len(actual_tables),
            mismatches=("TABLE_SET",),
        )

    metadata = build_baseline_metadata(connection.dialect.name)
    context = MigrationContext.configure(
        connection,
        opts={
            "compare_type": True,
            "compare_server_default": True,
            "include_object": (
                lambda _object, name, _type, _reflected, _compare_to: name
                != "alembic_version"
            ),
        },
    )
    alembic_diffs = compare_metadata(context, metadata)
    mismatches = _alembic_mismatches(alembic_diffs)
    mismatches.extend(_supplemental_mismatches(connection, metadata))
    stable = tuple(sorted(set(mismatches)))
    return SchemaValidation(
        matches=not stable,
        is_empty=False,
        business_table_count=len(actual_tables),
        mismatches=stable,
    )


__all__ = ["SchemaValidation", "validate_baseline_schema"]
