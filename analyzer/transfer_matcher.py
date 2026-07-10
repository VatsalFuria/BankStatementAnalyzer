import re
import uuid
from difflib import SequenceMatcher

from analyzer.database import db_session
from analyzer.config import DEFAULT_AMOUNT_TOLERANCE
from analyzer.constants import DrCr, MatchStatus, CategoryType, CategorySource

# Below this combined score (0-100) we don't even suggest a match — same
# date + same amount alone is too common a coincidence (rent, recurring
# bills, round-number payments) to call it a transfer on its own.
MIN_MATCH_SCORE = 35

# Alnum runs of 5+ chars are treated as possible reference/UTR fragments —
# these tend to survive even when each bank formats the rest of the
# narration completely differently.
_TOKEN_RE = re.compile(r"[A-Z0-9]{5,}")


def _tokens(*texts, exclude=()):
    combined = " ".join((t or "") for t in texts).upper()
    found = set(_TOKEN_RE.findall(combined))
    return found - set(exclude)


def _description_similarity(a, b):
    return SequenceMatcher(None, (a or "").upper().strip(), (b or "").upper().strip()).ratio()


def _score_pair(row):
    """Score a candidate pair that already passed the SQL-level hard
    filters (same date, amount in tolerance, opposite dr/cr, different
    account, compatible payment_mode). Returns (score 0-100, reasons)."""
    score, reasons = 0, []

    if abs(row["debit_amount"] - row["credit_amount"]) < 0.01:
        score += 35
        reasons.append("exact amount match")
    else:
        score += 20
        reasons.append("amount within tolerance")

    if row["debit_mode"] and row["credit_mode"] and row["debit_mode"] == row["credit_mode"]:
        score += 25
        reasons.append(f"same payment mode ({row['debit_mode']})")

    # Both txns share the txn_date already (by SQL join) — exclude the
    # date itself so a coincidentally-embedded date stamp doesn't get
    # counted as a "shared reference".
    date_variants = {row["txn_date"], row["txn_date"].replace("-", "")}
    shared = _tokens(row["debit_ref"], row["debit_desc"], exclude=date_variants) & \
             _tokens(row["credit_ref"], row["credit_desc"], exclude=date_variants)

    if shared:
        score += 30
        reasons.append(f"shared reference token(s): {', '.join(sorted(shared))[:60]}")
    else:
        sim = _description_similarity(row["debit_desc"], row["credit_desc"])
        if sim > 0.3:
            score += round(sim * 20)
            reasons.append(f"description similarity {sim:.0%}")

    return min(score, 100), reasons


def find_transfers(new_import_id: str | None = None, amount_tolerance: float | None = None):
    """
    Find self-transfer pairs across different accounts: same date, amount
    within tolerance, opposite dr/cr, compatible payment_mode — filtered
    in SQL so the DB does the heavy lifting instead of an O(n*m) Python
    scan. Candidates are then scored (payment mode, shared reference
    tokens, description similarity) and assigned greedily, best score
    first, so a debit can't get stuck on a weak match found earlier in
    iteration order.
    """
    if amount_tolerance is None:
        amount_tolerance = DEFAULT_AMOUNT_TOLERANCE

    query = """
        SELECT
            d.txn_id AS debit_id, d.account AS debit_account, d.txn_date,
            d.amount AS debit_amount, d.payment_mode AS debit_mode,
            d.description AS debit_desc, d.reference AS debit_ref,
            d.category AS debit_category, d.category_src AS debit_category_src,
            c.txn_id AS credit_id, c.account AS credit_account,
            c.amount AS credit_amount, c.payment_mode AS credit_mode,
            c.description AS credit_desc, c.reference AS credit_ref,
            c.category AS credit_category, c.category_src AS credit_category_src
        FROM transactions d
        JOIN transactions c
            ON d.txn_date = c.txn_date
           AND d.account != c.account
           AND ABS(d.amount - c.amount) <= ?
           AND (d.payment_mode IS NULL OR c.payment_mode IS NULL OR d.payment_mode = c.payment_mode)
        WHERE d.dr_cr = ? AND c.dr_cr = ?
          AND d.match_id IS NULL AND c.match_id IS NULL
    """
    params = [amount_tolerance, DrCr.DEBIT.value, DrCr.CREDIT.value]

    # Cross-import matching matters (per the original comment) — so if an
    # import_id is given, we widen to "at least one side is from this
    # import" rather than requiring BOTH sides to share it, which would
    # only ever catch transfers where both legs were imported together.
    if new_import_id:
        query += " AND (d.import_id = ? OR c.import_id = ?)"
        params += [new_import_id, new_import_id]

    with db_session(commit=False) as conn:
        rows = conn.execute(query, params).fetchall()
        category_types = {
            r["category"]: r["category_type"]
            for r in conn.execute("SELECT category, category_type FROM category_types").fetchall()
        }

    def _is_manually_excluded(category, category_src):
        # Respect an explicit human categorization that isn't Transfer —
        # don't suggest a transfer link for something a user has already
        # told the app is Rent/Salary/Shopping/etc. Rule-based or unset
        # categories are left alone; most real transfers get auto-tagged
        # "Transfer" by the NEFT/IMPS/UPI default rule anyway, which is a
        # positive signal, not a reason to exclude.
        if category_src != CategorySource.MANUAL.value:
            return False
        ctype = category_types.get(category)
        return ctype not in (None, CategoryType.TRANSFER.value, CategoryType.UNSPECIFIED.value)

    candidates = []
    for row in rows:
        if _is_manually_excluded(row["debit_category"], row["debit_category_src"]):
            continue
        if _is_manually_excluded(row["credit_category"], row["credit_category_src"]):
            continue
        score, reasons = _score_pair(row)
        if score >= MIN_MATCH_SCORE:
            candidates.append((score, reasons, row))

    # Best matches win first; each txn can only be used once on either side.
    candidates.sort(key=lambda x: x[0], reverse=True)

    used_debits, used_credits = set(), set()
    results, match_rows, debit_updates, credit_updates = [], [], [], []

    for score, reasons, row in candidates:
        d_id, c_id = row["debit_id"], row["credit_id"]
        if d_id in used_debits or c_id in used_credits:
            continue
        used_debits.add(d_id)
        used_credits.add(c_id)

        match_id = str(uuid.uuid4())
        match_rows.append((match_id, d_id, c_id, score, MatchStatus.SUGGESTED.value))
        debit_updates.append((match_id, d_id))
        credit_updates.append((match_id, c_id))
        results.append({
            "match_id": match_id, "debit": row, "credit": row,
            "confidence": score, "reasons": reasons,
        })

    with db_session() as conn:
        conn.executemany(
            "INSERT INTO matches (match_id, debit_txn, credit_txn, confidence, status) VALUES (?, ?, ?, ?, ?)",
            match_rows,
        )
        conn.executemany("UPDATE transactions SET match_id=? WHERE txn_id=?", debit_updates)
        conn.executemany("UPDATE transactions SET match_id=? WHERE txn_id=?", credit_updates)

    return results