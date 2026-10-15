# we-are-drv 防災士培訓報名系統

縣市政府「防災士培訓」的報名與管理系統。民眾可線上報名、查詢審核進度；承辦人員可在後台管理梯次、名單、課程、證書與通知。預設為基隆市，可透過設定檔移植到其他縣市（見 [PORTING.md](PORTING.md)）。

## 功能

**前台（民眾）**
- 首頁、最新消息、課程資訊
- 線上報名（限報名期間內、設籍縣市者；含證件照上傳）
- 報名進度查詢
- 學員專區（`my.html`）：課程資料、學科測驗、課後問卷

**後台（承辦人員，`/admin`）**
- 儀表板與統計（行政區／里分布、性別、年齡、職業）
- 梯次管理、報名審核、名單管理
- 匯出報名名冊（Excel，符合中央函報格式）
- 課程、講師、課程照片與教材管理；測驗題庫
- 證書領取紀錄與未領取提醒
- 防災士資料庫：匯入歷年培訓名單（範例：`samples/members-import-example.xlsx`）
- 報名成功等 Email 通知（未設定 SMTP 時列為「待發送」，可匯出名單人工寄送）
- 操作紀錄、使用者與角色（`admin`／`staff`）

## 架構

```
瀏覽器 ─▶ (Traefik, TLS) ─▶ web (nginx:alpine)
                              ├─ 靜態頁面：index / register / status / my / news / courses / admin .html
                              └─ /api/*  ─▶ api (Flask + gunicorn)
                                              ├─ SQLite（volume: apidata）
                                              └─ 上傳檔案（volume: uploads）
```

- 前端：純 HTML／CSS／原生 JavaScript，無建置流程
- 後端：Python 3.12、Flask 3、PyJWT、openpyxl、gunicorn
- 資料庫：SQLite（WAL），備份即複製檔案
- 部署：Docker Compose

```
api/            Flask 應用（app/routes 路由、db/init.sql 資料表、tests 測試）
api/app/sites/  縣市設定（keelung.json）
nginx/          nginx 設定（含 /api 反向代理）
samples/        匯入範例檔
source/         原始需求與參考文件（不納入版控）
*.html, site.js 前台與後台頁面
```

## 快速開始

需要 Docker 與 Docker Compose。

1. 建立 `.env`：

   ```
   DRV_HOST=drv.example.org   # 僅 Traefik 部署需要
   JWT_SECRET=<隨機長字串>
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD=<強密碼>
   ```

2. 啟動：

   ```bash
   make up          # 透過 Traefik 部署（需 .env 的 DRV_HOST 與外部網路 galaxy-catalog_default）
   make up-local    # 不使用 Traefik，僅綁定 http://localhost:8020
   ```

首次啟動會自動建立資料表與管理員帳號。後台網址為 `/admin`。

### Make 指令

| 指令 | 說明 |
|---|---|
| `make up` / `down` / `restart` | 啟動（含建置）／停止／重啟（Traefik） |
| `make up-local` / `down-local` / `restart-local` | 同上，不使用 Traefik |
| `make build` | 只建置映像 |
| `make logs` / `make ps` | 查看日誌／容器狀態 |
| `make clean` | 停止並移除映像 |

## 環境變數

| 變數 | 必填 | 說明 |
|---|---|---|
| `JWT_SECRET` | 是 | 後台登入 token 簽章金鑰 |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | 是 | 初始管理員帳號密碼 |
| `DRV_HOST` | Traefik 時 | 對外網域 |
| `SITE_CONFIG` | 否 | 縣市設定檔名（預設基隆市） |
| `SMTP_HOST` `SMTP_PORT` `SMTP_USER` `SMTP_PASSWORD` `SMTP_FROM` | 否 | Email 通知；未設定則不寄送 |

## 測試

```bash
cd api
pip install -r requirements.txt pytest
JWT_SECRET=test pytest tests
```

## 移植到其他縣市

所有縣市專屬內容（機關名稱、聯絡資訊、行政區與村里）都集中在 `api/app/sites/<名稱>.json`，不需改程式。步驟見 [PORTING.md](PORTING.md)。

## 注意事項

- 系統含報名者個資，每個縣市請獨立部署（各自的資料庫與上傳檔）。
- 正式環境請務必更換 `JWT_SECRET` 與管理員密碼，且不要將 `.env` 提交到版控（已列入 `.gitignore`）。

## 授權

[MIT](LICENSE)
