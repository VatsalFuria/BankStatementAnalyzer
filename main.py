from analyzer.database import init_db
from analyzer.import_manager import import_file

if __name__ == "__main__":
    init_db()
    try:
        import_file("sample_hdfc.xlsx", bank_override="HDFC", account="Savings")
    except Exception as e:
        print(e)