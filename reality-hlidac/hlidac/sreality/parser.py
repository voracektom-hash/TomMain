"""Turn raw Sreality JSON into plain Python objects.

This is the only module that knows the shape of Sreality responses (see docs/API.md).
If Sreality changes its API, fix it here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# "Prodej bytu 2+kk 54 m²" – \s also matches the non-breaking space.
AREA_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*m²")

# Agents enter placeholder prices like 1 Kč for "price on request".
MIN_REAL_PRICE_CZK = 10_000

# Any valid disposition works in the URL; Sreality redirects to the canonical one.
URL_TEMPLATE = "https://www.sreality.cz/detail/prodej/byt/2+kk/x/{id}"


class ParseError(Exception):
    """The response does not look like what we expect – the API probably changed."""


@dataclass(frozen=True)
class Listing:
    id: int
    name: str
    disposition: str | None
    area_m2: float | None
    price_czk: int | None  # None = price on request
    price_m2: int | None
    region_id: int | None
    district: str | None
    quarter: str | None  # Praha 1–22; None when Sreality does not know it
    citypart: str | None  # e.g. Smíchov, Karlín
    city: str | None  # e.g. Praha, Černošice
    street: str | None
    lat: float | None
    lon: float | None
    premise_id: int | None  # real estate agency; None = private seller
    user_id: int | None
    image_url: str | None = None

    @property
    def is_private(self) -> bool:
        return self.premise_id is None

    @property
    def url(self) -> str:
        return URL_TEMPLATE.format(id=self.id)


@dataclass(frozen=True)
class ListingDetail:
    id: int
    since: str | None  # date first published, "YYYY-MM-DD"
    edited: str | None
    floor: int | None
    floors_total: int | None
    ownership: str | None  # "Osobní", "Družstevní", ...
    usable_area: float | None
    description: str
    broker_name: str | None
    broker_phone: str | None
    broker_email: str | None
    agency: str | None


def parse_area(name: str) -> float | None:
    match = AREA_RE.search(name)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def _check_status(data: object) -> dict:
    if not isinstance(data, dict):
        raise ParseError(f"expected JSON object, got {type(data).__name__}")
    status = data.get("status_code")
    if status != 200:
        raise ParseError(f"API status {status}: {data.get('status_message')}")
    return data


def _str(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_listing(item: dict) -> Listing:
    try:
        listing_id = int(item["hash_id"])
        name = str(item["advert_name"])
        loc = item["locality"]
        if not isinstance(loc, dict):
            raise TypeError("locality is not an object")
    except (KeyError, TypeError, ValueError) as exc:
        raise ParseError(f"listing is missing a required field: {exc}") from exc

    area = parse_area(name)
    price = _int(item.get("price_czk"))
    if price is not None and price < MIN_REAL_PRICE_CZK:  # 0 or 1 Kč = price on request
        price = None
    price_m2 = _int(item.get("price_czk_m2")) or None
    if price and not price_m2 and area:
        price_m2 = round(price / area)
    if not price:
        price_m2 = None

    quarter = _str(loc.get("quarter"))
    if _int(loc.get("quarter_id")) == -1:
        quarter = None

    images = item.get("advert_images") or []
    image = images[0] if images and isinstance(images[0], str) else None
    if image and image.startswith("//"):
        image = "https:" + image

    sub = item.get("category_sub_cb") or {}
    return Listing(
        id=listing_id,
        name=name,
        disposition=_str(sub.get("name")) if isinstance(sub, dict) else None,
        area_m2=area,
        price_czk=price,
        price_m2=price_m2,
        region_id=_int(loc.get("region_id")),
        district=_str(loc.get("district")),
        quarter=quarter,
        citypart=_str(loc.get("citypart")),
        city=_str(loc.get("city")),
        street=_str(loc.get("street")),
        lat=loc.get("gps_lat"),
        lon=loc.get("gps_lon"),
        premise_id=_int(item.get("premise_id")),
        user_id=_int(item.get("user_id")),
        image_url=image,
    )


def parse_search(data: object) -> tuple[int, list[Listing]]:
    """Return (total number of matching listings, listings on this page)."""
    data = _check_status(data)
    results = data.get("results")
    pagination = data.get("pagination")
    if not isinstance(results, list) or not isinstance(pagination, dict):
        raise ParseError("search response is missing 'results' or 'pagination'")
    total = _int(pagination.get("total"))
    if total is None:
        raise ParseError("search response is missing 'pagination.total'")
    return total, [parse_listing(item) for item in results]


def parse_detail(data: object) -> ListingDetail:
    data = _check_status(data)
    r = data.get("result")
    if not isinstance(r, dict) or "hash_id" not in r:
        raise ParseError("detail response is missing 'result.hash_id'")

    user = r.get("user") if isinstance(r.get("user"), dict) else {}
    premise = r.get("premise") if isinstance(r.get("premise"), dict) else {}
    ownership = r.get("ownership") if isinstance(r.get("ownership"), dict) else {}
    phones = [p.get("phone") for p in user.get("user_phones") or [] if isinstance(p, dict)]
    # Prefer a mobile number; brokers often list the same number twice.
    mobile = [p.get("phone") for p in user.get("user_phones") or []
              if isinstance(p, dict) and p.get("phone_type") == "MOB"]

    return ListingDetail(
        id=int(r["hash_id"]),
        since=_str(r.get("since")),
        edited=_str(r.get("edited")),
        floor=_int(r.get("floor_number")),
        floors_total=_int(r.get("floors")),
        ownership=_str(ownership.get("name")),
        usable_area=r.get("usable_area"),
        description=r.get("advert_description") or "",
        broker_name=_str(user.get("user_name")),
        broker_phone=_str((mobile or phones or [None])[0]),
        broker_email=_str(user.get("user_email")),
        agency=_str(premise.get("name")),
    )
