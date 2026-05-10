"""Хелперы: телефон, даты, QR, экранирование."""
import re
import io
from datetime import datetime, date
from typing import Optional
import qrcode
from html import escape as html_escape


def normalize_phone(raw: str) -> Optional[str]:
    """+7XXXXXXXXXX или None."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits[0] in ("7", "8"):
        return "+7" + digits[1:]
    if len(digits) == 10:
        return "+7" + digits
    return None


def parse_birthday(raw: str) -> Optional[str]:
    """ДД.ММ.ГГГГ или ГГГГ-ММ-ДД -> ISO YYYY-MM-DD. None если невалидно."""
    raw = (raw or "").strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            d = datetime.strptime(raw, fmt).date()
            if d.year < 1920 or d > date.today():
                return None
            return d.isoformat()
        except ValueError:
            continue
    return None


def calc_age(birthday_iso: str) -> int:
    d = datetime.fromisoformat(birthday_iso).date()
    today = date.today()
    return today.year - d.year - ((today.month, today.day) < (d.month, d.day))


def is_birthday_today(birthday_iso: Optional[str]) -> bool:
    if not birthday_iso:
        return False
    try:
        d = datetime.fromisoformat(birthday_iso).date()
    except Exception:
        return False
    today = date.today()
    return d.month == today.month and d.day == today.day


def days_between_iso(a_iso: str, b_iso: str) -> int:
    a = datetime.fromisoformat(a_iso)
    b = datetime.fromisoformat(b_iso)
    return abs((a - b).days)


def make_qr(payload: str) -> bytes:
    qr = qrcode.QRCode(version=None, box_size=10, border=2,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def esc(text) -> str:
    return html_escape(str(text), quote=False)


def fmt_dt_iso(iso: Optional[str]) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return iso


def fmt_date_iso(iso: Optional[str]) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m.%Y")
    except Exception:
        return iso
