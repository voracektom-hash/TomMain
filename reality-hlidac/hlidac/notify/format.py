"""Build alert texts: rich push (ntfy) and compact ASCII SMS.

SMS example (fits 2 segments, i.e. ≤ 306 GSM characters):
  P5-Smichov 2+kk 54m2 3.NP OV6.49M (120k/m2, -12% med) J.Novak RE/MAX 777123456
  https://sreality.cz/detail/prodej/byt/2+kk/x/1234567890
"""

from __future__ import annotations

import re

from hlidac.locations import short_name
from hlidac.notify.base import Message
from hlidac.sreality.parser import Listing, ListingDetail
from hlidac.text import ascii_text

SMS_SEGMENT = 160
SMS_MULTI_SEGMENT = 153
SMS_MAX_SEGMENTS = 2
SMS_MAX_LEN = SMS_MULTI_SEGMENT * SMS_MAX_SEGMENTS

SHORT_URL = "https://sreality.cz/detail/prodej/byt/2+kk/x/{id}"

TITLES = re.compile(r"^(bc|ing|mgr|mudr|judr|phdr|rndr|doc|prof|dis|mba|ph\.?d|arch|akad)\.?,?$",
                    re.IGNORECASE)
COMPANY_SUFFIX = re.compile(r",?\s*\b(s\.\s?r\.\s?o\.?|spol\..*|a\.\s?s\.?|v\.\s?o\.\s?s\.?|k\.\s?s\.?|z\.\s?s\.?)\s*$",
                            re.IGNORECASE)
OWNERSHIP_SHORT = {"osobn": "OV", "druzs": "DV", "statn": "SV"}


def sms_segments(text: str) -> int:
    if len(text) <= SMS_SEGMENT:
        return 1
    return -(-len(text) // SMS_MULTI_SEGMENT)


def _money_short(czk: int) -> str:
    if czk >= 1_000_000:
        return f"{czk / 1_000_000:.2f}M"
    return f"{round(czk / 1000)}k"


def _money_cz(czk: int | None) -> str:
    if not czk:
        return "cena na dotaz"
    return f"{czk / 1_000_000:.2f} M Kč".replace(".", ",")


def _thousands(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def broker_short(name: str | None) -> str | None:
    """'Bc. Jana Kuželíková' -> 'J.Kuzelikova'."""
    if not name:
        return None
    words = [w for w in name.replace(",", " ").split() if not TITLES.match(w)]
    if not words:
        return None
    if len(words) == 1:
        return ascii_text(words[0])
    first, last = words[0], words[-1]
    # Sreality sometimes lists "Surname Name"; Czech female surnames end with -ová.
    if first.lower().endswith("ová") and not last.lower().endswith("ová"):
        first, last = last, first
    return ascii_text(f"{first[0]}.{last}")


def agency_short(name: str | None, max_len: int = 14) -> str | None:
    """'Bydlení a Reality s.r.o.' -> 'Bydleni a Real'."""
    if not name:
        return None
    clean = COMPANY_SUFFIX.sub("", name).strip(" ,")
    return ascii_text(clean)[:max_len].strip() or None


def phone_short(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("420") and len(digits) == 12:
        digits = digits[3:]
    return digits or None


def floor_label(floor: int | None) -> str | None:
    if floor is None:
        return None
    return f"{floor}.NP" if floor > 0 else f"{abs(floor)}.PP"


def ownership_short(ownership: str | None) -> str:
    if not ownership:
        return ""
    return OWNERSHIP_SHORT.get(ascii_text(ownership).lower()[:5], "")


def sms_text(l: Listing, d: ListingDetail | None, below: float | None,
             drop_pct: float | None = None) -> str:
    head = f"SLEVA {drop_pct:.0f}% " if drop_pct is not None else ""
    parts = [short_name(l), l.disposition or "", f"{l.area_m2:g}m2" if l.area_m2 else ""]
    if d:
        parts.append(floor_label(d.floor) or "")
    price = ownership_short(d.ownership if d else None)
    price += _money_short(l.price_czk) if l.price_czk else "cena?"
    parts.append(price)
    stats = []
    if l.price_m2:
        stats.append(f"{round(l.price_m2 / 1000)}k/m2")
    if below is not None:
        stats.append(f"{-below:+.0f}% med")
    if stats:
        parts.append(f"({', '.join(stats)})")
    main = head + " ".join(p for p in parts if p)

    broker = broker_short(d.broker_name if d else None)
    agency = agency_short(d.agency if d else None) or ("soukromy" if l.is_private else None)
    phone = phone_short(d.broker_phone if d else None)
    url = SHORT_URL.format(id=l.id)

    # Drop the least important pieces until it fits two SMS segments.
    for contact in ([broker, agency, phone], [broker, phone], [phone], []):
        text = ascii_text(" ".join(p for p in [main, *contact, url] if p))
        if len(text) <= SMS_MAX_LEN:
            return text
    return ascii_text(f"{main[:SMS_MAX_LEN - len(url) - 1]} {url}")


def listing_message(l: Listing, d: ListingDetail | None, below: tuple[float, str] | None,
                    rule_names: list[str], drop: tuple[int, int] | None = None) -> Message:
    """drop = (old_price, new_price) for price-drop alerts."""
    drop_pct = (drop[1] - drop[0]) / drop[0] * 100 if drop else None
    loc = short_name(l).replace("-", " ")
    area = f"{l.area_m2:g} m²" if l.area_m2 else "? m²"
    title = f"{l.disposition or '?'} {area} · {loc}"
    if drop_pct is not None:
        title = f"SLEVA {drop_pct:.0f} % · {title}".replace(".", ",")

    lines = []
    price_line = _money_cz(l.price_czk)
    if drop:
        price_line = f"{_money_cz(drop[0])} → {price_line}"
    if l.price_m2:
        price_line += f" · {_thousands(l.price_m2)} Kč/m²"
    if below is not None:
        word = "pod" if below[0] >= 0 else "nad"
        price_line += f" · {abs(below[0]):.0f} % {word} mediánem ({below[1]})"
    lines.append(price_line)

    if d:
        facts = []
        if d.floor is not None:
            floors = f" z {d.floors_total}" if d.floors_total else ""
            facts.append(f"{d.floor}. NP{floors}" if d.floor > 0 else "suterén")
        if d.ownership:
            facts.append(d.ownership.lower())
        if d.since:
            y, m, day = d.since.split("-")
            facts.append(f"vloženo {int(day)}. {int(m)}.")
        if facts:
            lines.append(" · ".join(facts))
        contact = [x for x in (d.broker_name, d.agency, d.broker_phone) if x]
        if contact:
            lines.append(" · ".join(contact))
    elif l.is_private:
        lines.append("soukromý prodejce")
    if rule_names:
        lines.append("Pravidlo: " + ", ".join(rule_names))

    return Message(
        title=title,
        body="\n".join(lines),
        sms=sms_text(l, d, below[0] if below else None, drop_pct),
        url=l.url,
        image_url=l.image_url,
        phone=d.broker_phone if d else None,
        priority=4 if drop is None else 3,
        tags=["house"] if drop is None else ["chart_with_downwards_trend"],
    )


def service_message(text: str) -> Message:
    return Message(title="Reality Hlídač: problém", body=text,
                   sms=ascii_text(f"Hlidac: {text}")[:SMS_SEGMENT], priority=4, tags=["warning"])
