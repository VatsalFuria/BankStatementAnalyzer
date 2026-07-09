# Bank Statement Analyzer

A Python application for importing, categorizing, and analyzing bank statements across multiple accounts and banks. Features rule-based transaction categorization, self-transfer detection, and an interactive GUI.

---

## Project Overview

This tool helps you:

- **Import** bank statements from multiple formats (XLSX, CSV)
- **Categorize** transactions using customizable rules
- **Detect** self-transfers between your accounts
- **Consolidate** statements from multiple banks
- **Export** analyzed data to Excel with summaries and insights

---

## File Structure & Roles

### Core Application Files

| File            | Role                                                                        |
| --------------- | --------------------------------------------------------------------------- |
| **main.py**     | CLI entry point; imports a sample file and applies categorization rules     |
| **main_gui.py** | PySide6 GUI application with tabs for Import, Review, Transfers, and Export |
| **setup_db.py** | Database initialization and default rules seeding script                    |

### Database & Models

| File                     | Role                                                                                                                                             |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| **analyzer/database.py** | SQLite connection, schema initialization, and PRAGMA setup. Creates tables: `transactions`, `import_log`, `rules`, `manual_overrides`, `matches` |
| **analyzer/models.py**   | `StandardTransaction` dataclass defining the canonical format for all parsed transactions                                                        |

### Parsing & Import

| File                                | Role                                                                                                |
| ----------------------------------- | --------------------------------------------------------------------------------------------------- |
| **analyzer/parsers/base_parser.py** | Abstract base class (`BaseParser`) that all bank parsers inherit from                               |
| **analyzer/parsers/**init**.py**    | Parser discovery system; auto-loads all parser implementations and provides `get_parser_for_file()` |
| **analyzer/parsers/hdfc_parser.py** | Concrete HDFC bank statement parser (Excel format with Narration column)                            |
| **analyzer/import_manager.py**      | Orchestrates file parsing, deduplication, and bulk database insertion                               |

### Rules & Categorization

| File                        | Role                                                                                                                        |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **analyzer/rule_engine.py** | Rule matching logic (`test_rule()`), rule application (`apply_rules()`), manual override handling, and default rule seeding |

### Transfer Matching

| File                             | Role                                                                                                          |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| **analyzer/transfer_matcher.py** | Identifies self-transfers by matching debit/credit pairs across accounts using date, amount, and payment mode |

### Export

| File                   | Role                                                                                                                                    |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| **analyzer/export.py** | Exports analyzed transactions to multi-sheet Excel workbook with consolidated view, per-bank sheets, summaries, and uncategorized items |

### Configuration & Data

| File                   | Role                                                        |
| ---------------------- | ----------------------------------------------------------- |
| **requirements.txt**   | Python dependencies: `pandas`, `openpyxl`, `PySide6`        |
| **generate_sample.py** | Creates a sample HDFC statement (Excel) for testing         |
| **test_import.py**     | Test script demonstrating import → categorization workflow  |
| **.gitignore**         | Excludes virtual env, cache, IDE files, and `statements.db` |

---

## Setup Instructions

### 1. Prerequisites

- Python 3.8+
- pip or poetry

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Initialize Database & Rules

```bash
python setup_db.py
```

This creates:

- `statements.db` (SQLite database)
- Default categorization rules (Salary, Food, Shopping, Transfers, Interest, etc.)

### 4. Generate Sample Data (Optional)

```bash
python generate_sample.py
```

Creates `sample_hdfc.xlsx` with 5 sample transactions for testing.

---

## Usage

### CLI Usage

```bash
python main.py
```

Imports `sample_hdfc.xlsx`, categorizes transactions, and prints results.

### GUI Usage

```bash
python main_gui.py
```

Opens an interactive window with tabs:

- **Import**: Select and import statement files
- **Review Uncategorized**: View and manually categorize transactions
- **Transfers**: Confirm or reject auto-detected self-transfers
- **Export**: Save analyzed data to Excel workbook

### Testing

```bash
python test_import.py
```

Demonstrates the full workflow: database init → parser discovery → file import → rule application.

---

## Database Schema

### transactions

Core transaction records with categorization metadata.

```
txn_id, import_id, bank, account, txn_date, description, amount, dr_cr,
balance, reference, payment_mode, category, category_src, rule_id, match_id,
source_file, source_row
```

### import_log

History of imported files.

```
import_id (PK), filename, bank, account, imported_at, row_count
```

### rules

Categorization rules (priority-ordered).

```
id (PK), priority, match_field, match_op, match_value, category, source, created_at
```

### matches

Self-transfer pair matches.

```
match_id (PK), debit_txn (FK), credit_txn (FK), confidence, status
```

### manual_overrides

Manual category assignments.

```
txn_id (PK, FK), category, reason
```

---

## Extending the System

### Adding a New Bank Parser

1. Create `analyzer/parsers/mybank_parser.py`:

```python
from analyzer.parsers.base_parser import BaseParser
from analyzer.models import StandardTransaction

class MyBankParser(BaseParser):
    def can_parse(self, filepath: str) -> bool:
        # Return True if this parser can handle the file
        pass

    def parse(self, filepath: str) -> list[StandardTransaction]:
        # Parse file and return list of StandardTransaction objects
        pass
```

2. Save the file. The discovery system auto-loads it.

### Adding Custom Categorization Rules

In code:

```python
from analyzer.rule_engine import add_rule

add_rule(
    priority=11,
    match_field='description',
    match_op='contains',
    match_value='NETFLIX',
    category='Subscriptions'
)
```

Or manually insert into the `rules` table.

---

## Key Features

✅ **Multi-bank support** – Extensible parser architecture  
✅ **Rule-based categorization** – Priority-ordered matching with manual overrides  
✅ **Self-transfer detection** – Smart matching across accounts  
✅ **Duplicate prevention** – Import log deduplication  
✅ **Rich export** – Consolidated, per-bank, summary, and category sheets  
✅ **Interactive GUI** – PySide6 interface with tabs and action buttons  
✅ **Test-ready** – Sample data generator and test scripts included

---

## License & Notes

- Uses SQLite for persistence
- All transaction amounts stored as positive floats; sign determined by `dr_cr` field
- Payment modes (NEFT, IMPS, UPI) auto-detected from description/reference
- Rule matching is case-insensitive
- Supports regex patterns in rule matching

# TROUBLESHOOTING

Here's the complete map of this project's flows, broken into separate diagrams so each stays readable. I've marked gaps I noticed with ⚠ — places where a flow exists in the code but nothing currently triggers it, which are worth knowing about even outside the immediate bug.

---

## A. Master Overview — where every flow starts

```
                              ┌─────────────────────┐
                              │   ENTRY POINTS       │
                              └─────────────────────┘
                                        │
        ┌───────────────────┬──────────┴──────────┬───────────────────┐
        │                   │                     │                   │
        ▼                   ▼                     ▼                   ▼
  setup_db.py          main.py              main_gui.py         tests/test_export.py
  (one-time DB +       (CLI single           (interactive          (isolated DB,
   rule seeding)        import demo)           GUI app)             export only)
        │                   │                     │
        ▼                   ▼                     ▼
    [Flow B]            [Flow C-1]           [Flow G: GUI lifecycle]
                                                    │
                                        ┌───────────┼───────────┬────────────┐
                                        ▼           ▼           ▼            ▼
                                   ImportTab   ReviewTab   TransferTab   Export tab
                                   [Flow C-2]  [Flow E-2]  [Flow E-3]   [Flow F]
```

---

## B. Database Setup & Rule Seeding (`setup_db.py`)

```
setup_db.py
   │
   ├──► init_db()                                    [analyzer/database.py]
   │       │
   │       └─ CREATE TABLE IF NOT EXISTS ...
   │            transactions, import_log, rules,
   │            manual_overrides, matches, category_types
   │          (idempotent — safe to call repeatedly, never re-seeds rules)
   │
   └──► seed_default_rules()                          [analyzer/rule_engine.py]
           │
           ├──► _load_seed_rule_definitions()
           │       │
           │       ├─ open(config.DEFAULT_RULES_FILE)  ─► analyzer/data/default_rules.json
           │       │    ⚠ if file missing: except FileNotFoundError → returns []
           │       │      (silent — no error printed)
           │       │
           │       └─ append synthetic "Transfer" rules, one per entry in
           │          constants.PAYMENT_MODE_KEYWORDS (NEFT/IMPS/UPI/RTGS)
           │
           └──► for each rule definition: add_rule(...)
                   │
                   ├─ INSERT INTO rules (priority, match_field, match_op,
                   │                     match_value, category, source)
                   │
                   └─ if category_type given:
                        set_category_type(category, category_type)   [analyzer/categories.py]
                           └─ INSERT ... ON CONFLICT UPDATE → category_types table
                              (used only by export.py's Income Summary sheet —
                               does NOT affect whether a txn gets categorized)
```

---

## C. Import Pipeline — two entry points, one shared core

### C-1: CLI (`main.py`)

```
main.py  (__main__)
   │
   ├──► init_db()                          [analyzer/database.py]
   │
   ├──► import_file("sample_hdfc.xlsx",
   │                 account=DEFAULT_ACCOUNT)          ──► see [Flow C-core] below
   │
   └──► apply_rules()                      [analyzer/rule_engine.py] ──► see [Flow D]
        ⚠ ONLY if you added this call yourself — the original main.py
          stops after import_file() and never categorizes anything.
```

### C-2: GUI (`main_gui.py` → `ImportTab.import_file`)

```
User clicks "Import Statement Files"
   │
   ├──► QFileDialog.getOpenFileNames()  → filepaths[]
   ├──► QInputDialog.getText()          → account name (prompt, not hardcoded)
   │
   ├──► for each filepath:
   │       import_file(filepath, account=account)      ──► see [Flow C-core] below
   │
   ├──► apply_rules()                    [analyzer/rule_engine.py]     ──► see [Flow D]
   │       (called ONCE after all files import, not per-file)
   │
   └──► refresh_imported_files()
           └─ SELECT filename FROM import_log ORDER BY imported_at DESC
              → repopulate QListWidget
```

### C-core: `import_file()` — shared by both paths above

```
import_file(filepath, bank_override=None, account=None)   [analyzer/import_manager.py]
   │
   ├─ account ← DEFAULT_ACCOUNT if None          [analyzer/config.py]
   ├─ bank_override ← DEFAULT_BANK_OVERRIDE if None (usually stays None,
   │   so the detected parser's bank name is authoritative)
   │
   ├──► discover_parsers()   — ONLY on first-ever call (cached via
   │       function attribute import_file._parsers_loaded)
   │       │                                        [analyzer/parsers/__init__.py]
   │       ├─ pkgutil.iter_modules(parsers package dir)
   │       ├─ skip 'base_parser', '__init__'
   │       ├─ importlib.import_module() each remaining module
   │       └─ for each attr in dir(module):
   │            if isinstance(attr, type)
   │               and issubclass(attr, BaseParser)
   │               and attr is not BaseParser
   │               and attr.__module__ == module.__name__   ← the fix we made
   │            → instantiate, e.g. HDFCParser()
   │                  │
   │                  └──► ConfigurableExcelParser.__init__()
   │                            [analyzer/base_configurable_parser.py]
   │                        └─ json.load(config_path)
   │                             → analyzer/parsers/bank_formats/hdfc.json
   │
   ├─ conn.execute SELECT import_log WHERE filename/bank/account match
   │    → if found: print "already imported", return existing import_id (STOP HERE)
   │
   ├──► get_parser_for_file(filepath)
   │       └─ loop registered parsers, return first where .can_parse(filepath) is True
   │
   ├──► parser.parse(filepath)             [ConfigurableExcelParser.parse]
   │       ├─ pd.read_excel(filepath)
   │       └─ for each row: build StandardTransaction
   │            (category = None, category_src = None — always, at this stage)
   │
   ├─ apply bank_override / account to each txn (if bank_override given)
   │
   ├─ INSERT INTO transactions  (loop, one row per txn)
   ├─ INSERT INTO import_log    (one row, this import batch)
   │
   └─ return import_id
```

---

## D. Categorization Engine (`analyzer/rule_engine.py`)

This is the piece that's silent/invisible when broken — worth understanding on its own.

```
apply_rules(transaction_list=None)
   │
   ├──► load_rules()
   │       └─ SELECT * FROM rules ORDER BY priority ASC
   │          ⚠ if this returns [] → loop below runs 0 times,
   │            every transaction stays category=NULL. No error, no log.
   │
   ├─ txns ← transaction_list, OR:
   │    SELECT txn_id, description, bank, reference FROM transactions
   │    WHERE category IS NULL OR category_src != 'manual'
   │
   └─ for each txn:
        for each rule (in priority order):
           test_rule(rule, txn)
              ├─ pick text field (description / bank / reference)
              ├─ uppercase both text and match_value
              └─ apply match_op: contains / startswith / regex / equals
           │
           if True:
              → UPDATE transactions
                SET category=rule.category, category_src='rule', rule_id=rule.id
              → break (first match wins, remaining rules skipped for this txn)
```

```
reapply_all_rules()                     — NOT wired to any GUI button currently ⚠
   │
   ├─ UPDATE transactions SET category=NULL, category_src=NULL, rule_id=NULL
   │    WHERE category_src='rule'          (wipes rule-based categories only)
   │
   ├──► apply_rules()                      (re-run matching from scratch)
   │
   └──► apply_manual_overrides()
           └─ SELECT txn_id, category FROM manual_overrides
              → for each: UPDATE transactions SET category=..., category_src='manual'
                (re-applied LAST, so manual always wins over rules)
```

```
add_rule(priority, match_field, match_op, match_value, category,
         category_type=None, source='manual')
   │
   ├─ INSERT INTO rules (...)
   └─ if category_type: set_category_type(category, category_type)   [categories.py]
```

---

## E. Transfer Matching & Review

### E-1: The matching engine itself

```
find_transfers(new_import_id=None, amount_tolerance=None)   [analyzer/transfer_matcher.py]
   │
   ⚠ NOT CALLED FROM ANYWHERE IN main_gui.py OR main.py CURRENTLY.
     This is a complete, working function with no UI trigger wired to it.
     TransferTab only ever displays matches that already exist in the
     `matches` table — but nothing currently populates that table.
   │
   ├─ amount_tolerance ← config.DEFAULT_AMOUNT_TOLERANCE if None
   ├─ SELECT debits  WHERE dr_cr='DR' (+ import_id filter if given)
   ├─ SELECT credits WHERE dr_cr='CR' (+ import_id filter if given)
   │
   └─ nested loop (debit × credit):
        skip if same account / different date / amount outside tolerance /
             payment_mode mismatch / credit already matched
        │
        confidence = FULL (100) if both have payment_mode & match,
                     else PARTIAL (90)
        │
        ├─ INSERT INTO matches (match_id, debit_txn, credit_txn,
        │                       confidence, status='suggested')
        └─ UPDATE transactions SET match_id=... for both debit & credit rows
```

### E-2: Review Uncategorized tab (read-only currently)

```
ReviewTab.__init__() → refresh()
   │
   └─ SELECT txn_id, bank, account, txn_date, description, amount, dr_cr
     FROM transactions WHERE category IS NULL ORDER BY txn_date DESC
     → populate QTableWidget
        ⚠ No action button exists here to actually assign a category —
          this tab can show you the problem but not fix it from the GUI.
          (manual_overrides table has no write-path in the GUI at all yet)
```

### E-3: Transfers tab

```
TransferTab.__init__() → refresh()
   │
   └─ SELECT m.match_id, d.txn_date, d.amount, from_acc, to_acc,
            m.confidence, m.status
     FROM matches m JOIN transactions d/c
     WHERE m.status = 'suggested'
     → populate QTableWidget, with Accept/Reject buttons per row
        (lambda checked, m=match: ... — default-arg trick to avoid
         Python's late-binding closure bug in the loop)

User clicks "Accept" on a row
   │
   └─► accept_match(match_id)
           ├─ UPDATE matches SET status='accepted' WHERE match_id=?
           └─► refresh()   (re-run the query above)

User clicks "Reject" on a row
   │
   └─► reject_match(match_id)
           ├─ UPDATE matches SET status='rejected' WHERE match_id=?
           ├─ UPDATE transactions SET match_id=NULL WHERE match_id=?
           └─► refresh()
```

---

## F. Export Flow (`analyzer/export.py`)

```
User clicks "Export Workbook"
   │
   └─► MainWindow.export()
           │
           ├──► get_export_summary()
           │       ├─ COUNT(*) transactions
           │       ├─ COUNT(*) WHERE category IS NULL OR ''
           │       └─ COUNT(*) matches JOIN transactions WHERE status='accepted'
           │       → if total_transactions <= 0: QMessageBox.warning, STOP
           │
           ├─ QFileDialog.getSaveFileName() → filepath
           │
           └──► export_workbook(filepath)
                   │
                   ├─ re-check total_transactions <= 0 → raise ValueError
                   │
                   ├─ wb = openpyxl.Workbook(); remove default sheet
                   │
                   ├─ add_sheet("Consolidated", ...)          [all txns]
                   ├─ for each DISTINCT bank:
                   │     add_sheet(f"Bank - {bank}", ...)
                   ├─ add_sheet("Self Transfers", ...)         [status='accepted' only]
                   ├─ add_sheet("Income Summary", ...)
                   │     └─ JOIN transactions t ON category_types ct
                   │        WHERE dr_cr='CR' AND ct.category_type='income'
                   │        (this is what makes manual overrides count too,
                   │         per our last fix — NOT derived from `rules`)
                   ├─ add_sheet("Uncategorized", ...)
                   ├─ add_sheet("Category Summary", ...)       [GROUP BY category, dr_cr]
                   │
                   └─ wb.save(output_path)
           │
           └─ update_export_summary()   (refresh the label text on Export tab)
```

---

## G. GUI Lifecycle & Reset Flow

```
main_gui.py  (__main__)
   │
   ├──► init_db()                         [creates tables if missing — does NOT seed rules]
   │       ⚠ if this is someone's first run and setup_db.py was never run,
   │         the GUI will start fine but rules table is empty → Flow D
   │         will silently categorize nothing.
   │
   ├──► QApplication(sys.argv)
   │
   └──► MainWindow()
           │
           ├─ ImportTab()    → refresh_imported_files() runs immediately on construction
           ├─ ReviewTab()    → refresh() runs immediately         [Flow E-2]
           ├─ TransferTab()  → refresh() runs immediately         [Flow E-3]
           └─ Export tab     → get_export_summary() runs immediately for the label
           │
           └─ window.show(); app.exec()


Reset Database button  (ImportTab.reset_database)
   │
   ├─ QMessageBox.question("This will remove ...") → if No: STOP
   ├─ QMessageBox.question("Also delete input files?") → remove_files bool
   │
   └──► reset_database(remove_files)      [analyzer/database.py]
           ├─ DELETE FROM manual_overrides, matches, transactions,
           │              import_log, rules, category_types
           ├─ DELETE FROM sqlite_sequence WHERE name IN (transactions, rules)
           └─ if remove_files: os.remove() every file in INPUT_FOLDER
           │
           ⚠ Does NOT call seed_default_rules() afterward (unless you added
             that call, per the earlier fix) — a reset followed by a new
             import will show everything uncategorized until rules are
             re-seeded, either manually or via the fix suggested earlier.
```

---

## Quick-reference: "if X is broken, look at Y"

| Symptom                                   | Flow to check                                     | File(s)                                                                           |
| ----------------------------------------- | ------------------------------------------------- | --------------------------------------------------------------------------------- |
| Everything uncategorized                  | B (seeding) → D (apply_rules)                     | `rule_engine.py`, check `rules` table row count                                   |
| Transaction missing after import          | C-core                                            | `import_manager.py` — check for "already imported" skip, or a swallowed exception |
| Wrong bank/account label on imported rows | C-core (bank_override/account resolution)         | `import_manager.py`, `config.py`                                                  |
| New bank's file not recognized            | C-core → `discover_parsers`/`get_parser_for_file` | `parsers/__init__.py`, `bank_formats/*.json`                                      |
| Transfers tab always empty                | E-1 vs E-3                                        | `find_transfers()` is never called — this is a real gap, not necessarily "broken" |
| Manual category not in Income Summary     | F                                                 | Check `category_types` table has an entry, not `rules`                            |
| Export button does nothing / errors       | F                                                 | `export.py` — check `total_transactions <= 0` guard                               |
| App won't start                           | G                                                 | `init_db()` — check `DB_PATH` resolves, check schema errors in console            |

If you want, I can turn the two ⚠ gaps (no button ever calls `find_transfers()`, and `ReviewTab` has no way to actually assign a manual category) into concrete GUI wiring — that would close the loop on the two flows that currently exist in code but are unreachable from the app.
