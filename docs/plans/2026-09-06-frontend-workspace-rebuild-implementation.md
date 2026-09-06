# Frontend Workspace Rebuild Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox state as review evidence.

**Goal:** Rebuild the entire Travel Agent frontend into a modern, workspace-centric travel operating system client (React 18 + Vite + Tailwind CSS + Lucide Icons) connecting to Workspaces, Conversations, Planner State, and Local Token Authentication.

**Architecture:** Workspace-Centric Dual Pane (Sidebar + Chat Panel + Interactive Itinerary Timeline), Light Mode with Warm Heritage & Coastal Sunshine theme, hybrid token authentication, and 1-click onboarding.

**Tech Stack:** React 18, Vite 5, Tailwind CSS 3, Lucide React, Axios, React-Markdown, Vitest.

**Spec:** [`docs/specs/2026-09-06-frontend-workspace-rebuild-design.md`](../specs/2026-09-06-frontend-workspace-rebuild-design.md) (Version 0.1, Approved).

| Field | Value |
| --- | --- |
| Status | Completed |
| Date | 2026-09-06 |
| Approved specification | `docs/specs/2026-09-06-frontend-workspace-rebuild-design.md` v0.1 |
| Execution owner | Implementer Subagent |
| Decision owner | Repository owner |
| Scope | `frontend/` (full overhaul of UI components, design tokens, API services, and unit tests) |
| Verification | `npm run lint`, `npm run test`, `npm run build`, browser validation flow |

---

## Global Constraints

1. **Light Mode Only:** No dark-mode styles or toggles. Use Warm Heritage palette (Terracotta `#E05D38`, Amber `#F59E0B`, Coastal Teal `#0D9488`, ivory/cream surface `#FDFBF7`).
2. **AI-Driven Planner Contract:** No inline manual editing of itinerary timeline items; all changes flow through AI chat and `/accept` action to preserve backend operation log integrity.
3. **Strict Content-Free Errors & Security:** Never display raw tokens or unhandled server internal traces in UI; handle 401 and 404 cleanly.
4. **Isolated Worktree Implementation:** Implementation must execute in an isolated Git worktree (`mode: branch`) without modifying the primary working tree before owner delivery.

---

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `frontend/package.json` | Dependencies: add `tailwindcss`, `postcss`, `autoprefixer`, `lucide-react` | Baseline |
| `frontend/tailwind.config.js` | Tailwind theme configuration with Warm Heritage color tokens | Task 1 |
| `frontend/postcss.config.js` | PostCSS config for Tailwind | Task 1 |
| `frontend/src/index.css` | Global styles, typography, and CSS variables | Task 1 |
| `frontend/src/services/api.js` | Axios instance with Bearer interceptor and error normalization | Task 1 |
| `frontend/src/services/auth.js` | Token storage in `localStorage`, preset user profiles | Task 2 |
| `frontend/src/services/workspaces.js` | CRUD client for `/api/v1/workspaces` | Task 2 |
| `frontend/src/services/chat.js` | Client for `/api/v1/chat` and `/api/v1/conversations` | Task 2 |
| `frontend/src/services/planner.js` | Client for `/api/v1/workspaces/{id}/planner/...` | Task 2 |
| `frontend/src/services/api.test.js` | Vitest test suite for API client and token injection | Task 2 |
| `frontend/src/components/auth/LoginModal.jsx` | Hybrid login screen with manual token input & quick presets | Task 2, 3 |
| `frontend/src/components/layout/Header.jsx` | App branding, mobile tab switcher, user badge, token indicator | Task 1, 3 |
| `frontend/src/components/layout/Sidebar.jsx` | Workspace list, new trip button (`+`), logout action | Task 2, 4 |
| `frontend/src/components/welcome/WelcomeView.jsx` | 1-Click Starter Cards onboarding empty state | Task 2, 5 |
| `frontend/src/components/chat/ChatPanel.jsx` | Scrollable message container with auto-scroll | Task 2, 6 |
| `frontend/src/components/chat/ChatMessage.jsx` | Markdown rendering, citation badges, action cards | Task 6 |
| `frontend/src/components/chat/ChatInput.jsx` | Auto-growing textarea with send button & shortcuts | Task 6 |
| `frontend/src/components/chat/CitationDrawer.jsx` | Slide-over drawer for reading extracted travel sources | Task 6 |
| `frontend/src/components/planner/PlannerPanel.jsx` | Version switcher, status badge, accept button, decisions | Task 2, 7 |
| `frontend/src/components/planner/ItineraryTimeline.jsx` | Day-by-day structured itinerary activities list | Task 7 |
| `frontend/src/components/planner/ItineraryItemCard.jsx` | Activity card with icons (`meal`, `lodging`, `activity`...) | Task 7 |
| `frontend/src/App.jsx` | Root state machine (Auth, Workspaces, Dual Pane layout, Mobile tabs) | Tasks 1–7 |
| `frontend/tests/components.test.jsx` | Vitest test suite for core UI components | Tasks 3–8 |

---

## Task 1: Setup Styling Infrastructure & Design System

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/tailwind.config.js`, `frontend/postcss.config.js`
- Modify: `frontend/src/index.css`

**Steps:**
1. Install `tailwindcss@3`, `postcss`, `autoprefixer`, and `lucide-react`.
2. Configure `tailwind.config.js` with custom Warm Heritage tokens:
   - `terracotta`: `#E05D38`, `terracotta-dark`: `#C84B27`
   - `amber`: `#F59E0B`, `amber-light`: `#FEF3C7`
   - `teal`: `#0D9488`, `teal-light`: `#CCFBF1`
   - `surface`: base `#FDFBF7`, card `#FFFFFF`, muted `#F8F6F0`, border `#EADBCC`
3. Update `index.css` with `@tailwind base; @tailwind components; @tailwind utilities;` and custom scrollbars.
4. Verify with a quick test component build.

**Review Checkpoint:** `npm run build` succeeds and Tailwind classes compile properly.

---

## Task 2: Rebuild API Client Layer & Authentication Services

**Files:**
- Create: `frontend/src/services/auth.js`
- Modify: `frontend/src/services/api.js`
- Create: `frontend/src/services/workspaces.js`
- Create: `frontend/src/services/chat.js`
- Create: `frontend/src/services/planner.js`
- Modify: `frontend/src/services/api.test.js`

**Steps:**
1. Write TDD tests in `api.test.js` verifying token attachment in `Authorization: Bearer <token>` header, response unwrap, and error extraction.
2. Implement `services/auth.js` managing `localStorage` token, current user label, and presets:
   - Alice: `token_alice` (`user_alice`)
   - Bob: `token_bob` (`user_bob`)
3. Implement `services/workspaces.js`: `listWorkspaces()`, `createWorkspace({title, destination_scope})`, `getWorkspace(id)`, `deleteWorkspace(id)`.
4. Implement `services/chat.js`: `sendChatMessage({message, conversation_id})`, `listMessages(conversation_id)`.
5. Implement `services/planner.js`: `getItineraries(workspace_id)`, `getItinerary(workspace_id, version_id)`, `acceptItinerary(workspace_id, version_id)`, `listDecisions(workspace_id)`.
6. Run `npm run test` to verify all client service tests pass.

**Review Checkpoint:** All service unit tests pass with Vitest.

---

## Task 3: Build Hybrid Login Modal Component

**Files:**
- Create: `frontend/src/components/auth/LoginModal.jsx`

**Steps:**
1. Implement modal with warm illustration/icon header, input field for custom bearer token, and 2 preset buttons ("Đăng nhập với Alice", "Đăng nhập với Bob").
2. Validate non-empty token on submit.
3. Save token via `auth.js` and notify parent `App.jsx` to load user workspaces.
4. Add clear error messaging when token format is rejected or server returns 401.

**Review Checkpoint:** Login component mounts and triggers authentication callback properly.

---

## Task 4: Build Core Layout & Sidebar

**Files:**
- Create: `frontend/src/components/layout/Header.jsx`
- Create: `frontend/src/components/layout/Sidebar.jsx`

**Steps:**
1. Implement `Sidebar.jsx`:
   - App logo with "Travel Agent AI" and Vietnam flag badge.
   - "+ Chuyến đi mới" button.
   - List of workspaces with active indicator, delete button, and destination scope.
   - Bottom profile footer showing logged-in user badge and "Đăng xuất" button.
   - Collapsible on mobile.
2. Implement `Header.jsx`:
   - Mobile hamburger menu toggle.
   - Mobile Tab Switcher: `[💬 Trò chuyện AI]` ⟷ `[📅 Lịch trình & Quyết định]`.
   - Active workspace title and status tag (`Planning`, `Active`...).

**Review Checkpoint:** Sidebar renders workspace list correctly and handles workspace selection.

---

## Task 5: Build Welcome Screen & 1-Click Onboarding

**Files:**
- Create: `frontend/src/components/welcome/WelcomeView.jsx`

**Steps:**
1. Design welcoming hero section: *"Chào mừng bạn đến với Trợ lý Du lịch Việt Nam!"*.
2. Render 3 curated 1-click starter cards with rich imagery tags and metadata:
   - *Hà Giang 3N2Đ: Mùa hoa tam giác mạch & đèo Mã Pí Lèng*
   - *Đà Nẵng - Hội An 4N3Đ: Food tour ẩm thực phố cổ & biển Mỹ Khê*
   - *Phú Quốc 3N2Đ: Nghỉ dưỡng hoàng hôn bãi Sao & lặn ngắm san hô*
3. When clicked, trigger `onSelectTemplate(template)`: creates workspace, creates initial conversation, and sends first planning prompt.

**Review Checkpoint:** Clicking a starter card initiates workspace creation seamlessly.

---

## Task 6: Build Chat Panel with Action Cards & Citations Drawer

**Files:**
- Create: `frontend/src/components/chat/ChatPanel.jsx`
- Create: `frontend/src/components/chat/ChatMessage.jsx`
- Create: `frontend/src/components/chat/ChatInput.jsx`
- Create: `frontend/src/components/chat/CitationDrawer.jsx`

**Steps:**
1. Implement `ChatMessage.jsx`:
   - Clean markdown rendering via `react-markdown` and `remark-gfm`.
   - Distinct styling for user message vs assistant message.
   - Action Card rendering when message contains itinerary proposals or decisions (e.g. badge *"Đã cập nhật Lịch trình v2"* with *"Xem lịch trình"* button).
   - Clickable citation tags: `[📚 Nguồn {i}: {title}]`.
2. Implement `CitationDrawer.jsx`:
   - Slide-over panel from right showing citation title, chunk text snippet, and external link to `vietnam.travel`.
3. Implement `ChatInput.jsx`:
   - Textarea with auto-height adjustment, `Enter` to submit (and `Shift+Enter` for newline), loading spinner, send button.
4. Implement `ChatPanel.jsx`:
   - Scrollable messages container with smooth auto-scroll to bottom on new message.

**Review Checkpoint:** Chat panel renders messages, displays citations, and opens evidence drawer on click.

---

## Task 7: Build Interactive Itinerary Planner Panel

**Files:**
- Create: `frontend/src/components/planner/PlannerPanel.jsx`
- Create: `frontend/src/components/planner/ItineraryTimeline.jsx`
- Create: `frontend/src/components/planner/ItineraryItemCard.jsx`

**Steps:**
1. Implement `ItineraryItemCard.jsx`:
   - Icon per item type (`meal` -> Utensils, `lodging` -> Hotel, `transport` -> Compass/Car, `activity` -> Camera/MapPin).
   - Time tags (`start_time` - `end_time`), title, location, notes.
2. Implement `ItineraryTimeline.jsx`:
   - Group itinerary items by `day_index` (Ngày 1, Ngày 2...).
   - Clean vertical timeline connecting line.
3. Implement `PlannerPanel.jsx`:
   - Header with Version Switcher dropdown (`Phiên bản v1`, `v2`...).
   - Status badge (`draft`, `proposed`, `accepted` in Teal/Amber).
   - Action button *"Phê duyệt lịch trình này"* calling `/accept` API.
   - List of confirmed `TripDecisions` (e.g. hotel chosen, dietary constraints).

**Review Checkpoint:** Planner panel displays day-by-day items, switches versions, and calls `/accept` successfully.

---

## Task 8: Root Integration & Verification

**Files:**
- Modify: `frontend/src/App.jsx`
- Create: `frontend/tests/components.test.jsx`

**Steps:**
1. Integrate all modules into `App.jsx`:
   - Check auth token on mount -> if absent, render `LoginModal`.
   - If authenticated, fetch workspaces. If empty, render `WelcomeView`.
   - If workspace active, render Dual Pane: `ChatPanel` (left) and `PlannerPanel` (right).
   - On mobile screen (< 1024px), toggle panels via Header tabs.
   - Chat message sending triggers planner reload.
2. Write unit tests in `frontend/tests/components.test.jsx` testing Login, Sidebar, and Timeline rendering.
3. Execute fresh verification:
   - `cd frontend && npm run lint`
   - `cd frontend && npm run test`
   - `cd frontend && npm run build`
4. Document verification evidence in walkthrough.

**Review Checkpoint:** All tests pass, build succeeds, and app runs cleanly in dev mode.

---

## Implementation Plan Approval Record

| Role | Status | Date |
| --- | --- | --- |
| Author (Agent) | Prepared | 2026-09-06 |
| Repository Owner | **Approved (Version 0.1)** | 2026-09-06 |
