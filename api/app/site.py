"""縣市設定：承辦機關、聯絡資訊與行政區里別。

預設使用內建的基隆市設定。移植到其他縣市時，新增 app/sites/<縣市>.json（欄位同 keelung.json），
並以環境變數 SITE_CONFIG 指定：可填檔名（例：yilan）或 JSON 檔的完整路徑。
"""
import json
import os

SITES_DIR = os.path.join(os.path.dirname(__file__), "sites")
DEFAULT_CONFIG = os.path.join(SITES_DIR, "keelung.json")
REQUIRED_KEYS = ("city", "agency", "unit", "phone", "address", "districts")


def _load():
    path = os.environ.get("SITE_CONFIG") or DEFAULT_CONFIG
    if os.sep not in path and not path.endswith(".json"):
        path = os.path.join(SITES_DIR, f"{path}.json")
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    missing = [k for k in REQUIRED_KEYS if not cfg.get(k)]
    if missing:
        raise RuntimeError(f"{path} 缺少縣市設定欄位：{', '.join(missing)}")
    cfg.setdefault("training_location", f"{cfg['city']}消防局訓練中心")
    cfg["program"] = f"{cfg['city']}防災士培訓"
    cfg["site_name"] = f"{cfg['program']}報名系統"
    cfg["phone_ext"] = f"{cfg['phone']} 分機 {cfg['ext']}" if cfg.get("ext") else cfg["phone"]
    tel = cfg.get("tel") or ""
    cfg["tel_uri"] = f"{tel},{cfg['ext']}" if tel and cfg.get("ext") else tel
    cfg["contact"] = f"{cfg['agency']} {cfg['unit']}"
    cfg["training_location_example"] = f"例：{cfg['training_location']}"
    return cfg


SITE = _load()
DISTRICTS = SITE["districts"]

# 前台可公開的欄位（不含行政區里別，里別另由 /api/public/villages 提供）
PUBLIC_KEYS = (
    "city", "agency", "unit", "phone", "ext", "phone_ext", "tel_uri", "fax", "hours", "address",
    "address_example", "home_phone_example", "training_location", "training_location_example",
    "program", "site_name", "contact",
)


def public_config():
    return {k: SITE.get(k) or "" for k in PUBLIC_KEYS}
