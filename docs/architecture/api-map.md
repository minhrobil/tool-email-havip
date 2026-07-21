# API Map — Microsoft Graph

> This repo is a **consumer** of Microsoft Graph API.
> Updated: 2026-05-05

---

## Authentication

| Step | Method | Details |
|---|---|---|
| OAuth token | MSAL `acquire_token_silent` | Uses cached accounts, refreshes if expired |
| Interactive login (GUI/headless bootstrap) | MSAL `acquire_token_interactive` | Opens browser, `prompt="select_account"` |
| Token cache | MSAL `SerializableTokenCache` | Persisted at `~/.tool_mail_cong_van/token_cache.bin` |

**Required Azure App settings:**
- Type: Public client (Mobile/Desktop)
- Redirect URI for GUI/native flow: `http://localhost`
- Permissions: `Mail.Read`, `Mail.ReadBasic` (Delegated)

---

## Microsoft Graph API Endpoints

### List Top-Level Mail Folders

```
GET /me/mailFolders
    ?$select=id,displayName,childFolderCount
    &$top=100
```

- **Used by:** `MailReader.find_cong_van_folder()` in `src/mail/reader.py`
- **Returns:** Array of folder objects
- **Pagination:** via `@odata.nextLink`

### List Child Folders

```
GET /me/mailFolders/{folder_id}/childFolders
    ?$select=id,displayName,childFolderCount
    &$top=100
```

- **Used by:** `MailReader._search_children()` in `src/mail/reader.py`
- **Recursion:** Yes — searches all nested levels

### List Messages in Folder

```
GET /me/mailFolders/{folder_id}/messages
    ?$select=id,internetMessageId,subject,sender,receivedDateTime,hasAttachments,bodyPreview,body
    &$top=50
    &$orderby=receivedDateTime desc
    &$filter=receivedDateTime ge {UTC_ISO} and receivedDateTime le {UTC_ISO}
```

- **Used by:** `MailReader.get_messages()` in `src/mail/reader.py`
- **Body field:** Full HTML or text body is fetched (`body` select) for portal URL extraction
- **Filter:** OData `$filter` on `receivedDateTime` — dates converted to UTC ISO 8601 via `_to_utc_str()`
- **Pagination:** via `GraphClient.paginate()` following `@odata.nextLink`
- **Auth scope required:** `Mail.Read`

### List Attachments (Metadata Only)

```
GET /me/messages/{message_id}/attachments
    ?$select=id,name,contentType,size,isInline,@odata.type
```

- **Used by:** `AttachmentDownloader.list_attachments()` in `src/mail/downloader.py`
- **Filters:** Skips non-file attachment types

### Download Attachment Content (Small Files ≤ 4 MB)

```
GET /me/messages/{message_id}/attachments/{attachment_id}
    ?$select=contentBytes
```

- **Used by:** `AttachmentDownloader._fetch_content()` in `src/mail/downloader.py`
- **Decoding:** Base64 decode of `contentBytes`
- **Fallback:** If `contentBytes` is empty → uses `$value` endpoint below

### Download Attachment Content (Large Files)

```
GET /me/messages/{message_id}/attachments/{attachment_id}/$value
```

- **Used by:** `GraphClient.get_bytes()` → `AttachmentDownloader._fetch_content()`
- **Returns:** Raw binary bytes

---

## GraphClient Behavior

| Feature | Implementation |
|---|---|
| Base URL | `https://graph.microsoft.com/v1.0` |
| Auth header | `Authorization: Bearer {token}` auto-injected in `GraphClient.__init__()` |
| Rate limiting | HTTP 429 → sleep `Retry-After`, retry up to 3 times |
| Token expired | HTTP 401 → raise `PermissionError("Access token expired...")` |
| Pagination | `paginate()` follows `@odata.nextLink` automatically |
| Binary download | `get_bytes()` returns `bytes` |
| Max retries | `_MAX_RETRIES = 3` |
| Default backoff | `_DEFAULT_BACKOFF = 5` seconds |

---

## Portal Automation Surface (IP Vietnam Portal)

The portal is **not** a REST API. It is automated through Playwright in `src/portal/browser_downloader.py`.

| Step | Method | Details |
|---|---|---|
| Navigate to portal | `page.goto(url, timeout=30000, wait_until="networkidle")` | URL extracted from email body or constructed from access code |
| Enter access code | `_enter_access_code(page, access_code, result)` | Fills textbox + clicks submit (or presses Enter) when portal requires a lookup code |
| Find bulk download button | `page.locator(selector).first` | Tries selectors from `portal.download_button_selectors` in order |
| Fallback to item links | `_click_file_items()` | Clicks each `a.file-item__title` link if bulk button is missing or yields no downloads |
| Capture downloads | `page.on("download", handler)` | All downloads captured via event listener |
| Save files | `download.save_as(str(dest))` | Must happen before `browser.close()` |
| Error detection | `_is_error_page(page)` | Checks page title for `404`, `403`, `500`, `error`, etc. |

**Portal URL extraction details** (`src/portal/url_extractor.py`):
- `_hrefs_from_html()` HTML-unescapes `href="..."` values
- `_bare_urls()` scans text/HTML, strips trailing punctuation, and applies `html.unescape()`
- If no URL is found, `extract_portal_access_code()` may still produce a constructed fallback URL: `https://thongbao.ipvietnam.gov.vn/tra-cuu-don/{access_code}`
