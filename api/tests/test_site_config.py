"""縣市設定：以另一個縣市的設定檔啟動（子程序，避免影響其他測試已載入的基隆市設定）。"""
import json
import os
import subprocess
import sys
import tempfile

API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHECK = r"""
import io, json
from app import create_app
c = create_app().test_client()
out = {
    "site": c.get("/api/public/site").get_json(),
    "js": c.get("/api/public/site-config.js").get_data(as_text=True),
    "districts": c.get("/api/public/villages").get_json()["districts"],
    "order": c.get("/api/public/villages").get_json()["order"],
    "keelung": c.post("/api/registrations", data={
        "batch_id": "4", "name": "王小明", "id_number": "A123456789", "birth_date": "1990-05-12", "sex": "男",
        "phone": "0912345678", "email": "a@example.com", "district": "安樂區", "village": "樂一里",
        "address": "x", "meal_pref": "葷食", "support_pref": "願意", "agree_consent": "true",
        "photo": (io.BytesIO(b"x"), "p.png", "image/png"),
    }, content_type="multipart/form-data").get_json(),
}
from app.routes.notify import TEMPLATES, SIGNATURE
from app.db import get_db
out["subject"] = TEMPLATES["approved"][1]
out["signature"] = SIGNATURE
out["location"] = get_db().execute("SELECT location FROM batches LIMIT 1").fetchone()["location"]
print(json.dumps(out, ensure_ascii=False))
"""


def test_other_municipality_config():
    tmp = tempfile.mkdtemp()
    cfg = {
        "city": "宜蘭縣", "agency": "宜蘭縣政府消防局", "unit": "災害預防科", "phone": "(03) 932-2119", "ext": "123",
        "tel": "+88639322119", "address": "260 宜蘭縣宜蘭市中山路二段 1 號",
        "districts": {"宜蘭市": ["民權里", "中山里"], "羅東鎮": ["北成里"]},
    }
    path = os.path.join(tmp, "yilan.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False)
    env = {**os.environ, "SITE_CONFIG": path, "JWT_SECRET": "t",
           "DATABASE_PATH": os.path.join(tmp, "db.sqlite3"), "UPLOAD_DIR": os.path.join(tmp, "up")}
    res = subprocess.run([sys.executable, "-c", CHECK], cwd=API_DIR, env=env, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip().splitlines()[-1])

    assert out["site"]["site_name"] == "宜蘭縣防災士培訓報名系統"
    assert out["site"]["phone_ext"] == "(03) 932-2119 分機 123"
    assert out["site"]["tel_uri"] == "+88639322119,123"
    assert out["js"].startswith("window.SITE = ") and "宜蘭縣政府消防局" in out["js"]
    assert out["districts"] == cfg["districts"]
    assert out["order"] == ["宜蘭市", "羅東鎮"]
    assert "設籍宜蘭縣" in out["keelung"]["error"]
    assert out["subject"].startswith("【宜蘭縣防災士培訓】")
    assert "宜蘭縣政府消防局 災害預防科" in out["signature"]
    assert out["location"] == "宜蘭縣消防局訓練中心"
