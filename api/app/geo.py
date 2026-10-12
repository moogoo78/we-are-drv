"""行政區與里別（資料來自縣市設定 app/site.py）。"""
from .site import DISTRICTS as VILLAGES


def parse_district_village(address):
    """從地址字串推測行政區與里別（找不到時回傳 None）。"""
    address = address or ""
    district = next((d for d in VILLAGES if d in address), None)
    village = None
    if district:
        village = next((v for v in VILLAGES[district] if v in address), None)
    return district, village


def is_valid_village(district, village):
    return village in VILLAGES.get(district, [])
