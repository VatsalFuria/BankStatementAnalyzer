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
    TRANSFER = "transfer"


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
    """Groups categories for reporting (e.g. the Income Summary sheet) and,
    increasingly, maps straight onto ITR schedules/sections. Values are
    never renamed or removed once shipped — existing DBs store the string
    value, so renaming would silently orphan old rows. New heads are only
    ever appended.
    """
    # --- Original, generic buckets ----------------------------------------
    INCOME_DEFAULT = "income"
    INCOME_SALARY = "income_salary"
    INCOME_HOUSE = "income_house"
    INCOME_OTHER = "income_other_sources"
    CAPITAL_GAINS = "income_capital_gains"
    PROFIT_GAINS_BUSINESS_PROFESSION = "income_pgbp"
    INVESTMENT_80C = "investment_80c"
    HEALTH_INSURANCE_80D = "health_insurance_80d"
    EDUCATION_LOAN_80E = "education_loan_80e"
    DONATION_80G = "donation_80g"
    GIFT_RECEIVED = "gift_received"
    GIFT_GIVEN = "gift_given"
    FRIENDLY_LOAN = "friendly_loan"
    PERSONAL_EXPENSE = "expense"
    TRANSFER = "transfer"
    UNSPECIFIED = "unspecified"

    # --- Added: sharper ITR-head/section mapping ---------------------------
    INCOME_DIVIDEND = "income_dividend"                  # Schedule OS — dividends, split out because they get their own advance-tax treatment
    INTEREST_SAVINGS_80TTA = "interest_savings_80tta"    # Only savings-account interest qualifies for 80TTA/80TTB — FD interest doesn't
    HOME_LOAN_INTEREST_24B = "home_loan_interest_24b"    # Section 24(b), set off against income_house (capped 2L for self-occupied)
    HOME_LOAN_PRINCIPAL_80C = "home_loan_principal_80c"  # Sits inside the overall 80C cap — kept apart from generic 80C for clarity
    NPS_SELF_80CCD1B = "nps_80ccd1b"                     # Additional 50k, over and above the 80C cap
    RENT_PAID_HRA = "rent_paid_hra"                      # Feeds the HRA exemption calc — not a deduction by itself
    CAPITAL_MARKET_PURCHASE = "capital_market_purchase"  # Stocks/MF/bonds bought — cost basis for a future capital gain, NOT a deduction
    TAX_PAYMENT = "tax_payment"                          # Advance tax / self-assessment tax / GST challans
    TAX_REFUND = "tax_refund"                            # IT refund principal — not taxable (interest on it is; see income_other_sources)
    LOAN_PROCEEDS = "loan_proceeds"                      # Loan disbursement received — not income
    LOAN_EMI = "loan_emi"                                # EMI outflow where the statement doesn't split principal/interest
    CASH_WITHDRAWAL = "cash_withdrawal"                  # Cash-flow only
    CREDIT_CARD_PAYMENT = "credit_card_payment"          # Cash-flow only — paying the bill isn't a second expense on top of the original spend
    BANK_CHARGES = "bank_charges"                        # Cash-flow only, not tax-relevant


# Payment modes recognized in transaction descriptions/references.
# Shared by parsers (to tag payment_mode) and rule_engine (to seed matching
# rules) so the two can't drift out of sync when a new mode is added.
# PAYMENT_MODE_KEYWORDS = ["NEFT", "IMPS", "UPI", "RTGS"]