# Web Migration Assessment — Xử lý Mail Công Văn

> Đánh giá khả năng chuyển đổi từ Tkinter desktop app sang web application.
> Ngày đánh giá: 22/04/2026

---

## 1. Kiến trúc hiện tại (Desktop)

```
┌─────────────────────────────────────────────┐
│              Tkinter GUI (app.py)            │
│  Login │ Dashboard │ Stats │ Activity Log    │
├─────────────────────────────────────────────┤
│         EmailProcessor (ThreadPool)          │
├──────┬──────┬──────┬──────┬──────┬──────────┤
│ Auth │Graph │ Mail │Portal│Parser│  Excel    │
│ MSAL │Client│Reader│Playw.│Rules │  Writer   │
├──────┴──────┴──────┴──────┴──────┴──────────┤
│  Local filesystem / Network share (SMB)      │
│  JSON dedup / Token cache                    │
└─────────────────────────────────────────────┘
```

**Đặc điểm:**
- Single-user, single-machine
- MSAL public client (device code / interactive browser)
- File I/O trực tiếp: Excel (openpyxl), JSON dedup, network share
- Playwright browser automation cho portal download
- Threading: `ThreadPoolExecutor` + `self.after(0, cb)` cho GUI updates

---

## 2. Architecture Mapping: Desktop → Web

| Component Desktop | Web Equivalent | Ghi chú |
|---|---|---|
| `tkinter.Tk` GUI | React + TypeScript + Tailwind | SPA, responsive |
| `threading.Thread` worker | Celery + Redis task queue | Background job processing |
| `self.after(0, callback)` | WebSocket / SSE push | Real-time progress updates |
| `config.json` (local) | Env vars + DB config table | Multi-tenant ready |
| MSAL public client | MSAL.js (SPA) hoặc MSAL confidential (server) | OAuth2 authorization code flow |
| `token_cache.bin` (local) | Redis / encrypted DB column | Per-user token storage |
| `openpyxl` Excel write | Server-side openpyxl → download link | Generate & serve file |
| `_processed.json` dedup | PostgreSQL table `processed_emails` | Queryable, multi-user |
| Network share `\\LIENDO\...` | Server mounts SMB share / S3 bucket | Cần infra setup |
| `subprocess taskkill EXCEL` | N/A | Không áp dụng trên web |
| Playwright portal download | Server-side Playwright in Docker | Headless container |
| Auto-scan scheduler | Celery Beat / APScheduler | Cron-like scheduling |

---

## 3. Đánh giá Complexity từng Module

### 🟢 Low Complexity (dùng gần nguyên bản)

| Module | File | Lý do |
|---|---|---|
| Graph HTTP client | `src/graph/client.py` | Pure HTTP, chạy server-side nguyên bản |
| Mail reader | `src/mail/reader.py` | Pure logic, không phụ thuộc UI |
| Parser rules | `src/parser/rules.py` | Pure regex/logic, zero I/O dependency |
| URL extractor | `src/portal/url_extractor.py` | Pure string processing |
| Config loader | `src/config.py` | Chỉ cần đổi source từ file → env/DB |

### 🟡 Medium Complexity (cần refactor)

| Module | File | Thay đổi cần thiết |
|---|---|---|
| Auth | `src/auth/graph_auth.py` | Đổi sang MSAL confidential client, token cache → Redis |
| Excel writer | `src/excel/writer.py` | Server-side generate, serve qua download endpoint |
| Dedup manager | `src/dedup/manager.py` | JSON file → PostgreSQL table |
| Folder routing | `src/folder/routing.py` | Network path → server filesystem / cloud storage |
| Browser downloader | `src/portal/browser_downloader.py` | Chạy trong Docker container, manage lifecycle |
| Email processor | `src/processor/email_processor.py` | ThreadPool → Celery tasks, progress → WebSocket |

### 🔴 High Complexity (rewrite)

| Module | File | Thay đổi cần thiết |
|---|---|---|
| GUI | `src/gui/app.py` | Rewrite hoàn toàn → React components |
| Attachment downloader | `src/mail/downloader.py` | Cần streaming to server storage thay vì local disk |

---

## 4. Recommended Web Stack

```
┌──────────────── Frontend ─────────────────┐
│  React 18 + TypeScript                     │
│  Tailwind CSS + shadcn/ui                  │
│  MSAL.js (@azure/msal-browser)             │
│  WebSocket client (scan progress)          │
└────────────────────┬──────────────────────┘
                     │ REST API + WebSocket
┌────────────────────▼──────────────────────┐
│  FastAPI (Python 3.11+)                    │
│  ├─ /api/auth/* — token relay              │
│  ├─ /api/scan — trigger scan               │
│  ├─ /api/stats — get statistics            │
│  ├─ /api/export — download Excel           │
│  ├─ /ws/progress — scan progress stream    │
│  └─ Background: Celery workers             │
├────────────────────────────────────────────┤
│  PostgreSQL (dedup, config, scan history)   │
│  Redis (task queue, token cache, sessions)  │
│  Playwright container (portal downloads)    │
└────────────────────────────────────────────┘
```

**Tại sao FastAPI?**
- Python → tái sử dụng tối đa code backend hiện tại (graph, mail, parser, excel, dedup)
- Native async + WebSocket support
- Type hints align với codebase hiện tại (dataclasses)

---

## 5. Migration Phases

### Phase 1: API Backend (2–3 tuần)
- Wrap existing modules trong FastAPI endpoints
- Setup PostgreSQL schema (dedup, scan_history, config)
- Migrate `_processed.json` → DB
- Auth: MSAL confidential client trên server
- Endpoint: `POST /api/scan`, `GET /api/stats`, `GET /api/export`

### Phase 2: React Frontend (2–3 tuần)
- Login page (MSAL.js redirect flow)
- Dashboard: scan controls, date range, stat cards
- Activity log component
- File download (Excel export)

### Phase 3: Real-time & Scheduler (1–2 tuần)
- WebSocket endpoint `/ws/progress`
- Celery Beat cho auto-scan scheduling
- Toast/notification system trên frontend

### Phase 4: Deployment & Testing (1 tuần)
- Docker Compose: FastAPI + Celery + Redis + PostgreSQL + Playwright
- Nginx reverse proxy
- E2E testing
- Migration script từ existing `_processed.json` → DB

**Tổng ước tính: 6–9 tuần** (1 developer full-time)

---

## 6. Risks & Blockers

| Risk | Impact | Mitigation |
|---|---|---|
| **Network share access** (`\\LIENDO\...`) | Server cần SMB mount | Mount SMB trong Docker hoặc deploy trên Windows Server cùng network |
| **Excel lock detection** | Không có `~$` lock file từ web | Implement file-level locking trong DB, hoặc generate Excel on-demand (không ghi trực tiếp lên share) |
| **Playwright memory** | Chromium ~200MB RAM per instance | Pool/queue Playwright instances, limit concurrency |
| **Multi-user conflicts** | 2 users cùng scan, cùng ghi Excel | Database-level locking, queue per output folder |
| **MSAL token refresh** | Server cần refresh token tự động | Implement token refresh middleware, handle errors gracefully |
| **Portal site changes** | Download selectors thay đổi | Config-driven selectors (đã có), nhưng cần monitoring |
| **Migration downtime** | Chuyển dữ liệu cũ | Script convert `_processed.json` → DB, chạy offline |

---

## 7. Decision Matrix

| Tiêu chí | Desktop (hiện tại) | Web (proposed) |
|---|---|---|
| Deploy & update | Khó (build exe, phân phối) | Dễ (deploy server, user truy cập URL) |
| Multi-user | ❌ Single machine | ✅ Nhiều user đồng thời |
| Cross-platform | ❌ Windows only | ✅ Mọi browser |
| Monitoring | ❌ Không có | ✅ Centralized logging, metrics |
| Offline access | ✅ Chạy local | ❌ Cần kết nối server |
| Network share | ✅ Direct UNC path | ⚠ Cần SMB mount |
| Development effort | ✅ Đã có | ⚠ 6-9 tuần |
| Maintenance | ❌ Fix per machine | ✅ Fix một lần, deploy cho tất cả |

---

## 8. Kết luận

**Khả năng migrate: KHẢ THI** — backend modules (70% codebase) có thể tái sử dụng gần nguyên bản trong FastAPI. Thách thức chính nằm ở:

1. **Network share integration** — cần infrastructure setup
2. **Real-time progress** — cần WebSocket, phức tạp hơn `self.after()`
3. **Frontend rewrite** — GUI layer phải viết lại hoàn toàn

**Khuyến nghị:** Nếu số lượng user > 2–3 người hoặc cần truy cập từ nhiều máy → nên migrate. Nếu chỉ 1 user trên 1 máy → desktop đủ tốt, chỉ cần enhance UI.
