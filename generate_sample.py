import openpyxl

wb = openpyxl.Workbook()
ws = wb.active
if ws is None:
    raise RuntimeError("No active worksheet in new workbook")
ws.title = "Account Statement"

# Headers (typical HDFC Excel statement)
headers = [
    "Date", "Narration", "Chq./Ref.No.", "Value Dt",
    "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"
]
ws.append(headers)

# Sample transactions (5 rows)
data = [
    ["2025-04-01", "SALARY CREDIT", "", "2025-04-01", 0, 50000, 50000],
    ["2025-04-02", "SWIGGY INSTA/Payment", "12345", "2025-04-02", 450, 0, 49550],
    ["2025-04-03", "IMPS/Transfer to ICICI AC/98765", "98765", "2025-04-03", 10000, 0, 39550],
    ["2025-04-04", "INT.PD (Savings Interest)", "", "2025-04-04", 0, 150, 39700],
    ["2025-04-05", "AMAZON PURCHASE", "AMZ123", "2025-04-05", 1200, 0, 38500],
]

for row in data:
    ws.append(row)

wb.save("sample_hdfc.xlsx")
print("Created sample_hdfc.xlsx")