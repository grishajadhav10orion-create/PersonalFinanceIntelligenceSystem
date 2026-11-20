"""XLS / XLSX / TXT statement import, and rejection of password-protected workbooks. Run: python -m unittest tests.test_formats"""
import datetime, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import openpyxl
from bsi.extractor import extract_statement
from bsi.readers.errors import PasswordProtectedError

HEAD = ["Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"]
ROWS = [[datetime.date(2026, 6, 1), "NEFT-HDFCN52026060112345-MR RAJESH KUMAR-RENT FOR JUN-", "REF1", "", 18000, "", 32000],
        [datetime.date(2026, 6, 2), "UPI/402981/SWIGGY/REF77281", "REF2", "", 606.53, "", 31393.47],
        [datetime.date(2026, 6, 5), "SALARY ACME LTD", "REF3", "", "", 50000, 81393.47]]
PRE = [["XYZ BANK", "Statement of account"], [], ["Account No", "12345"]]
D = tempfile.mkdtemp()

def check(t, n=3):
    valid, rej, _ = t
    assert len(valid) == n and not rej, (len(valid), rej)
    assert valid[0].date == "2026-06-01" and valid[0].withdrawal == 18000 and valid[2].deposit == 50000

class Formats(unittest.TestCase):
    def test_xlsx_with_preamble_and_real_dates(self):
        p = os.path.join(D, "a.xlsx"); wb = openpyxl.Workbook(); ws = wb.active
        for r in PRE + [HEAD] + ROWS: ws.append(r)
        wb.save(p); check(extract_statement(p))
    def test_xls(self):
        import xlwt
        p = os.path.join(D, "a.xls"); wb = xlwt.Workbook(); ws = wb.add_sheet("S"); st = xlwt.easyxf(num_format_str="DD/MM/YYYY")
        for i, r in enumerate(PRE + [HEAD] + ROWS):
            for j, v in enumerate(r):
                if isinstance(v, datetime.date): ws.write(i, j, v, st)
                elif v != "": ws.write(i, j, v)
        wb.save(p); check(extract_statement(p))
    def test_txt_delimiters_and_line_endings(self):
        def rows(sep): return [sep.join(HEAD)] + [sep.join(str(x.isoformat() if isinstance(x, datetime.date) else x) for x in r) for r in ROWS]
        for name, sep, nl, enc in [("tab", "\t", "\r\n", "utf-8"), ("pipe", "|", "\n", "utf-8-sig"), ("semi", ";", "\r", "cp1252"), ("comma", ",", "\n", "utf-16")]:
            p = os.path.join(D, name + ".txt")
            with open(p, "wb") as f: f.write((nl.join(["XYZ BANK", ""] + rows(sep)) + nl).encode(enc))
            check(extract_statement(p))
    def test_txt_space_aligned(self):
        # space-aligned text can't represent blank cells, so (as banks do) empty amounts are printed as 0.00
        p = os.path.join(D, "sp.txt"); fill = lambda r: [("0.00" if v == "" and j in (4, 5) else ("-" if v == "" else v)) for j, v in enumerate(r)]
        lines = ["  ".join(HEAD)] + ["   ".join(str(x.isoformat() if isinstance(x, datetime.date) else x) for x in fill(r)) for r in ROWS]
        with open(p, "w") as f: f.write("\n".join(lines))
        check(extract_statement(p))
    def test_encrypted_xlsx_rejected(self):
        p = os.path.join(D, "enc.xlsx")              # encrypted OOXML = OLE container with EncryptedPackage
        with open(p, "wb") as f: f.write(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600 + "EncryptedPackage".encode("utf-16-le"))
        with self.assertRaises(PasswordProtectedError): extract_statement(p)
    def test_encrypted_xls_rejected(self):
        import xlwt, xlrd
        from unittest import mock
        p = os.path.join(D, "e.xls"); wb = xlwt.Workbook(); wb.add_sheet("S"); wb.save(p)
        with mock.patch("xlrd.open_workbook", side_effect=xlrd.XLRDError("Workbook is encrypted")):
            with self.assertRaises(PasswordProtectedError): extract_statement(p)
    def test_unsupported_still_rejected(self):
        with self.assertRaises(ValueError): extract_statement(os.path.join(D, "x.docx"))

if __name__ == "__main__":
    unittest.main()
