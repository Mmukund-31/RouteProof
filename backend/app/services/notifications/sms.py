"""Mock SMS adapter: records a development delivery-log row. NO real SMS is sent."""
from sqlalchemy.orm import Session

from app.models import SmsLog


def mask_phone(phone: str | None) -> str:
    digits = "".join(c for c in (phone or "") if c.isdigit())
    return ("*" * max(len(digits) - 4, 0)) + digits[-4:] if digits else "unknown"


class MockSmsProvider:
    name = "mock"

    def send(self, db: Session, phone: str | None, link_id) -> SmsLog:
        row = SmsLog(link_id=link_id, to_masked=mask_phone(phone), provider=self.name, status="LOGGED_NOT_SENT")
        db.add(row)
        return row


def get_sms_provider() -> MockSmsProvider:
    return MockSmsProvider()
