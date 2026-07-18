"""
Centralized configuration for the Bank Statement Analyzer.
All values can be overridden via environment variables, so multiple
isolated instances (per-user, per-year, tests) don't require code edits.
"""
import os

# --- Storage locations -------------------------------------------------
DB_PATH = os.environ.get("BSA_DB_PATH", "statements.db")
INPUT_FOLDER = os.environ.get("BSA_INPUT_FOLDER", "InputStatements")
BANK_FORMATS_DIR = os.environ.get(
    "BSA_BANK_FORMATS_DIR",
    os.path.join(os.path.dirname(__file__), "parsers", "bank_formats"),
)
DEFAULT_RULES_FILE = os.environ.get(
    "BSA_DEFAULT_RULES_FILE",
    os.path.join(os.path.dirname(__file__), "data", "default_rules.json"),
)

RULES_FILE = os.environ.get(
    "BSA_RULES_FILE",
    os.path.join(os.path.dirname(__file__), "data", "rules.json"),
)

# --- Import defaults -----------------------------------------------------
DEFAULT_ACCOUNT = os.environ.get("BSA_DEFAULT_ACCOUNT", "Default_account")
# None => parser-detected bank name is authoritative unless a caller
# explicitly forces an override (e.g. bulk-importing a folder known to be
# all one bank).
DEFAULT_BANK_OVERRIDE = os.environ.get("BSA_DEFAULT_BANK_OVERRIDE") or None

# --- Transfer matching -----------------------------------------------------
DEFAULT_AMOUNT_TOLERANCE = float(os.environ.get("BSA_AMOUNT_TOLERANCE", "1.0"))
CONFIDENCE_FULL_MATCH = int(os.environ.get("BSA_CONFIDENCE_FULL_MATCH", "100"))
CONFIDENCE_PARTIAL_MATCH = int(os.environ.get("BSA_CONFIDENCE_PARTIAL_MATCH", "90"))

# --- Rule suggestions ---------------------------------------------------
RULE_SUGGESTION_MIN_OCCURRENCES = int(os.environ.get("BSA_RULE_SUGGESTION_MIN_OCCURRENCES", "3"))