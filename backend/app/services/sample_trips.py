"""The three client-supplied sample trips: one definition shared by the seed, the demo-document generator and the
seed-integrity test, so the trip record, the synthetic POD photo and the walkthrough can never disagree.

A mismatch here (say the photo prints LR-66142 or yesterday's date for a trip delivered two days ago) would make the
demo look like an AI failure when it is really a data error.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class SampleTrip:
    ref: str
    lr: str
    client_code: str
    client_name: str
    vehicle: str
    ownership: str  # owned | hired
    driver_email: str
    destination: str
    consignee: str
    freight: Decimal
    delivered_days_ago: int
    qty: int
    unit: str
    branch: str
    seed_state: str  # seed.py scenario state
    scenario: str  # demo_docs scenario for the POD photo
    expected_status: str  # what the walkthrough must show
    expected_reasons: tuple[str, ...]
    printed_qty: int  # what the consignee wrote on the POD (shortage: 6 fewer)
    demo_point: str

    def delivery_date(self, today: date | None = None) -> date:
        return (today or date.today()) - timedelta(days=self.delivered_days_ago)


SAMPLE_TRIPS: tuple[SampleTrip, ...] = (
    SampleTrip("TRP-66120", "LR-66120", "CMPB", "Company B (Cement)", "MH20 EL 4521", "owned", "driver1@routeproof.demo",
               "Nagpur", "Nagpur Cement Depot", Decimal("38500"), 3, 600, "bags", "Nagpur", "ai_verified",
               "clear_signed_stamped", "VERIFIED", (), 600, "Correct POD appears in the billing-ready queue"),
    SampleTrip("TRP-66134", "LR-66134", "CMPC", "Company C (Steel)", "MH20 GT 7718", "owned", "driver2@routeproof.demo",
               "Pune", "Pune Steel Yard", Decimal("26000"), 4, 40, "coils", "Pune", "retake",
               "missing_stamp", "RETAKE_REQUESTED", ("STAMP_NOT_VISIBLE",), 40,
               "Missing stamp is detected and the driver is asked for another photo"),
    SampleTrip("TRP-66141", "LR-66141", "CMPD", "Company D (Packaged Foods)", "MH17 BY 3092", "hired", "driver3@routeproof.demo",
               "Indore", "Indore Warehouse", Decimal("41200"), 2, 100, "cartons", "Chhatrapati Sambhajinagar", "review_shortage",
               "shortage_remark", "NEEDS_REVIEW", ("SHORTAGE", "QUANTITY_MISMATCH"), 94,
               "Shortage of six cartons is sent to the billing executive"),
)

BY_REF = {t.ref: t for t in SAMPLE_TRIPS}
