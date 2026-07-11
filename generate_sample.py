"""
Generates sample HDFC-format statements for exercising the full app:
rule-based categorization, uncategorized fallthrough, self-transfer
matching (including a deliberate false-positive), multi-account/file
consolidation, and parser edge cases.

Run: python generate_sample.py
Files land in ./SampleStatements/ (plus the original sample_hdfc.xlsx
at the repo root, kept for backward compatibility with the readme).
"""
import os
import random
import openpyxl

OUT_DIR = "SampleStatements"
HEADERS = ["Date", "Narration", "Chq./Ref.No.", "Value Dt",
           "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"]


def _save(rows, filename, headers=HEADERS):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Account Statement"
    ws.append(headers)
    for row in rows:
        ws.append(row)
    path = os.path.join(OUT_DIR, filename) if filename != "sample_hdfc.xlsx" else filename
    wb.save(path)
    print(f"  {path}  ({len(rows)} rows)")
    return path


# --------------------------------------------------------------------------
# Legacy file — unchanged, kept so existing instructions/tests still work.
# --------------------------------------------------------------------------
def generate_legacy_sample():
    rows = [
        ["2025-04-01", "SALARY CREDIT", "", "2025-04-01", 0, 50000, 50000],
        ["2025-04-02", "SWIGGY INSTA/Payment", "12345", "2025-04-02", 450, 0, 49550],
        ["2025-04-03", "IMPS/Transfer to ICICI AC/98765", "98765", "2025-04-03", 10000, 0, 39550],
        ["2025-04-04", "INT.PD (Savings Interest)", "", "2025-04-04", 0, 150, 39700],
        ["2025-04-05", "AMAZON PURCHASE", "AMZ123", "2025-04-05", 1200, 0, 38500],
    ]
    _save(rows, "sample_hdfc.xlsx")


# --------------------------------------------------------------------------
# Account A — "Primary Savings"
# Covers: every default rule, edge cases in parse_amount/date handling,
# the two outbound legs of real self-transfers, and one leg of the
# deliberate false-positive coincidence.
# --------------------------------------------------------------------------
def generate_primary_savings():
    rows = [
        # -- normal, rule-matching transactions --
        ["2026-06-01", "SALARY CREDIT JUNE", "", "2026-06-01", 0, 60000, 210000],
        ["2026-06-02", "SWIGGY ORDER 45231", "SWG45231", "2026-06-02", 450, 0, 209550],
        ["2026-06-02", "ZOMATO ORDER 99812", "ZMT99812", "2026-06-02", 600, 0, 208950],
        ["2026-06-03", "AMAZON PURCHASE ELECTRONICS", "AMZ778812", "2026-06-03", 2200, 0, 206750],
        ["2026-06-03", "FLIPKART BIG BILLION DAY SALE", "FKT552210", "2026-06-03", 1500, 0, 205250],
        ["2026-06-04", "INT.PD :Savings Interest", "", "2026-06-04", 0, 150, 205400],
        ["2026-06-04", "FD INT CREDIT Q1", "", "2026-06-04", 0, 2000, 207400],

        # -- real self-transfers (strong match: shared ref token) --
        # -> credit leg lives in Secondary Current, same ref N20260605001
        ["2026-06-05", "NEFT-N20260605001-TO SELF SECONDARY AC", "N20260605001", "2026-06-05", 10000, 0, 197400],
        # -> credit leg lives in Business Account, same ref P20260606771
        ["2026-06-06", "IMPS/P20260606771/TO SELF BUSINESS AC", "P20260606771", "2026-06-06", 5000, 0, 192400],
        # -> debit leg lives in Secondary Current, same ref 234567890123
        ["2026-06-07", "UPI/CR/234567890123/FROM SECONDARY AC", "234567890123", "2026-06-07", 0, 3000, 195400],

        # -- false-positive bait: same date + amount as Business Account's
        # "ATM CASH WITHDRAWAL SELF" (2026-06-08, 7000) but NO shared ref
        # and no real relationship. Should surface as low-confidence only.
        ["2026-06-08", "CASH DEPOSIT SELF", "", "2026-06-08", 0, 7000, 202400],

        # -- genuinely uncategorized (no rule matches) --
        ["2026-06-09", "MISC DEBIT CARD SWIPE XYZ MART", "XYZ4432", "2026-06-09", 875, 0, 201525],
        ["2026-06-09", "CHEQUE DEPOSIT LOCAL", "", "2026-06-09", 0, 12000, 213525],
        ["2026-06-15", "RENT PAYMENT TO LANDLORD MR SHARMA", "", "2026-06-15", 15000, 0, 197275],

        # -- edge cases --
        # both amounts blank/zero -> should be SKIPPED as an opening-balance row
        ["2026-06-10", "OPENING BALANCE B/F", "", "2026-06-10", 0, 0, 213525],
        # currency symbol + thousands separator, as a STRING cell
        ["2026-06-10", "AMAZON PURCHASE BOOKS", "AMZ990011", "2026-06-10", "₹1,250.00", 0, 212275],
        # accounting-negative deposit -> parse_amount returns -300; watch
        # this one, it produces a negative `amount` (violates the "always
        # positive" contract in models.py) — worth confirming intended.
        ["2026-06-11", "REFUND ADJUSTMENT", "", "2026-06-11", 0, "(300.00)", 211975],
        # unparseable amount -> ParseError -> row skipped, logged
        ["2026-06-11", "UNKNOWN FEE CHARGE", "", "2026-06-11", "N/A", 0, 211975],
        # invalid calendar date (Feb 31) -> exception -> row skipped
        ["31/02/2026", "INVALID DATE TEST", "", "31/02/2026", 500, 0, 211475],
        # blank Narration -> str(NaN) quirk ("nan" as description)
        ["2026-06-13", None, "", "2026-06-13", 0, 900, 212375],
        # both Withdrawal AND Deposit filled -> withdrawal silently wins
        ["2026-06-14", "DUPLICATE AMOUNT BOTH FIELDS TEST", "", "2026-06-14", 400, 300, 212275],
    ]
    return _save(rows, "PrimarySavings_hdfc_FYxxxx.xlsx")


# --------------------------------------------------------------------------
# Account B — "Secondary Current"
# --------------------------------------------------------------------------
def generate_secondary_current():
    rows = [
        ["2026-06-01", "SALARY CREDIT JUNE - CONSULTING", "", "2026-06-01", 0, 45000, 125000],
        ["2026-06-02", "SWIGGY ORDER 33210", "SWG33210", "2026-06-02", 350, 0, 124650],
        # not in default_rules.json — deliberately uncategorized, ties into
        # the readme's "Adding Custom Categorization Rules" NETFLIX example
        ["2026-06-03", "NETFLIX SUBSCRIPTION", "", "2026-06-03", 499, 0, 124151],
        ["2026-06-04", "INT.PD :Savings Interest", "", "2026-06-04", 0, 80, 124231],
        # credit leg matching Primary Savings' outbound NEFT (ref N20260605001)
        ["2026-06-05", "NEFT-N20260605001-FROM PRIMARY SAVINGS", "N20260605001", "2026-06-05", 0, 10000, 134231],
        # opening-balance style skip row
        ["2026-06-06", "OPENING BAL CARRY FWD", "", "2026-06-06", 0, 0, 134231],
        # debit leg matching Primary Savings' inbound UPI credit (ref 234567890123)
        ["2026-06-07", "UPI/DR/234567890123/TO PRIMARY SAVINGS", "234567890123", "2026-06-07", 3000, 0, 131231],
        ["2026-06-08", "ATM CASH WITHDRAWAL LOCAL", "", "2026-06-08", 2000, 0, 129231],
        ["2026-06-09", "ZOMATO ORDER 11029", "ZMT11029", "2026-06-09", 550, 0, 128681],
        ["2026-06-12", "FD INT CREDIT Q1", "", "2026-06-12", 0, 1200, 129881],
        ["2026-06-13", "ELECTRICITY BILL PAYMENT BSES", "", "2026-06-13", 2100, 0, 127781],
        ["2026-06-14", "FLIPKART ELECTRONICS SALE", "FKT100234", "2026-06-14", 3200, 0, 124581],
    ]
    return _save(rows, "SecendoryCurrent_hdfc_FYxxxx.xlsx")


# --------------------------------------------------------------------------
# Account C — "Business Account"
# --------------------------------------------------------------------------
def generate_business_account():
    rows = [
        # uncategorized — "CLIENT PAYMENT" matches no rule
        ["2026-06-01", "CLIENT PAYMENT RECEIVED - INVOICE 2201", "", "2026-06-01", 0, 85000, 585000],
        ["2026-06-02", "AMAZON BUSINESS PURCHASE OFFICE SUPPLIES", "AMZB4471", "2026-06-02", 6200, 0, 578800],
        # auto-tagged "Transfer" by the NEFT keyword rule but NOT a real
        # self-transfer — no matching counterpart anywhere. Confirms
        # category="Transfer" and an actual matched pair are independent.
        ["2026-06-03", "GST PAYMENT NEFT CHALLAN", "", "2026-06-03", 18000, 0, 560800],
        # credit leg matching Primary Savings' outbound IMPS (ref P20260606771)
        ["2026-06-06", "IMPS/CR/P20260606771/FROM PRIMARY SAVINGS", "P20260606771", "2026-06-06", 0, 5000, 565800],
        # false-positive bait paired with Primary Savings' "CASH DEPOSIT SELF"
        ["2026-06-08", "ATM CASH WITHDRAWAL SELF", "", "2026-06-08", 7000, 0, 558800],
        ["2026-06-09", "OFFICE RENT NEFT PAYMENT", "", "2026-06-09", 25000, 0, 533800],
        ["2026-06-10", "OPENING BALANCE", "", "2026-06-10", 0, 0, 533800],
        ["2026-06-11", "SALARY PAYOUT TO STAFF NEFT", "", "2026-06-11", 45000, 0, 488800],
        ["2026-06-13", "FLIPKART OFFICE FURNITURE", "FKT778821", "2026-06-13", 12000, 0, 476800],
        ["2026-06-14", "CLIENT PAYMENT RECEIVED - INVOICE 2202", "", "2026-06-14", 0, 32000, 508800],
    ]
    return _save(rows, "Business_hdfc_FYxxxx.xlsx")


# --------------------------------------------------------------------------
# Bulk pair — for perf-testing apply_rules() and find_transfers() at scale.
# A handful of real transfer pairs are seeded among random noise so the
# matcher has genuine work to do, not just a big table to scan.
# --------------------------------------------------------------------------
def generate_bulk_pair(n_per_account=400, seed=42):
    random.seed(seed)
    merchants_categorized = [
        ("SWIGGY ORDER", lambda i: f"SWG{i:05d}"),
        ("ZOMATO ORDER", lambda i: f"ZMT{i:05d}"),
        ("AMAZON PURCHASE", lambda i: f"AMZ{i:05d}"),
        ("FLIPKART ORDER", lambda i: f"FKT{i:05d}"),
    ]
    merchants_uncategorized = [
        "GROCERY STORE PURCHASE", "FUEL STATION PAYMENT", "MOBILE RECHARGE",
        "INSURANCE PREMIUM", "GYM MEMBERSHIP", "STREAMING SERVICE",
    ]

    def _rand_rows(account_tag, ref_prefix, transfer_slots):
        rows, balance = [], 300000
        for i in range(n_per_account):
            day = 1 + (i % 28)
            date = f"2026-0{6 if day < 31 else 7}-{day:02d}"
            if i in transfer_slots:
                ref = f"{ref_prefix}{i:05d}"
                is_debit = transfer_slots[i] == "debit"
                desc = f"NEFT-{ref}-{'TO' if is_debit else 'FROM'} SELF OTHER ACCOUNT"
                amt = random.choice([1000, 2500, 5000, 7500])
                withdraw, deposit = (amt, 0) if is_debit else (0, amt)
            elif random.random() < 0.6:
                name, ref_fn = random.choice(merchants_categorized)
                desc, ref = f"{name} {i}", ref_fn(i)
                withdraw, deposit = random.randint(100, 3000), 0
            else:
                desc, ref = random.choice(merchants_uncategorized), ""
                withdraw, deposit = random.randint(200, 5000), 0
            balance += deposit - withdraw
            rows.append([date, desc, ref, date, withdraw, deposit, balance])
        return rows

    # Seed 10 matching transfer pairs at the same indices/dates/refs/amounts
    # across both files — everything else is independent random noise.
    transfer_indices = random.sample(range(n_per_account), 10)
    slots_1 = {i: "debit" for i in transfer_indices}
    slots_2 = {i: "credit" for i in transfer_indices}

    random.seed(seed)  # reset so amounts align between the two calls
    rows_1 = _rand_rows("bulk1", "BULKREF", slots_1)
    random.seed(seed)
    rows_2 = _rand_rows("bulk2", "BULKREF", slots_2)

    p1 = _save(rows_1, "BulkAcc1_hdfc_FYxxxx.xlsx")
    p2 = _save(rows_2, "BulkAcc2_hdfc_FYxxxx.xlsx")
    return p1, p2


# --------------------------------------------------------------------------
# Structural edge cases
# --------------------------------------------------------------------------
def generate_empty_statement():
    """Headers only, zero data rows — exercises the 'no transactions
    found' path in import_manager.import_file()."""
    return _save([], "hdfc_empty_statement.xlsx")


def generate_wrong_format():
    """No 'Narration' column at all — can_parse()'s detect_column check
    fails, so Auto-detect should raise ParserNotFoundError."""
    bad_headers = ["Txn Date", "Details", "Ref", "Debit", "Credit", "Bal"]
    rows = [
        ["2026-06-01", "SOME TRANSACTION", "REF1", 500, 0, 10000],
        ["2026-06-02", "ANOTHER TRANSACTION", "REF2", 0, 1500, 11500],
    ]
    return _save(rows, "hdfc_wrong_format.xlsx", headers=bad_headers)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("Legacy file:")
    generate_legacy_sample()

    print("\nCore 3-account scenario (rules, uncategorized, real transfers,")
    print("a deliberate false-positive, and parser edge cases):")
    generate_primary_savings()
    generate_secondary_current()
    generate_business_account()

    print("\nBulk pair (performance / stress testing):")
    generate_bulk_pair()

    print("\nStructural edge cases:")
    generate_empty_statement()
    generate_wrong_format()

    print(
        "\nSuggested import — one batch, per-file account assignment:\n"
        "  hdfc_primary_savings.xlsx    -> account 'Primary Savings'\n"
        "  hdfc_secondary_current.xlsx  -> account 'Secondary Current'\n"
        "  hdfc_business_account.xlsx   -> account 'Business Account'\n"
        "Then check: Review tab (uncategorized rows), Transfers tab\n"
        "(3 high-confidence pairs + 1 low-confidence false positive to\n"
        "reject), and Export (Category Summary should show 'Transfer'-\n"
        "categorized rows that were never matched as real transfers).\n"
        "\n"
        "Bulk files -> two more accounts, for timing apply_rules()/\n"
        "find_transfers() at ~400 rows/account.\n"
        "\n"
        "hdfc_empty_statement.xlsx and hdfc_wrong_format.xlsx are for\n"
        "single-file imports to check error handling, not the main batch."
    )


if __name__ == "__main__":
    main()