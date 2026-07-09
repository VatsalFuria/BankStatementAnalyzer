"""
Shared enums/constants used across parsers, rule engine, transfer matcher,
and export — eliminates duplicated, typo-prone string literals.
"""
from enum import Enum


class DrCr(str, Enum):
    DEBIT = "DR"
    CREDIT = "CR"


class CategorySource(str, Enum):
    RULE = "rule"
    MANUAL = "manual"


class MatchStatus(str, Enum):
    SUGGESTED = "suggested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class MatchOp(str, Enum):
    CONTAINS = "contains"
    STARTSWITH = "startswith"
    REGEX = "regex"
    EQUALS = "equals"


class CategoryType(str, Enum):
    """Groups categories for reporting (e.g. the Income Summary sheet)."""
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    UNSPECIFIED = "unspecified"


# Payment modes recognized in transaction descriptions/references.
# Shared by parsers (to tag payment_mode) and rule_engine (to seed matching
# rules) so the two can't drift out of sync when a new mode is added.
PAYMENT_MODE_KEYWORDS = ["NEFT", "IMPS", "UPI", "RTGS"]