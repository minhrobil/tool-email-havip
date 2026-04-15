# API Map — Microsoft Graph API Endpoints Used

> This tool is a **consumer** of Microsoft Graph API (not a provider).
> All calls go through `src/graph/client.py:GraphClient`.
> Updated: 2026-04-15

---

## Authentication

| Step | Method | Details |
|---|---|---|
| OAuth token | MSAL `acquire_token_silent` | Uses cached accounts, refreshes if expired |
| Interactive login | MSAL `acquire_token_interactive` | Opens browser, `prompt="select_account"` |
| Token cache | MSAL `SerializableTokenCache` | Persisted at `~/.tool_mail_cong_van/token_cache.bin` |

**Required Azure App settings:**
- Type: Public client (Mobile/Desktop)
- Redirect URI: `http://localhost`
- Permissions: `Mail.Read`, `Mail.ReadBasic` (Delegated)

---

## Graph API Endpoints

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
- **Filters:** Skips non-`#microsoft.graph.fileAttachment` types (itemAttachment, referenceAttachment)

### Download Attachment Content (Small Files ≤ 4 MB)

```
GET /me/messages/{message_id}/attachments/{attachment_id}
    ?$select=contentBytes
```

- **Used by:** `AttachmentDownloader._fetch_content()` in `src/mail/downloader.py`
- **Decoding:** Base64 decode of `contentBytes` field
- **Fallback:** If `contentBytes` is empty → uses `$value` endpoint below

### Download Attachment Content (Large Files)

```
GET /me/messages/{message_id}/attachments/{attachment_id}/$value
```

- **Used by:** `GraphClient.get_bytes()` → `AttachmentDownloader._fetch_content()`
- **Returns:** Raw binary bytes (not JSON)

---

## GraphClient Behavior

| Feature | Implementation |
|---|---|
| Base URL | `https://graph.microsoft.com/v1.0` |
| Auth header | `Authorization: Bearer {token}` (auto-injected in `__init__`) |
| Rate limiting | HTTP 429 → sleep `Retry-After` seconds, retry up to 3 times |
| Token expired | HTTP 401 → raise `PermissionError("Access token expired...")` |
| Pagination | `paginate()` generator follows `@odata.nextLink` automatically |
| Binary download | `get_bytes()` → separate method, returns `bytes` |
| Max retries | `_MAX_RETRIES = 3` |
| Default backoff | `_DEFAULT_BACKOFF = 5` seconds (when `Retry-After` header missing) |

---

## Portal API (IP Vietnam Government Portal)

The portal is NOT a standard REST API — it is a web page accessed via Playwright browser automation.

| Step | Method | Details |
|---|---|---|
| Navigate to portal | `page.goto(url, timeout=15000, wait_until="networkidle")` | URL extracted from email body |
| Find download button | `page.locator(selector).first` | Tries selectors in `portal.download_button_selectors` order |
| Click button | `btn.click(timeout=5000)` | Triggers browser native file download |
| Capture downloads | `page.on("download", handler)` | All downloads captured via event listener |
| Save files | `download.save_as(str(dest))` | Must happen BEFORE `browser.close()` |
| Error detection | `_is_error_page(page)` | Checks page title for "404", "403", "500", "error", etc. |

**Portal URL patterns** (configured in `config.json`):
- `ipvietnam.gov.vn`
- `dichvucong.ipvietnam`

**Download button selectors** (tried in order):
1. `button:has-text('Tải tất cả')`
2. `a:has-text('Tải tất cả')`
3. `button:has-text('Tải xuống tất cả')`
4. `a:has-text('Tải xuống tất cả')`
5. `[class*='download-all']`

