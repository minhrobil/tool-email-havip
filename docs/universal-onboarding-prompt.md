# Universal Repository Onboarding Prompt for AI Coding Agents

> Copy prompt bên dưới, paste vào AI agent (Claude, Copilot, Codex, Cursor, ChatGPT...), thay `{placeholders}` bằng thông tin thực tế. Prompt này hoạt động cho mọi loại project.

---

## 🚀 THE PROMPT — Copy từ đây

```
You are onboarding yourself to this repository as a long-term coding agent. Your goal is to deeply understand the codebase and produce comprehensive documentation that allows ANY AI agent (including yourself in future sessions) to immediately start working on tasks without re-reading source code.

## Repository Info
- **Repo path**: {path/to/repo}
- **Project type**: {e.g., React Native mobile app / Next.js fullstack / Django REST API / Monorepo with multiple services}
- **Languages**: {e.g., TypeScript, Python, Go}
- **Key frameworks**: {e.g., React Native 0.79, FastAPI, Spring Boot — or say "discover from package files"}

## What to Inspect

### Phase 1 — Discover the Stack (read config files first)
Read these files to understand the technology stack:
- Package/dependency files: package.json, requirements.txt, go.mod, Cargo.toml, build.gradle, pom.xml, Gemfile, etc.
- Config files: tsconfig.json, .env.example, docker-compose.yml, webpack.config.js, etc.
- Entry points: index.ts, main.py, App.tsx, cmd/main.go, etc.
- CI/CD: .github/workflows/, Dockerfile, Makefile, etc.

### Phase 2 — Understand Architecture (read source code)
For EACH layer of the application, identify and document:

**Data Layer:**
- Database schema / ORM models / domain models
- How data flows: API → processing → storage → UI
- State management approach (Redux? Singleton? Context? Zustand? Pinia?)
- Caching strategy (in-memory, Redis, AsyncStorage, localStorage)
- Offline/sync strategy if applicable

**Service/Business Logic Layer:**
- Core service files — where business logic lives
- How services communicate (direct calls? event bus? message queue?)
- Authentication & authorization flow
- Error handling patterns
- External API integrations

**API Layer (if backend or fullstack):**
- All endpoints with method, path, handler, auth requirements
- Request/response formats
- Error response patterns
- Rate limiting, pagination, versioning

**UI Layer (if frontend or mobile):**
- Component hierarchy and reusable components
- Navigation/routing structure
- Styling system (CSS modules? Tailwind? styled-components? theme tokens?)
- Form patterns, validation approach

**Cross-cutting:**
- Logging & monitoring (Sentry, DataDog, custom)
- i18n/localization setup
- Feature flags if any
- Environment configuration (dev/staging/prod)

### Phase 3 — Identify Patterns & Risks
- What patterns does the codebase follow? (MVC? Clean Architecture? Singleton services? Repository pattern?)
- What are the "copy-paste" patterns for common tasks? (adding a new endpoint, screen, model, migration)
- What are the fragile/risky areas? (tightly coupled modules, no tests, complex legacy code)
- What's the test situation? (unit tests? integration? E2E? or no tests at all?)
- Known tech debt or deprecated code?

## Deliverables — Files to Create

Create the following documentation files. Use Markdown. Be precise — cite actual file names, function names, and line numbers.

### Required Files:

1. **`AGENTS.md`** (root) — Main operating manual for AI agents
   - Repository overview (tech stack, architecture pattern, key dependencies)
   - Folder structure with purpose of each folder
   - Architecture rules (how data flows, how modules communicate)
   - How to safely add new features (step-by-step for each type: endpoint, screen, model, etc.)
   - Critical dependencies between modules
   - Common pitfalls (things that break silently)
   - Pre-submit checklist
   - Build/run/test/lint commands
   - Environment setup

2. **`CLAUDE.md`** (root) — Quick reference for Claude (also useful for any agent)
   - Fast repo map (key files with 1-line descriptions)
   - Access patterns for core objects (how to get current user, database connection, config, etc.)
   - What NOT to break (fragile areas)
   - Important commands

3. **`.github/copilot-instructions.md`** — Compact conventions for GitHub Copilot
   - Code style patterns with examples
   - Naming conventions
   - Data access patterns with code snippets
   - Validation checklist before proposing changes
   - Critical files list (do not modify without understanding impact)

4. **`docs/architecture/feature-map.md`** — All features/modules documented
   - For each feature: screens/endpoints, services, models, data flow

5. **`docs/architecture/api-map.md`** — All API endpoints (if applicable)
   - Method, path, handler, auth, description, request/response format

6. **`docs/architecture/data-flow.md`** — How data moves through the system
   - Read path (API/DB → processing → cache → UI)
   - Write path (user action → validation → mutation → persistence → sync)
   - Startup/initialization sequence

7. **`docs/architecture/state-management.md`** — Where state lives
   - All state locations (global store, singletons, context, local state)
   - How state updates propagate to UI
   - Persistence strategy

8. **`docs/architecture/component-catalog.md`** (if frontend/mobile)
   - All reusable UI components with props and usage examples
   - Color palette, icon set, typography
   - Toast/notification patterns

9. **`docs/architecture/pattern-cookbook.md`** — Copy-paste patterns
   - 8-15 patterns for the most common tasks in this codebase
   - Each pattern: when to use, step-by-step, code template, pitfalls
   - Import paths quick reference

10. **`docs/architecture/known-risks.md`** — Ranked list of fragile areas
    - Critical / Medium / Low risk items
    - Location, risk description, mitigation

11. **`docs/tickets/_TEMPLATE.md`** — Template for per-ticket documentation
    Structure of Section 0 (mandatory):
    ```
    ### 📋 Tiến độ xử lý (Work Progress)
    - [ ] 🔍 Xác định nguyên nhân gốc rễ
    - [ ] 🛠️ Triển khai fix trong code
    - [ ] 🌐 Thêm key dịch thuật nếu cần
    - [ ] 🧪 Kiểm thử thủ công
    - [ ] 📄 Tài liệu ticket hoàn chỉnh

    ### 🎯 Các vấn đề cần giải quyết / Issues to Resolve
    - [ ] [ticket-specific bug/feature 1]
    - [ ] [ticket-specific bug/feature 2]
    ```
    Remaining sections: summary (EN+native language), root cause, solution, files changed, testing, risks, code reference.

12. **`docs/conversations/conversation-001.md`** — First conversation log file
    - Log all non-ticket discussions here
    - Max 5000 lines per file, then create conversation-002.md, etc.
    - Format: date, topic, summary of decisions made

### For Monorepos / Multi-service Projects, ALSO create:

12. **`docs/architecture/service-map.md`** — How services connect
    - Service topology diagram (text-based)
    - Communication protocols (REST, gRPC, message queue, shared DB)
    - Which service owns which data
    - Deployment dependencies

13. **Per-service AGENTS.md** — Each service/package gets its own mini-AGENTS.md
    - `services/auth/AGENTS.md`
    - `services/api/AGENTS.md`
    - `packages/shared/AGENTS.md`
    - etc.

### Optional but High-Value:

14. **`docs/architecture/navigation-map.md`** (mobile/SPA) — Full route tree
15. **`docs/architecture/async-side-effects.md`** — Background jobs, event listeners, timers, webhooks
16. **`docs/architecture/integration-points.md`** — Third-party services, native modules, external APIs
17. **`docs/prompting-guide.md`** — How to write effective prompts for this specific codebase

## Output Quality Requirements

- **Cite real code**: Use actual file paths, function names, class names from the repo. Never make up names.
- **Be precise about data flow**: Trace the EXACT path data takes, not a generic description.
- **Include code snippets**: Show actual access patterns, not pseudocode.
- **Flag ambiguity**: If something is unclear or seems broken, say so explicitly.
- **Prioritize actionability**: An agent reading your docs should be able to start coding within 5 minutes.

## File Writing Rules
- Create all files using your file creation tools — do NOT just output markdown to chat.
- Use Markdown with proper headers, tables, and code blocks.
- Keep each file focused on its topic. Don't duplicate content across files.
- Use relative paths for cross-references between docs.

## After Creating Docs, Verify:
- [ ] Can an agent find ANY feature's code location from feature-map.md?
- [ ] Can an agent add a new [endpoint/screen/model] by following pattern-cookbook.md?
- [ ] Can an agent find the right UI component from component-catalog.md?
- [ ] Are all critical files listed with "do not modify without understanding" warnings?
- [ ] Are known risks ranked and explained?
- [ ] Is the ticket template ready to use?
- [ ] Does README.md have an "🤖 AI Agents — Start Here" section linking to AGENTS.md?
- [ ] Does .github/copilot-instructions.md contain ALL workflow rules (see below)?

## Workflow Rules to Embed in `.github/copilot-instructions.md`

This section MUST be included in the copilot-instructions.md you create.
These are the operating rules that govern HOW agents work on this project — not just what the code does.

```markdown
## 🎯 Coding Philosophy (Non-negotiable)

> These rules apply to EVERY change, regardless of size.

1. **Minimal diff** — Change the least amount of code necessary to solve the problem.
   Do NOT refactor surrounding code, rename variables, or reformat lines not directly related to the task.
   A reviewer should be able to see exactly what changed and why.

2. **Follow existing conventions first** — Before writing any code, observe:
   - How existing files in the same folder are structured
   - What naming pattern is already used (camelCase? snake_case? PascalCase?)
   - What import style is used (named vs default, relative vs absolute)
   - What component/class pattern is used
   Match the existing pattern even if you personally prefer a different style.

3. **Language best practices** — Code must follow the idiomatic style of the language.
   Code that would **fail SonarQube** or be **rejected in code review** is not acceptable:
   - No dead code, no commented-out blocks, no debug logs left in
   - No direct state mutation
   - Cleanup all side effects (event listeners, timers, subscriptions)
   - No memory leaks

4. **Design patterns** — Use the pattern already established in the codebase.
   When no pattern exists, use the simplest well-known pattern (Strategy, Observer, Factory, Repository).
   Do NOT invent new base classes or architectural layers.

5. **No sloppy shortcuts** — Forbidden regardless of urgency:
   - Suppressing type errors (`@ts-ignore`, `as any`, `// eslint-disable`) without explanation
   - Hardcoded strings, colors, IDs that should be constants or config
   - Bypassing the established data mutation/persistence pipeline
   - Side-effect listeners without cleanup

## 📋 Mandatory Workflow Rules

1. **Before starting any ticket/task** — check `docs/tickets/` for previous fixes in the same area.
   If no ticket file exists yet, create one from `docs/tickets/_TEMPLATE.md` before writing code.

2. **After completing any ticket/task** — create or update `docs/tickets/ticket-{ID}-{slug}.md`.
   File must be bilingual (English + team's native language) and include:
   - Issue summary (symptoms only, not causes)
   - Root cause analysis (file names, function names, logic failure)
   - Solution (what changed and why)
   - Files changed (table)
   - Testing guidance
   - Related risks

3. **Non-ticket conversations** — log to `docs/conversations/conversation-{N}.md`.
   Max 5000 lines per file. When full, create the next numbered file.

4. **Ticket files MUST have Section 0** with two checklists:
   - `### 📋 Tiến độ xử lý` — 5-step progress tracking (root cause → fix → i18n → test → doc)
   - `### 🎯 Các vấn đề cần giải quyết` — ticket-specific bugs/features (fill in manually)

5. **Language rule** — all notes in the team's native language MUST use correct diacritics/accents.
   (e.g., Vietnamese: "người dùng" NOT "nguoi dung")

6. **Never modify these critical files without reading them fully first**:
   {list the project's critical files here — e.g., main service files, auth middleware, etc.}
```

START by reading the root config/entry files, then systematically work through the codebase. Do NOT guess — read actual files before documenting anything.
```

---

## 📝 Hướng dẫn sử dụng

### Cho single repo (backend hoặc frontend):
1. Copy toàn bộ prompt trên
2. Thay `{placeholders}` ở phần "Repository Info"
3. Xóa các deliverable không liên quan (ví dụ: xóa `component-catalog.md` nếu là pure backend)
4. Paste vào AI agent và để nó chạy

### Cho monorepo / multi-repo:
1. Copy toàn bộ prompt trên
2. Thay `{placeholders}` — liệt kê tất cả services/packages
3. Giữ nguyên section "For Monorepos" 
4. Thêm vào phần Repository Info:
```
- **Services**:
  - services/auth — Authentication service (Node.js/Express)
  - services/api — Main API (Python/FastAPI)  
  - services/worker — Background job processor (Go)
  - packages/shared — Shared types & utilities (TypeScript)
  - frontend/ — Web app (Next.js)
  - mobile/ — Mobile app (React Native)
```

### Cho project đã có docs cũ:
Thêm dòng này vào đầu prompt:
```
This repo already has some documentation. Read existing docs first, 
then UPDATE/EXTEND them rather than creating from scratch. 
Preserve any existing content that is still accurate.
```

### Cho project mới (greenfield):
Thêm dòng này vào đầu prompt:
```
This is a new project with minimal code. Focus on documenting:
- The chosen architecture patterns and WHY they were chosen
- Setup/bootstrap instructions
- The first 5 patterns that new contributors will need
- Placeholder sections for features not yet built
```

---

## Thời gian ước tính

| Project size | Thời gian onboarding |
|---|---|
| Nhỏ (< 50 files) | 10-15 phút |
| Trung bình (50-200 files) | 20-40 phút |
| Lớn (200-500 files) | 40-90 phút |
| Monorepo (500+ files) | 1-3 giờ (có thể cần chia thành nhiều session) |

---

## Checklist sau khi onboarding xong

### Architecture docs
- [ ] `AGENTS.md` tồn tại ở root với "⚡ START HERE" table ưu tiên đọc
- [ ] `README.md` có section "🤖 AI Agents — Start Here" trỏ đến AGENTS.md
- [ ] `pattern-cookbook.md` có ít nhất 8 pattern copy-paste
- [ ] `component-catalog.md` liệt kê tất cả reusable components (nếu có UI)
- [ ] `known-risks.md` có ít nhất 10 risk items được ranked
- [ ] Tất cả file names, function names trong docs là THỰC (không bịa)
- [ ] Mỗi service trong monorepo có AGENTS.md riêng

### Workflow system
- [ ] `docs/tickets/_TEMPLATE.md` có Section 0 với 2 sub-checklist (Tiến độ + Issues to Resolve)
- [ ] `docs/conversations/conversation-001.md` đã được tạo
- [ ] `.github/copilot-instructions.md` có đầy đủ Mandatory Workflow Rules (6 rules)
- [ ] `docs/prompting-guide.md` có template prompt cho bug fix, feature, UI change
- [ ] `AGENTS.md` trỏ đến `pattern-cookbook.md` và `component-catalog.md` ở mức 🔴 Always

