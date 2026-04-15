# Conversation Log — 001

> Non-ticket discussions, architectural decisions, Q&A sessions.
> Max 5000 lines per file. When full, create `conversation-002.md`.
> Format: date, topic, summary of decisions made.

---

## 2026-04-15 — Initial Onboarding

**Topic:** Repository onboarding — first-time documentation creation

**Context:** AI agent performed full codebase analysis and created comprehensive documentation for the `mail-extract` (Công Văn Processor) project.

**Decisions made:**

1. **Documentation structure confirmed:** Created all required files per `universal-onboarding-prompt.md`:
   - `AGENTS.md` — main operating manual
   - `CLAUDE.md` — quick reference
   - `.github/copilot-instructions.md` — coding conventions
   - `docs/architecture/feature-map.md` — feature locations
   - `docs/architecture/api-map.md` — Microsoft Graph + Portal API
   - `docs/architecture/data-flow.md` — exact email→Excel pipeline
   - `docs/architecture/state-management.md` — all state locations
   - `docs/architecture/pattern-cookbook.md` — 12 copy-paste patterns
   - `docs/architecture/known-risks.md` — 15 ranked risks
   - `docs/architecture/async-side-effects.md` — threads, timers, events
   - `docs/tickets/_TEMPLATE.md` — ticket template
   - `docs/conversations/conversation-001.md` — this file
   - Updated `README.md` — added "🤖 AI Agents — Start Here" section

2. **Architecture pattern identified:** Pipeline / Orchestrator — `EmailProcessor` is the central orchestrator; all modules are called directly from it.

3. **Critical ordering constraint documented:** `CLASSIFICATION_RULES` in `src/parser/rules.py` — "Từ chối hủy bỏ HLC" must precede "Cấp toàn bộ" because rejection-of-cancellation documents contain grant-condition phrases in their body text.

4. **Threading model documented:** GUI scan runs in daemon thread; GUI updates only via `self.after(0, callback)`. Login also runs in daemon thread with 120s timeout and countdown callback.

5. **Dedup split documented:** `_processed.json` always stored at `~/.tool_mail_cong_van/<date>/` (local), NOT in the network output folder. This ensures dedup works even when network is down. Risk documented as RISK-005.

6. **Highest-risk areas identified:**
   - RISK-001: Excel locked → email processed but not registered in dedup → re-processed on next run
   - RISK-002: UTC/local time mismatch → wrong date folder
   - RISK-003: Portal HTML structure changes → all portal downloads fail
   - RISK-004: Classification rules ordering

**Codebase stats:**
- Language: Python 3.10+
- Total source files: ~14 Python modules
- Largest file: `src/gui/app.py` (1019 lines)
- Dependencies: msal, requests, PyMuPDF, openpyxl, python-dateutil, playwright, pyinstaller
- Test coverage: parser, dedup, folder routing, portal URL extraction, file naming
- Architecture: No database, no web server — pure desktop automation tool

---

*(Log subsequent conversations below this line)*

