"""
Single source of truth for "what type of category is this" (income /
expense / transfer / unspecified) — independent of *how* a transaction
got that category (rule match or manual override). This lets the
Income Summary export include manually-categorized transactions too,
not just ones assigned via a rule.
"""
from analyzer.database import get_connection
from analyzer.constants import CategoryType


def set_category_type(category: str, category_type: str = CategoryType.UNSPECIFIED.value):
    """Create or update the type for a category name (e.g. 'Salary' -> 'income')."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO category_types (category, category_type)
        VALUES (?, ?)
        ON CONFLICT(category) DO UPDATE SET category_type=excluded.category_type
    """, (category, category_type))
    conn.commit()
    conn.close()


def get_category_type(category: str) -> str:
    conn = get_connection()
    row = conn.execute(
        "SELECT category_type FROM category_types WHERE category=?", (category,)
    ).fetchone()
    conn.close()
    return row["category_type"] if row else CategoryType.UNSPECIFIED.value


def list_category_types():
    conn = get_connection()
    rows = conn.execute(
        "SELECT category, category_type FROM category_types ORDER BY category"
    ).fetchall()
    conn.close()
    return rows


def get_existing_categories():
    """
    Distinct category names seen so far, from both rules and manual
    overrides, for populating dropdowns (e.g. the Review tab's
    Categorize dialog) so users can reuse an existing category name
    instead of retyping it and accidentally creating a near-duplicate
    (e.g. "Food" vs "food" vs "Food ").
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT DISTINCT category FROM rules
        UNION
        SELECT DISTINCT category FROM manual_overrides
        ORDER BY category
    """).fetchall()
    conn.close()
    return [r["category"] for r in rows]