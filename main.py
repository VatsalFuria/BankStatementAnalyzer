from analyzer.database import init_db
from analyzer.import_manager import import_file
from analyzer.config import DEFAULT_ACCOUNT

if __name__ == "__main__":
    init_db()
    try:
        # bank_override intentionally omitted: HDFCParser's own detection
        # (analyzer/parsers/bank_formats/hdfc.json) sets txn.bank, so
        # multiple bank formats can sit in the same folder without being
        # relabeled to a single hardcoded bank.
        import_file("sample_hdfc.xlsx", account=DEFAULT_ACCOUNT)
    except Exception as e:
        print(e)