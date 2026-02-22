# -*- coding: utf-8 -*-
"""
Database administration router.
Provides generic CRUD endpoints for all SQLite tables in the project database.
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/database", tags=["database"])

# Use the same database path as other storage modules
DB_PATH = Path.home() / ".autoglm" / "chat.db"

# Columns that contain binary data and should not be sent to the frontend
BLOB_COLUMNS = {"image_data"}


@contextmanager
def _get_conn():
    """Get a database connection with context management."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _serialize_value(value):
    """Serialize a value for JSON response."""
    if isinstance(value, bytes):
        return f"[BLOB: {len(value)} bytes]"
    return value


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class RowData(BaseModel):
    """Request body for insert/update/delete operations."""
    data: dict
    primary_key: Optional[dict] = None  # For update/delete: {column: value}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/tables")
async def list_tables():
    """List all tables with row counts."""
    with _get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        tables = []
        for row in cursor.fetchall():
            name = row["name"]
            count = conn.execute(f'SELECT COUNT(*) as cnt FROM "{name}"').fetchone()["cnt"]
            tables.append({"name": name, "row_count": count})
        return {"tables": tables}


@router.get("/tables/{table_name}/schema")
async def get_table_schema(table_name: str):
    """Get column information for a table."""
    with _get_conn() as conn:
        cursor = conn.cursor()
        # Validate table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")

        cursor.execute(f'PRAGMA table_info("{table_name}")')
        columns = []
        for col in cursor.fetchall():
            columns.append({
                "cid": col["cid"],
                "name": col["name"],
                "type": col["type"],
                "notnull": bool(col["notnull"]),
                "default_value": col["dflt_value"],
                "pk": bool(col["pk"]),
            })
        return {"table": table_name, "columns": columns}


@router.get("/tables/{table_name}/rows")
async def get_table_rows(
    table_name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    search: str = Query("", description="Search across all text columns"),
    sort_by: str = Query("", description="Column to sort by"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
):
    """Get paginated rows with optional search and sorting."""
    with _get_conn() as conn:
        cursor = conn.cursor()
        # Validate table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")

        # Get column info
        cursor.execute(f'PRAGMA table_info("{table_name}")')
        columns = cursor.fetchall()
        col_names = [c["name"] for c in columns]

        # Validate sort column
        if sort_by and sort_by not in col_names:
            sort_by = ""

        # Build query
        params = []
        where_clause = ""
        if search:
            # Search across all text columns (skip BLOB)
            text_cols = [c["name"] for c in columns if c["name"] not in BLOB_COLUMNS]
            if text_cols:
                conditions = [f'CAST("{col}" AS TEXT) LIKE ?' for col in text_cols]
                where_clause = "WHERE " + " OR ".join(conditions)
                params = [f"%{search}%"] * len(text_cols)

        # Count
        count_sql = f'SELECT COUNT(*) as cnt FROM "{table_name}" {where_clause}'
        total = conn.execute(count_sql, params).fetchone()["cnt"]

        # Order
        order_clause = ""
        if sort_by:
            direction = "DESC" if sort_order == "desc" else "ASC"
            order_clause = f'ORDER BY "{sort_by}" {direction}'
        else:
            # Default: order by first column descending for recent-first
            order_clause = f'ORDER BY rowid DESC'

        # Pagination
        offset = (page - 1) * page_size
        data_sql = f'SELECT * FROM "{table_name}" {where_clause} {order_clause} LIMIT ? OFFSET ?'
        params.extend([page_size, offset])

        cursor.execute(data_sql, params)
        rows = []
        for row in cursor.fetchall():
            row_dict = {}
            for col_name in col_names:
                val = row[col_name]
                row_dict[col_name] = _serialize_value(val)
            rows.append(row_dict)

        return {
            "table": table_name,
            "rows": rows,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }


@router.post("/tables/{table_name}/rows")
async def insert_row(table_name: str, body: RowData):
    """Insert a new row into a table."""
    with _get_conn() as conn:
        cursor = conn.cursor()
        # Validate table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")

        # Get valid columns
        cursor.execute(f'PRAGMA table_info("{table_name}")')
        valid_cols = {c["name"] for c in cursor.fetchall()}

        # Filter to valid columns only
        data = {k: v for k, v in body.data.items() if k in valid_cols}
        if not data:
            raise HTTPException(status_code=400, detail="No valid columns provided")

        cols = ", ".join(f'"{c}"' for c in data.keys())
        placeholders = ", ".join("?" for _ in data)
        values = []
        for v in data.values():
            # Store complex values as JSON
            if isinstance(v, (dict, list)):
                values.append(json.dumps(v, ensure_ascii=False))
            else:
                values.append(v)

        try:
            cursor.execute(
                f'INSERT INTO "{table_name}" ({cols}) VALUES ({placeholders})',
                values,
            )
            return {"success": True, "message": "Row inserted successfully", "rowid": cursor.lastrowid}
        except sqlite3.IntegrityError as e:
            raise HTTPException(status_code=409, detail=f"Integrity error: {e}")
        except sqlite3.OperationalError as e:
            raise HTTPException(status_code=400, detail=f"Operation error: {e}")


@router.put("/tables/{table_name}/rows")
async def update_row(table_name: str, body: RowData):
    """Update a row identified by primary key."""
    if not body.primary_key:
        raise HTTPException(status_code=400, detail="primary_key is required for update")

    with _get_conn() as conn:
        cursor = conn.cursor()
        # Validate table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")

        # Get valid columns
        cursor.execute(f'PRAGMA table_info("{table_name}")')
        valid_cols = {c["name"] for c in cursor.fetchall()}

        # Filter data to valid columns
        data = {k: v for k, v in body.data.items() if k in valid_cols}
        if not data:
            raise HTTPException(status_code=400, detail="No valid columns provided")

        # Build SET clause
        set_parts = []
        values = []
        for k, v in data.items():
            set_parts.append(f'"{k}" = ?')
            if isinstance(v, (dict, list)):
                values.append(json.dumps(v, ensure_ascii=False))
            else:
                values.append(v)

        # Build WHERE clause from primary key
        where_parts = []
        for k, v in body.primary_key.items():
            if k not in valid_cols:
                raise HTTPException(status_code=400, detail=f"Invalid primary key column: {k}")
            where_parts.append(f'"{k}" = ?')
            values.append(v)

        set_clause = ", ".join(set_parts)
        where_clause = " AND ".join(where_parts)

        try:
            cursor.execute(
                f'UPDATE "{table_name}" SET {set_clause} WHERE {where_clause}',
                values,
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Row not found")
            return {"success": True, "message": "Row updated successfully", "rows_affected": cursor.rowcount}
        except sqlite3.IntegrityError as e:
            raise HTTPException(status_code=409, detail=f"Integrity error: {e}")
        except sqlite3.OperationalError as e:
            raise HTTPException(status_code=400, detail=f"Operation error: {e}")


@router.delete("/tables/{table_name}/rows")
async def delete_row(table_name: str, body: RowData):
    """Delete a row identified by primary key."""
    if not body.primary_key:
        raise HTTPException(status_code=400, detail="primary_key is required for delete")

    with _get_conn() as conn:
        cursor = conn.cursor()
        # Validate table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")

        # Get valid columns
        cursor.execute(f'PRAGMA table_info("{table_name}")')
        valid_cols = {c["name"] for c in cursor.fetchall()}

        # Build WHERE clause from primary key
        where_parts = []
        values = []
        for k, v in body.primary_key.items():
            if k not in valid_cols:
                raise HTTPException(status_code=400, detail=f"Invalid primary key column: {k}")
            where_parts.append(f'"{k}" = ?')
            values.append(v)

        where_clause = " AND ".join(where_parts)

        try:
            cursor.execute(f'DELETE FROM "{table_name}" WHERE {where_clause}', values)
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Row not found")
            return {"success": True, "message": "Row deleted successfully", "rows_affected": cursor.rowcount}
        except sqlite3.OperationalError as e:
            raise HTTPException(status_code=400, detail=f"Operation error: {e}")
