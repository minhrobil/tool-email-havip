# docs/tickets/_TEMPLATE.md

> Copy this file, rename to `ticket-{ID}-{slug}.md`, fill in Section 0 FIRST.

---

# Ticket: {ID} — {Short Title}

## Section 0 — Bắt buộc (Mandatory)

### 📋 Tiến độ xử lý (Work Progress)
- [ ] 🔍 Xác định nguyên nhân gốc rễ
- [ ] 🛠️ Triển khai fix trong code
- [ ] 🌐 Thêm key dịch thuật nếu cần
- [ ] 🧪 Kiểm thử thủ công
- [ ] 📄 Tài liệu ticket hoàn chỉnh

### 🎯 Các vấn đề cần giải quyết / Issues to Resolve
- [ ] [Mô tả vấn đề cụ thể 1 — điền vào đây]
- [ ] [Mô tả vấn đề cụ thể 2 — điền vào đây]

---

## 1. Tóm tắt / Summary

**English:**
> One-paragraph description of what the bug/feature is, from the user's perspective. What symptoms are visible?

**Tiếng Việt:**
> Mô tả ngắn về bug/tính năng từ góc nhìn người dùng. Triệu chứng nào có thể quan sát được?

---

## 2. Nguyên nhân gốc rễ / Root Cause

**English:**
> Exact technical reason. Include file names, function names, line numbers, and the specific logic failure.

**Tiếng Việt:**
> Nguyên nhân kỹ thuật chính xác. Bao gồm tên file, tên hàm, số dòng, và logic bị lỗi.

Example:
```
File: src/parser/rules.py
Function: classify_document()
Issue: Rule "Từ chối hủy bỏ HLC" was missing from CLASSIFICATION_RULES,
       so these documents were being classified as "Cấp toàn bộ" (wrong).
```

---

## 3. Giải pháp / Solution

**What changed and why:**

```python
# Before:
CLASSIFICATION_RULES = [
    ("Dự định từ chối", ["dự định từ chối"]),
    ...
]

# After:
CLASSIFICATION_RULES = [
    ("Dự định từ chối", ["dự định từ chối"]),
    ("Từ chối hủy bỏ HLC", ["từ chối", "hủy bỏ hiệu lực"]),  # ← Added
    ...
]
```

---

## 4. Files Changed

| File | Change type | Description |
|---|---|---|
| `src/parser/rules.py` | Modified | Added new classification rule |
| `tests/test_parser.py` | Modified | Added test case for new rule |

---

## 5. Testing / Kiểm thử

**Manual test steps:**
1. Run the tool against an email containing "từ chối hủy bỏ hiệu lực"
2. Verify the Excel output shows "Từ chối hủy bỏ HLC" in the "Loại công văn" column

**Automated tests:**
```bash
python -m pytest tests/test_parser.py -v
```

**Expected result:** All tests pass; classification matches expected label.

---

## 6. Rủi ro / Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| New rule may conflict with existing rules | Low | Tests verify all existing rule cases still pass |
| Order of rules matters | Medium | Added comment explaining ordering constraint |

---

## 7. Code Reference

```python
# src/parser/rules.py, lines 136-150
CLASSIFICATION_RULES: List[tuple] = [
    # ... see actual file for current state
]
```

---

## 8. Related

- Related ticket: [none]
- Related risk: RISK-004 in `docs/architecture/known-risks.md`
- Related pattern: Pattern 1 in `docs/architecture/pattern-cookbook.md`

