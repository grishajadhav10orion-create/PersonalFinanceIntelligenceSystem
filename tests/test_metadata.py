"""Statements that carry extra metadata (bank name, account details, period, summaries, totals, footers) must import
without any manual clean-up, in every format. Run: python -m unittest tests.test_metadata"""
import csv, datetime, io, json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import openpyxl
from bsi.extractor import extract_statement

D = tempfile.mkdtemp()
HEAD = ["Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"]
ROWS = [["01/06/2026", "NEFT-HDFCN52026060112345-MR RAJESH KUMAR-RENT FOR JUN-", "REF1", "01/06/26", "18000.00", "", "32000.00"],
        ["02/06/2026", "UPI/402981/SWIGGY/REF77281", "REF2", "02/06/26", "606.53", "", "31393.47"],
        ["05/06/2026", "SALARY ACME LTD", "REF3", "05/06/26", "", "50000.00", "81393.47"]]
PRE = [["XYZ BANK LTD"], ["Statement of Account"], ["Account Holder:", "SECRET HOLDER NAME"], ["Account No:", "99887766554433", "IFSC:", "XYZB0001234"],
       ["Address:", "12 Hill Road, Pune, 411001"], ["Statement Date:", "30/06/2026", "Closing Balance:", "81393.47"],      # looks a bit like a header
       ["Statement Period:", "01/06/2026 to 30/06/2026"], ["Opening Balance", "Total Debits", "Total Credits", "Closing Balance"], ["50000.00", "18606.53", "50000.00", "81393.47"], []]
POST = [[], ["Total", "", "", "", "18606.53", "50000.00", ""], ["Generated on 01/07/2026. This is a computer generated statement."], ["Registered Office: XYZ Bank, Mumbai"]]
MID = list(HEAD)                                                      # header repeated (page break)

def table(sep_rows=False):
    return PRE + [HEAD] + ROWS[:2] + ([MID] if sep_rows else []) + ROWS[2:] + POST

def check(res):
    valid, rej, _ = res
    assert len(valid) == 3 and not rej, (len(valid), rej)
    assert valid[0].date == "2026-06-01" and valid[0].withdrawal == 18000 and valid[2].deposit == 50000 and valid[2].closing_balance == 81393.47
    assert not any("SECRET" in v.narration or "99887766554433" in v.narration for v in valid)

def write_delim(name, sep, enc="utf-8", nl="\n"):
    p = os.path.join(D, name)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=sep, lineterminator=nl)
    for r in table(True): w.writerow(r)
    with open(p, "wb") as f: f.write(buf.getvalue().encode(enc))
    return p

class Metadata(unittest.TestCase):
    def test_csv_comma(self): check(extract_statement(write_delim("a.csv", ",")))
    def test_csv_semicolon_windows(self): check(extract_statement(write_delim("b.csv", ";", "cp1252", "\r\n")))
    def test_txt_tab_and_pipe(self):
        check(extract_statement(write_delim("a.txt", "\t"))); check(extract_statement(write_delim("b.txt", "|")))
    def test_xlsx(self):
        p = os.path.join(D, "a.xlsx"); wb = openpyxl.Workbook(); ws = wb.active
        for r in table(True): ws.append(r)
        wb.save(p); check(extract_statement(p))
    def test_xls(self):
        import xlwt
        p = os.path.join(D, "a.xls"); wb = xlwt.Workbook(); ws = wb.add_sheet("S")
        for i, r in enumerate(table(True)):
            for j, v in enumerate(r):
                if v != "": ws.write(i, j, v)
        wb.save(p); check(extract_statement(p))
    def test_json_with_account_details(self):
        rows = [dict(zip(HEAD, r)) for r in ROWS]
        for name, doc in (("a.json", {"bank": "XYZ", "account": {"holder": "SECRET HOLDER NAME", "no": "99887766554433"}, "transactions": rows}),
                          ("b.json", {"bank": "XYZ", "statement": {"period": "June", "entries": rows}, "summary": {"total_debits": 18606.53}})):
            p = os.path.join(D, name); json.dump(doc, open(p, "w")); check(extract_statement(p))
    def test_pdf_with_metadata_and_summary_table(self):
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors
        p = os.path.join(D, "a.pdf"); st = getSampleStyleSheet(); grid = TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black), ("FONTSIZE", (0, 0), (-1, -1), 7)])
        long = Paragraph("NEFT-HDFCN52026060112345-MR RAJESH KUMAR-RENT FOR JUN-", st["BodyText"])
        story = [Paragraph("XYZ BANK LTD - Statement of Account", st["Title"]), Paragraph("Account Holder: SECRET HOLDER NAME, Account No 99887766554433", st["BodyText"]),
                 Table([PRE[7], PRE[8]], style=grid), Spacer(1, 12),
                 Table([HEAD, [ROWS[0][0], long] + ROWS[0][2:], ROWS[1], ROWS[2]], style=grid, colWidths=[55, 150, 55, 50, 70, 70, 75]), Spacer(1, 12),
                 Table([["Total", "", "", "", "18606.53", "50000.00", ""]], style=grid), Paragraph("Generated on 01/07/2026. This is a computer generated statement.", st["BodyText"])]
        SimpleDocTemplate(p, pagesize=landscape(A4)).build(story); check(extract_statement(p))
    def test_clean_statement_still_works(self):
        p = os.path.join(D, "clean.csv")
        with open(p, "w", newline="") as f:
            w = csv.writer(f); w.writerow(HEAD); w.writerows(ROWS)
        check(extract_statement(p))
    def test_bad_date_row_inside_table_is_rejected_not_hidden(self):
        p = os.path.join(D, "bad.csv")
        with open(p, "w", newline="") as f:
            w = csv.writer(f); w.writerow(HEAD); w.writerows(ROWS); w.writerow(["31/31/2026", "BAD DATE ROW", "", "", "10.00", "", "100.00"])
        valid, rej, _ = extract_statement(p)
        self.assertEqual((len(valid), len(rej)), (3, 1)); self.assertIn("could not parse date", rej[0]["reason"])
    def test_file_without_a_table_gives_clear_error(self):
        p = os.path.join(D, "none.csv"); open(p, "w").write("XYZ BANK\nAccount No,123\nStatement Date,01/06/2026\n")
        with self.assertRaises(ValueError) as cm: extract_statement(p)
        self.assertIn("transaction table", str(cm.exception))

if __name__ == "__main__":
    unittest.main()
