"""Password-protected statements are rejected (never opened, no password requested).
Run: python -m unittest tests.test_pdf_password   (needs `pip install pypdf` to build the encrypted PDFs)"""
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_fd, _db = tempfile.mkstemp(suffix=".db"); os.close(_fd)
os.environ["DB_PATH"] = _db
try:
    from pypdf import PdfReader, PdfWriter
except ImportError:                                                  # pragma: no cover
    PdfReader = None
import app as A                                                      # noqa: E402
from bsi.extractor import extract_statement                          # noqa: E402
from bsi.readers.errors import PasswordProtectedError                # noqa: E402
SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sample_data", "sample_statement.pdf")

def encrypted(algo):
    r, w = PdfReader(SAMPLE), PdfWriter()
    for p in r.pages: w.add_page(p)
    w.encrypt("Secret123", algorithm=algo)
    path = os.path.join(tempfile.gettempdir(), f"enc_test_{algo}.pdf"); w.write(path); return path

@unittest.skipIf(PdfReader is None, "pypdf not installed")
class RejectProtectedPdf(unittest.TestCase):
    def test_all_common_encryptions_rejected(self):
        for algo in ("AES-256", "AES-128", "RC4-128"):
            with self.assertRaises(PasswordProtectedError): extract_statement(encrypted(algo))
    def test_unprotected_pdf_still_imports(self):
        self.assertGreater(len(extract_statement(SAMPLE)[0]), 0)
    def test_endpoint_rejects_and_ignores_password_field(self):
        c = A.app.test_client()
        tok = c.post("/api/signup", json={"username": "pdfpw", "password": "secret1"}).get_json()["token"]; H = {"Authorization": "Bearer " + tok}
        r = c.post("/api/import", data={"file": (open(encrypted("AES-256"), "rb"), "s.pdf"), "password": "Secret123"}, headers=H, content_type="multipart/form-data")
        j = r.get_json(); self.assertEqual(r.status_code, 422); self.assertTrue(j["password_protected"]); self.assertNotIn("Secret123", r.get_data(as_text=True))
        self.assertEqual(c.get("/api/records", headers=H).get_json(), [])

if __name__ == "__main__":
    unittest.main()
