from analyzer.database import init_db
from analyzer.parsers import discover_parsers  # loads parser registry
from analyzer.import_manager import import_file
from analyzer.rule_engine import apply_rules, reapply_all_rules

init_db()
discover_parsers()  # must be called before importing

# Import the sample file
import_id = import_file("sample_hdfc.xlsx", bank_override="HDFC", account="Savings")

# Apply categorization rules
count = apply_rules()
print(f"Categorized {count} new transactions.")

# Check the results
from analyzer.database import get_connection
conn = get_connection()
txns = conn.execute("SELECT txn_id, txn_date, description, amount, dr_cr, category FROM transactions").fetchall()
for t in txns:
    print(t["txn_date"], t["description"], t["amount"], t["dr_cr"], "→", t["category"])
conn.close()