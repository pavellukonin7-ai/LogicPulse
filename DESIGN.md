---
version: alpha
name: "LogicPulse Living Pulse"
description: "A dark, precise digital-systems studio identity with a living particle signature and restrained product forms."
colors:
  background: "#090e11"
  panel: "#11181c"
  text: "#f2f4f2"
  muted: "#b0b8b9"
  primary: "#91ead0"
  accent: "#91ead0"
  line: "#343e42"
  light-surface: "#f4f4f0"
  light-text: "#151b1e"
  error: "#ffbea6"
typography:
  display:
    fontFamily: "Onest, Arial, Helvetica, sans-serif"
  chinese:
    fontFamily: "LP Chinese, Onest, PingFang SC, Microsoft YaHei, sans-serif"
rounded:
  DEFAULT: "2px"
  focus: "3px"
spacing:
  page-width: "90%"
  page-max: "1320px"
  section-desktop: "68px"
  section-mobile: "48px"
components:
  language-switch:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.text}"
    rounded: "{rounded.focus}"
    padding: "3px"
    height: "44px"
  button:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.background}"
    rounded: "{rounded.DEFAULT}"
    height: "51px"
  field:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.text}"
    rounded: "{rounded.DEFAULT}"
    height: "47px"
---

# LogicPulse Living Pulse Design System

## Overview

### Creative North Star

The interface resembles a controlled digital signal in a dark laboratory: the particle ring is the one expressive gesture; typography, rules, and forms remain quiet and exact.

### Product context and register

- **Audience and primary job:** Russian, English, and Chinese-speaking business owners evaluating LogicPulse and submitting a project enquiry.
- **Target markets and evidence:** Global client-facing brand surface. Locale selection expresses language preference only and does not infer legal jurisdiction, currency, or market terms.
- **Locales and language policy:** `ru`, `en-GB`, and Simplified Chinese `zh-CN`. Russian is the source language. The five maintained service templates have reviewed in-project English and Chinese equivalents. Administrator-edited text without an exact translation remains in Russian and is clearly marked; it is never silently replaced by a stale template.
- **Usage scene:** Public website on desktop and mobile, with infrequent but consequential form completion.
- **Register:** Hybrid. The homepage is expressive brand presentation; account, privacy, and form states use familiar product patterns.
- **Memorable signature:** The mint-to-violet particle field responds reversibly to page scroll.
- **Restraint:** Language, authentication, consent, errors, pricing, and submission states favour clarity over animation.
- **Anti-references:** No generic gradient SaaS cards, flag-based language picker, stock illustrations, glossy glass controls, or culturally stereotyped Chinese decoration.
- **Token ownership/runtime mapping:** Existing runtime CSS is canonical. This file mirrors accepted values from `frontend/living-pulse.css`, `frontend/language.css`, and shared `frontend/styles.css`; it does not generate them.

## Colors

The public shell uses `background`, `panel`, `text`, `muted`, `accent`, and `line`. The service catalogue uses `light-surface` and `light-text` for a deliberate editorial pause. Mint is reserved for focus, selected language, and primary emphasis. `error` is accompanied by text and `aria-invalid`, never used alone.

## Typography

Onest is the display and body family with weights 300–600 stored locally. Simplified Chinese uses the locally subsetted LP Chinese font before platform fallbacks to avoid missing glyphs and layout flash. Chinese headings remove negative Latin letter spacing and use a more generous line height. Prices use locale-aware number grouping but remain denominated in RUB until the business defines regional pricing.

## Layout

Public content uses a 90% container capped at 1320px. Desktop sections follow the established 68–94px vertical rhythm; mobile sections use 40–48px. The language control belongs in the header and reflows before navigation on narrow screens. Switching locale must preserve form values, selected service, open disclosures, authentication state, and scroll-linked motion.

## Elevation & Depth

Hierarchy comes from tonal surfaces, hairline borders, and the particle field. Static content has no card shadows. Focus and invalid states use borders and outlines without moving layout.

## Shapes

Controls are nearly square with 2px corners. The language switch is a compact segmented control with a 44px touch target per option. Rounded pills and ornamental badges are not part of this identity.

## Components

### Foundational visual states

Interactive controls define default, hover, visible keyboard focus, selected, disabled, busy, success, and error states. Text status accompanies colour. Reduced-motion preferences disable decorative transforms while preserving content.

### Buttons and actions

Primary actions use a light surface on the dark theme. Secondary actions use a restrained border. Busy labels remain within the existing button geometry and duplicate submission is blocked.

### Navigation and data display

The RU / EN / 中文 control uses real buttons with an accessible group label and `aria-pressed`. The selected locale persists under `lp_language`; `?lang=` may be used for a shareable locale link. Flags are intentionally avoided because language is not nationality.

### Forms and overlays

Project and urgency selectors remain native: platform-owned popup geometry is accepted, while labels and options are localized. Forms use app-owned inline validation in the active language, preserve entered values, focus the first error, and retain idempotency keys across localized retries. Password input is masked by default and has a localized show/hide control.

### Iconography

Arrows and plus signs are functional, optically simple glyphs. Icon-only actions need localized accessible names; essential actions retain text labels.

### Motion

The particle ring and footer field follow scroll position and reverse exactly when scrolling upward. Motion is requestAnimationFrame-bound, interruptible, milder on mobile, and disabled by `prefers-reduced-motion`.

### Content and data visualization

Copy is direct and business-focused. Owned interface text, validation, status, accessibility labels, number grouping, and standard services follow the active locale. Unknown administrator-authored Russian content is preserved with a language note instead of being mistranslated.

## Do's and Don'ts

- **Do:** Keep the particle field as the single expressive signature.
- **Do:** Preserve values and workflow state when users change language.
- **Do:** Treat Chinese as a complete script and typography requirement, not a decorative label.
- **Don't:** Infer country, tax, legal terms, or currency from the selected language.
- **Don't:** hide unapproved pricing or content fallback behind a translation.
