from types import SimpleNamespace
from io import BytesIO
from PyPDF2 import PdfReader
from app.services.pdf_profile import generate_employee_pdf



class DummyEmpRepo:
    def list_employees(self):
        return [SimpleNamespace(id="1", full_name="Test", name="Tester", birthdate=None)]


class DummyPayoutRepo:
    def list(self, employee_id=None, *args, **kwargs):
        return [{"timestamp": "2025-05-01 12:00:00", "amount": 100, "status": "Pending"}]


class DummyVacRepo:
    def list(self):
        return [{"employee_id": "1", "start_date": "2025-06-01", "end_date": "2025-06-10", "comment": ""}]


def test_generate_employee_profile_pdf():
    pdf = generate_employee_pdf(
        1,
        employee_repo=DummyEmpRepo(),
        payout_repo=DummyPayoutRepo(),
        vacation_repo=DummyVacRepo(),
    )
    reader = PdfReader(BytesIO(pdf))
    text = "".join(page.extract_text() or "" for page in reader.pages)
    assert "Telegram ID: 1" in text
    assert "2025-05-01" in text
    assert "PAYOUT HISTORY" in text
