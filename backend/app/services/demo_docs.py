"""Synthetic POD document renderer. All names, numbers and marks are fictional test data."""
import io
import math
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SCENARIOS = {
    "clear_signed_stamped": "Clear, signed and stamped POD",
    "missing_stamp": "Signed but consignee stamp missing",
    "blurred_unreadable": "Blurred / unreadable photograph",
    "incorrect_lr": "LR number on document does not match the trip",
    "shortage_remark": "Shortage remark written by consignee",
    "damage_remark": "Damage remark written by consignee",
}


def _f(size):
    return ImageFont.load_default(size=size)


def render_pod(scenario: str, *, lr: str, consignee: str, qty: int, unit: str, date_str: str, client: str = "Demo Client",
               vehicle: str = "MH20 XX 0000", seed: int = 1) -> bytes:
    rnd = random.Random(seed)
    W, H = 1000, 1300
    im = Image.new("RGB", (W, H), (250, 248, 240))
    d = ImageDraw.Draw(im)
    d.rectangle([20, 20, W - 20, H - 20], outline=(40, 40, 40), width=3)
    d.text((W // 2, 70), "SAMPLE TRANSPORT CO. (FICTIONAL)", font=_f(34), fill=(24, 59, 54), anchor="mm")
    d.text((W // 2, 120), "LORRY RECEIPT / PROOF OF DELIVERY", font=_f(40), fill=(20, 20, 20), anchor="mm")
    d.line([40, 160, W - 40, 160], fill=(40, 40, 40), width=2)

    shown_lr = "LR-" + str(int(lr.split("-")[-1]) + 17) if scenario == "incorrect_lr" else lr
    rows = [("LR No.", shown_lr), ("Consignor", client), ("Consignee", consignee), ("Vehicle No.", vehicle),
            ("Delivered Qty", f"{qty} {unit}"), ("Delivery Date", date_str)]
    y = 220
    for k, v in rows:
        d.text((70, y), k + ":", font=_f(34), fill=(70, 70, 70))
        d.text((380, y), v, font=_f(40), fill=(10, 10, 60))
        d.line([380, y + 52, W - 70, y + 52], fill=(160, 160, 160), width=1)
        y += 95

    remark = {"shortage_remark": f"Short by 6 {unit}", "damage_remark": f"2 {unit} damaged / torn"}.get(scenario)
    d.text((70, y + 10), "Remarks:", font=_f(34), fill=(70, 70, 70))
    d.text((380, y + 10), remark or "-", font=_f(38), fill=(150, 20, 20) if remark else (10, 10, 60))

    # signature scribble
    sy = 1050
    d.text((70, sy - 70), "Receiver signature:", font=_f(30), fill=(70, 70, 70))
    pts = [(120 + i * 8, sy + 22 * math.sin(i / 2.2) + rnd.randint(-6, 6)) for i in range(32)]
    d.line(pts, fill=(15, 15, 120), width=4)
    d.line([70, sy + 50, 470, sy + 50], fill=(0, 0, 0), width=2)

    if scenario != "missing_stamp":
        cx, cy = 760, 1010
        d.ellipse([cx - 120, cy - 120, cx + 120, cy + 120], outline=(160, 20, 60), width=6)
        d.ellipse([cx - 100, cy - 100, cx + 100, cy + 100], outline=(160, 20, 60), width=2)
        d.text((cx, cy - 40), consignee.upper()[:22], font=_f(24), fill=(160, 20, 60), anchor="mm")
        d.text((cx, cy + 5), "RECEIVED", font=_f(34), fill=(160, 20, 60), anchor="mm")
        d.text((cx, cy + 50), date_str, font=_f(24), fill=(160, 20, 60), anchor="mm")

    im = im.rotate(rnd.uniform(-1.2, 1.2), fillcolor=(235, 235, 230))
    if scenario == "blurred_unreadable":
        im = im.filter(ImageFilter.GaussianBlur(22))
    im = im.resize((800, 1040))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=72, optimize=True)
    return buf.getvalue()
