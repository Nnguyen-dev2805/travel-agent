---
name: ux-ui-agent-skills
description: Senior UI/UX Design System & Architectural Standards for crafting premium, state-of-the-art web interfaces with cohesive design tokens, rich aesthetics, glassmorphism, and responsive micro-interactions.
---

# Senior UI/UX Architecture & Design System Skill

Skill này hướng dẫn AI Coding Agent thực thi các nguyên tắc thiết kế giao diện (UI/UX) đỉnh cao chuẩn Senior Designer, đảm bảo mọi giao diện Web App/React UI được xây dựng có tính thẩm mỹ vượt trội, nhất quán và hiện đại.

---

## 🎨 1. CORE DESIGN TOKENS (HỆ THỐNG MÀU SẮC & PHỐI MÀU)

### A. Dark Mode Palette (Mã Màu Chuẩn Cẩm Nang Du Lịch)
- **Background Primary**: `#171717` (Deep Obsidian Dark)
- **Background Secondary / Sidebar**: `#212121` (Charcoal Surface)
- **Container / Card Background**: `#2f2f2f` (Elevated Panel)
- **Border Glass & Dividers**: `#383838` (Subtle Glass Outline)
- **Primary Accent / Brand**: `#10a37f` (Emerald Teal - Năng động, du lịch)
- **Primary Hover**: `#1a7f64` (Dark Emerald)
- **Text Primary**: `#ececec` (Crisp Soft White)
- **Text Secondary / Muted**: `#9b9b9b` (Slate Gray)

### B. Typography Hierarchy (Phân cất Chữ)
- **Font Family**: Google Fonts `Inter`, `Plus Jakarta Sans`, hoặc `Outfit` (`sans-serif`).
- **Heading 1 (H1)**: `text-2xl md:text-3xl font-bold tracking-tight text-white`
- **Heading 2 (H2)**: `text-xl md:text-2xl font-semibold tracking-tight text-gray-100`
- **Body Regular**: `text-sm md:text-base leading-relaxed text-gray-200`
- **Caption / Meta**: `text-xs text-gray-400 font-medium`

---

## 💎 2. PREMIUM AESTHETIC & MICRO-INTERACTIONS

### A. Glassmorphism & Backdrop Blur
- Áp dụng `backdrop-blur-md bg-[#212121]/80 border border-[#383838]` cho Navigation Header, Sticky Controls và Floating Bar.

### B. Micro-Animations & Hover States
- Tất cả các Button, Link, Card tương tác **BẮT BỘC** phải có cờ `transition-all duration-200 ease-in-out`.
- Khi Hover: `hover:bg-[#383838] hover:scale-[1.02] active:scale-[0.98]`.
- Nút Action chính: `shadow-md hover:shadow-emerald-900/30`.

### C. Rich Citations & Source Badges
- Thẻ Trích dẫn nguồn (Citations) được tạo dạng Badge tương tác:
  - Background: `#2f2f2f`
  - Border: `border border-[#424242]`
  - Text & Icon: `#10a37f` (Emerald)
  - Hover: `hover:bg-[#383838] hover:border-[#10a37f]`

---

## 📱 3. COMPONENT ARCHITECTURE & RESPONSIVE LAYOUTS

1. **Sidebar Navigation**:
   - Mobile: Drawer trượt `fixed inset-y-0 left-0 z-50 transform transition-transform duration-300`.
   - Desktop: Fixed navigation width `w-[260px] shrink-0 border-r border-[#383838]`.

2. **Chat Bubble Components**:
   - User Message: Background trong suốt hoặc pill mờ `bg-[#2f2f2f] rounded-2xl rounded-tr-none px-4 py-3`.
   - Assistant Message: Background phân tách rõ ràng `bg-[#212121] rounded-2xl rounded-tl-none px-5 py-4 border border-[#383838]`.

3. **Input Prompt Bar**:
   - Bọc trong container mờ nổi `max-w-3xl mx-auto bg-[#2f2f2f] border border-[#424242] focus-within:border-[#10a37f] rounded-2xl p-3 shadow-lg transition-all`.

---

## ♿ 4. ACCESSIBILITY (WCAG 2.2) & BEST PRACTICES
- **Contrast Ratio**: Đảm bảo độ tương phản giữa Text và Background luôn >= 4.5:1.
- **Unique Identifiers**: Mọi nút bấm và trường nhập liệu interactive phải có `id` hoặc `aria-label` minh bạch.
- **Interactive Feedback**: Mọi thao tác chờ (Loading/Searching) phải có hiệu ứng Skeleton hoặc Spinner mượt mà.
