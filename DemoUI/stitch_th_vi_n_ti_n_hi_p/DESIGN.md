---
name: VNDict Reader
colors:
  surface: '#0b1326'
  surface-dim: '#0b1326'
  surface-bright: '#31394d'
  surface-container-lowest: '#060e20'
  surface-container-low: '#131b2e'
  surface-container: '#171f33'
  surface-container-high: '#222a3d'
  surface-container-highest: '#2d3449'
  on-surface: '#dae2fd'
  on-surface-variant: '#bec8d2'
  inverse-surface: '#dae2fd'
  inverse-on-surface: '#283044'
  outline: '#88929b'
  outline-variant: '#3e4850'
  surface-tint: '#89ceff'
  primary: '#89ceff'
  on-primary: '#00344d'
  primary-container: '#0ea5e9'
  on-primary-container: '#003751'
  inverse-primary: '#006591'
  secondary: '#4fdbc8'
  on-secondary: '#003731'
  secondary-container: '#04b4a2'
  on-secondary-container: '#003f38'
  tertiary: '#c0c1ff'
  on-tertiary: '#1000a9'
  tertiary-container: '#8d90ff'
  on-tertiary-container: '#1407ad'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#c9e6ff'
  primary-fixed-dim: '#89ceff'
  on-primary-fixed: '#001e2f'
  on-primary-fixed-variant: '#004c6e'
  secondary-fixed: '#71f8e4'
  secondary-fixed-dim: '#4fdbc8'
  on-secondary-fixed: '#00201c'
  on-secondary-fixed-variant: '#005048'
  tertiary-fixed: '#e1e0ff'
  tertiary-fixed-dim: '#c0c1ff'
  on-tertiary-fixed: '#07006c'
  on-tertiary-fixed-variant: '#2f2ebe'
  background: '#0b1326'
  on-background: '#dae2fd'
  surface-variant: '#2d3449'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  title-sm:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
  reading-body:
    fontFamily: Merriweather
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 32px
  reading-body-mobile:
    fontFamily: Merriweather
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 28px
  ui-label:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
  ui-caption:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 40px
  container-max: 1200px
  sidebar-width: 260px
---

## Brand & Style

The design system for this local productivity tool is built on a foundation of **Calm Professionalism**. It targets readers and researchers who require a focused, distraction-free environment for long-form content consumption. 

The aesthetic is a blend of **Corporate Modern** and **Minimalism**, prioritizing content legibility and systemic reliability. The interface uses deep, cool-toned backgrounds to reduce eye strain during extended reading sessions, while subtle borders and high-quality typography provide a sense of structure and precision. The emotional response should be one of "quiet capability"—a tool that works reliably in the background without overwhelming the user.

## Colors

The palette is anchored by a deep slate and charcoal foundation to create a premium, "night-mode" reading experience. 

- **Primary Accent:** Calm Blue (#0ea5e9) is used for primary actions, progress indicators, and active selection states.
- **Surface Tiers:** Use `#0f172a` for the main application background and `#1e293b` for elevated containers like cards, sidebars, and modals.
- **Borders:** `#334155` provides a low-contrast definition that maintains UI structure without visual noise.
- **Semantic Feedback:**
    - **Pending:** Neutral Slate (#64748b) for inactive or queued items.
    - **Processing:** Indigo (#6366f1) for active fetching or translation tasks.
    - **Success:** Emerald (#22c55e) for completed translations.
    - **Error:** Rose (#ef4444) for system alerts or failed tasks.

## Typography

This design system utilizes a dual-typeface strategy to balance functional utility with reading comfort.

- **UI Controls & Navigation:** **Inter** (Sans-serif) is used for all dashboard elements, buttons, sidebar links, and metadata. It provides a clean, systematic look that remains legible at small sizes.
- **Reading Content:** **Merriweather** (Serif) is reserved for novel titles, chapter content, and translation outputs. The increased line height (1.8x) and generous font size (18px) are optimized for "deep reading" to minimize cognitive load.
- **Vietnamese Language Support:** Ensure all weights are properly loaded to handle Vietnamese diacritics without "tofu" or baseline shifting.

## Layout & Spacing

The layout follows a **Fixed-Fluid Hybrid** model. The sidebar remains at a fixed width of 260px, while the main content area expands to a maximum width of 1200px to prevent excessively long line lengths in the reading view.

- **Grid:** A 12-column grid is used for the dashboard view.
- **Reading View:** Content should be centered with wide margins (at least 80px on desktop) to simulate a book-like experience.
- **Responsive Adaptations:**
    - **Desktop:** Sidebar visible, 24px margins.
    - **Tablet:** Sidebar collapses into a drawer, 16px margins.
    - **Mobile:** 12px margins, typography scales down (using `reading-body-mobile`), and cards stack vertically.

## Elevation & Depth

In this dark-themed environment, depth is communicated through **Tonal Layering** and subtle ambient shadows rather than heavy drop shadows.

- **Level 0 (Background):** `#0f172a` — The primary canvas.
- **Level 1 (Cards/Sidebar):** `#1e293b` — Raised surfaces. Use a 1px solid border of `#334155` for definition.
- **Level 2 (Popovers/Modals):** `#1e293b` with a soft, diffused shadow: `0 10px 15px -3px rgba(0, 0, 0, 0.4)`.
- **Active State Shadow:** Primary buttons and active cards may use a very subtle outer glow of the primary color (`#0ea5e9`) at 10% opacity to indicate focus.

## Shapes

The shape language is modern and approachable, utilizing a consistent **Rounded** (8px to 16px) corner radius.

- **Standard UI (Buttons/Inputs):** 8px (`rounded-md`).
- **Containers (Cards/Modals):** 12px to 16px (`rounded-lg` or `rounded-xl`).
- **Status Badges:** Fully rounded (pill-shaped) to distinguish them from interactive buttons.

## Components

### Buttons
- **Primary:** Solid `#0ea5e9` with white text. High contrast, 8px radius.
- **Secondary:** Bordered (`#334155`) with transparent background.
- **Ghost:** No background, `#64748b` text; turns to primary color on hover.

### Status Badges
Used for translation states. These should have a subtle background (10% opacity of the status color) and a solid text label for maximum readability.
- *Example:* **Đang dịch** (Translating) uses Indigo background at 10% and solid Indigo text.

### Sidebar Navigation
- **Active State:** A vertical 4px bar on the left edge in Primary Blue, with a subtle background highlight (`#0ea5e9` at 10% opacity).
- **Icons:** Use Lucide-style icons with a consistent 2px stroke weight.

### Cards (Novel/Document)
Cards use the `#1e293b` background with a 12px radius. Information is stacked: cover image (if available), title (Inter, Bold), and metadata (Inter, Caption).

### Reading Interface
The central reading pane must be devoid of UI clutter. Controls for font-size and theme (light/dark/sepia) should be tucked into a floating "Reader Settings" menu that appears only on interaction.

### Empty States
Use a centered layout with a de-saturated icon (`#334155`), a clear headline in Vietnamese (e.g., "Chưa có tài liệu nào"), and a primary action button to "Thêm mới".