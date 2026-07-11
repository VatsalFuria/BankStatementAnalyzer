# Bank Statement Analyzer

A Python application for importing, categorizing, and analyzing bank statements across multiple accounts and banks. Features rule-based transaction categorization, self-transfer detection, and an interactive GUI.

---

## Project Overview

This tool helps you:

- **Import** bank statements — currently XLSX
- **Categorize** transactions using customizable rules
- **Detect** self-transfers between your accounts
- **Consolidate** statements from multiple banks and accounts in one import batch, each with its own parser and account
- **Export** analyzed data to Excel with summaries and insights

---

## File Structure & Roles

### Core Application Files

| File            | Role                                                                        |
| --------------- | --------------------------------------------------------------------------- |
| **main_gui.py** | PySide6 GUI application with tabs for Import, Review, Transfers, and Export |
| **setup_db.py** | Database initialization and default rules seeding script                    |

### Database & Models

| File                           | Role                                                                                                                          |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| **analyzer/database.py**       | SQLite connection, schema init/migration, `db_session` context manager, and `reset_database()`                                |
| **analyzer/models.py**         | `StandardTransaction` dataclass — the canonical format all parsers produce                                                    |
| **analyzer/config.py**         | Centralized, env-overridable configuration (DB path, input folder, matching tolerances, etc.)                                 |
| **analyzer/constants.py**      | Shared enums (`DrCr`, `CategorySource`, `MatchStatus`, `MatchOp`, `CategoryType`)                 |
| **analyzer/exceptions.py**     | App-specific exception types (`ParserNotFoundError`, `ParseError`, `DuplicateImportError`) so the GUI can show clean messages |
| **analyzer/logging_config.py** | Rotating file + console logger, also piped into the GUI status bar                                                            |
| **analyzer/repository.py**     | Single place for read queries and simple status writes, used by the GUI                                                       |

### Parsing & Import

| File                                          | Role                                                                                                                                                                                 |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **analyzer/parsers/base_parser.py**           | Abstract `BaseParser`;  
                                                                  |
| **analyzer/parsers/**init**.py**              | Parser discovery (`discover_parsers()`, `get_parser_for_file()`, `get_parser_choices()`)                                                                                             |
| **analyzer/base_configurable_parser.py**      | JSON-config-driven Excel parser used by most banks (see `parsers/bank_formats/*.json`)                                                                                               |
| **analyzer/parsers/hdfc_parser.py**           | HDFC-specific `ConfigurableExcelParser` subclass, pointed at `hdfc.json`                                                                                                             |
| **analyzer/parsers/bank_formats/hdfc.json**   | Column mapping for HDFC's Excel export                                                                                                                                               |
| **analyzer/parsers/example_custom_parser.py** | Template for banks whose export doesn't fit the simple config format (merged cells, shifting columns) |
| **analyzer/utils.py**                         | `parse_amount()` — tolerant numeric parsing for messy bank export cells                                                                                                              |
| **analyzer/import_manager.py**                | Orchestrates parsing, per-file/account dedup, and bulk insert                                                                                                                        |

### Rules & Categorization

| File                                 | Role                                                                                                                  |
| ------------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| **analyzer/rule_engine.py**          | Rule matching (`test_rule`), application (`apply_rules`, `reapply_all_rules`), manual overrides, default rule seeding |
| **analyzer/categories.py**           | Maps a category name to a `CategoryType` (income/expense/transfer/unspecified), independent of how it was assigned    |
| **analyzer/data/default_rules.json** | Seed rule definitions, editable without a code change                                                                 |

### Transfer Matching

| File                             | Role                                                                                              |
| -------------------------------- | ------------------------------------------------------------------------------------------------- |
| **analyzer/transfer_matcher.py** | `find_transfers()` — matches debit/credit pairs across accounts by date, amount, and payment mode |

### Export

| File                   | Role                                                                                                                       |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| **analyzer/export.py** | Exports to a multi-sheet workbook: Consolidated, per-bank, Self Transfers, Income Summary, Uncategorized, Category Summary |

### Configuration & Data

| File                     | Role                                                              |
| ------------------------ | ----------------------------------------------------------------- |
| **requirements.txt**     | `pandas`, `openpyxl`, `xlrd` (for legacy `.xls`), `PySide6`       |
| **generate_sample.py**   | Creates a sample HDFC statement (Excel) for testing               |
| **test_import.py**       | Test script demonstrating import → categorization workflow        |
| **tests/test_export.py** | Unit test for the empty-export guard                              |
| **.gitignore**           | Excludes virtual env, cache, IDE files, logs, and `statements.db` |

---

## Setup Instructions

### 1. Prerequisites

- Python 3.10+
- pip or poetry

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Initialize Database & Rules (Optional)

```bash
python setup_db.py
```

Creates `statements.db` and seeds default categorization rules.

### 4. Generate Sample Data (Optional)

```bash
python generate_sample.py
```

Creates `sample_hdfc.xlsx` with 5 sample transactions for testing.

---

## Usage

### GUI Usage

```bash
python main_gui.py
```

**Import tab:** click "Import Statement Files" and select one or more files. A dialog then lets you set the **bank format** and **account** for _each file individually_ — this is the intended way to bring in several different banks' statements in one batch. Leave "Bank format" on Auto-detect to let the app guess from the file's columns. After import, rules are applied and self-transfer detection runs automatically.

Other tabs:

- **Review Uncategorized** — view and manually categorize leftover transactions, either as a one-off or as a new rule
- **Transfers** — accept/reject auto-detected self-transfers
- **Export** — save analyzed data to an Excel workbook


## Database Schema

_(unchanged — see `analyzer/database.py` for authoritative schema: `transactions`, `import_log`, `rules`, `manual_overrides`, `matches`, `category_types`)_

---

## Extending the System

### Adding a New Bank Parser

Most banks can be supported with just a JSON column mapping — no Python needed:

1. Add `analyzer/parsers/bank_formats/mybank.json`:

```json
{
  "bank_name": "MyBank",
  "file_extensions": [".xlsx"],
  "detect_column": "Description",
  "columns": {
    "date": "Txn Date",
    "description": "Description",
    "reference": "Ref No",
    "withdrawal": "Debit",
    "deposit": "Credit",
    "balance": "Balance"
  }
}
```

2. Add `analyzer/parsers/mybank_parser.py`:

```python
import os
from analyzer.base_configurable_parser import ConfigurableExcelParser
from analyzer.config import BANK_FORMATS_DIR

class MyBankParser(ConfigurableExcelParser):
    config_path = os.path.join(BANK_FORMATS_DIR, "mybank.json")
```

It'll be auto-discovered and appear in each file's format dropdown on next launch.


### Adding Custom Categorization Rules

```python
from analyzer.rule_engine import add_rule

add_rule(
  priority=priority,
  match_field="description",
  match_op=result["match_op"],
  match_value=result["match_value"],
  category=result["category"],
  category_type=result["category_type"],
  source="manual",
  dr_cr=result["dr_cr"],
)
```

---

## Known Limitations

- Parser discovery is cached per process — adding a new parser file while the GUI is running won't show it until restart.
- `analyzer/repository.py`'s `get_transactions_display()` (debit/credit as separate columns) isn't wired to any GUI tab yet — there's no "all transactions" view, only Uncategorized and per-export sheets.
- Regex rules (`match_op: "regex"`) have no validation in the GUI — an invalid pattern is silently treated as "no match" rather than surfaced as an error.
- Rows with both withdrawal and deposit blank/zero are now skipped as likely balance/heading rows rather than imported as spurious 0-amount transactions — if your bank format legitimately has zero-amount transactions, this will drop them too.


