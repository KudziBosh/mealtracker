---
name: The Design System
colors:
  surface: '#fbf9f4'
  surface-dim: '#dbdad5'
  surface-bright: '#fbf9f4'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f5f3ee'
  surface-container: '#f0eee9'
  surface-container-high: '#eae8e3'
  surface-container-highest: '#e4e2dd'
  on-surface: '#1b1c19'
  on-surface-variant: '#424843'
  inverse-surface: '#30312e'
  inverse-on-surface: '#f2f1ec'
  outline: '#727972'
  outline-variant: '#c2c8c0'
  surface-tint: '#466550'
  primary: '#163422'
  on-primary: '#ffffff'
  primary-container: '#2d4b37'
  on-primary-container: '#99baa1'
  inverse-primary: '#adcfb4'
  secondary: '#97472a'
  on-secondary: '#ffffff'
  secondary-container: '#ff9875'
  on-secondary-container: '#772f14'
  tertiary: '#2b3112'
  on-tertiary: '#ffffff'
  tertiary-container: '#424727'
  on-tertiary-container: '#afb58c'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#c8ebd0'
  primary-fixed-dim: '#adcfb4'
  on-primary-fixed: '#022110'
  on-primary-fixed-variant: '#2f4d39'
  secondary-fixed: '#ffdbd0'
  secondary-fixed-dim: '#ffb59c'
  on-secondary-fixed: '#390c00'
  on-secondary-fixed-variant: '#793015'
  tertiary-fixed: '#e0e6ba'
  tertiary-fixed-dim: '#c4ca9f'
  on-tertiary-fixed: '#191e03'
  on-tertiary-fixed-variant: '#444a29'
  background: '#fbf9f4'
  on-background: '#1b1c19'
  surface-variant: '#e4e2dd'
typography:
  display:
    fontFamily: Newsreader
    fontSize: 42px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Newsreader
    fontSize: 32px
    fontWeight: '500'
    lineHeight: '1.3'
  headline-md:
    fontFamily: Newsreader
    fontSize: 24px
    fontWeight: '500'
    lineHeight: '1.4'
  body-lg:
    fontFamily: Manrope
    fontSize: 18px
    fontWeight: '400'
    lineHeight: '1.6'
  body-md:
    fontFamily: Manrope
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
  label-md:
    fontFamily: Manrope
    fontSize: 14px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: 0.05em
  headline-lg-mobile:
    fontFamily: Newsreader
    fontSize: 28px
    fontWeight: '500'
    lineHeight: '1.3'
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 8px
  container-max: 1024px
  gutter: 24px
  margin-mobile: 16px
  stack-sm: 12px
  stack-md: 24px
  stack-lg: 48px
---

## Brand & Style

The brand personality of this design system is rooted in high-utility minimalism. It rejects the over-saturated gamification of modern health apps in favor of a "quiet tool" philosophy. The emotional response should be one of competence and tranquility—providing the user with a digital space that feels as organized and grounded as a well-kept physical kitchen or a structured journal.

The style is a blend of **Modern Minimalism** and **Tactile Practicality**. It prioritizes structural clarity and functional density, reminiscent of high-end editorial layouts or traditional apothecary labeling. The aesthetic is specifically tailored for a lightweight Django/HTMX implementation, favoring standard browser behaviors and solid CSS fundamentals over complex JavaScript animations.

## Colors

The color palette is inspired by natural materials and organic health. It utilizes a warm, off-white neutral base to reduce eye strain and provide a more "analog" feel than pure white.

- **Primary (Earthy Green):** Used for primary actions, navigation states, and representing growth/health. High contrast against the neutral background is maintained for legibility.
- **Secondary (Soft Terracotta):** Used for highlighting habits, protein tracking, or cautionary alerts that require attention without being alarming.
- **Tertiary (Sage):** Used for secondary metrics and non-urgent data visualization.
- **Neutrals:** A range of warm grays and creams create soft hierarchies without the harshness of monochrome blacks.

Accessibility is paramount; all text pairings must meet WCAG AA standards, particularly the primary green on the cream background.

## Typography

This design system employs a sophisticated pairing of a traditional serif and a modern geometric sans-serif.

- **Newsreader** is used for headlines and editorial-style data summaries. Its literary character reinforces the disciplined, journal-like nature of the application.
- **Manrope** is used for all functional UI elements, body text, and data points. Its balanced proportions ensure high legibility in dense meal lists and habit grids.

Rhythm is maintained through generous line-heights, ensuring that even data-heavy pages feel airy and readable. Use the uppercase label style for metadata and category headers to provide clear visual breaks.

## Layout & Spacing

The layout philosophy follows a **Fixed Grid** model for desktop to maintain the "lightweight web app" feel, centering content in a readable 1024px container. 

- **Grid:** A 12-column grid is used for desktop, collapsing to a single column on mobile.
- **Vertical Rhythm:** Elements are stacked using a strict 8px base unit. Section headers should have a 48px top margin to separate distinct habit or meal categories.
- **HTMX Loading States:** Since the app is built on HTMX, layout shifts should be minimized by defining explicit heights for card containers and using subtle skeleton states that match the rounded-corner geometry.

## Elevation & Depth

Hierarchy is established through **Tonal Layers** and **Ambient Shadows**. This design system avoids high-elevation shadows to keep the interface feeling grounded and practical.

- **Level 0 (Background):** The warm neutral base (#F9F7F2).
- **Level 1 (Cards):** Pure white surfaces with a very soft, diffused shadow (0px 4px 20px rgba(0, 0, 0, 0.04)). This provides a subtle "lift" from the background.
- **Outlines:** A thin 1px border (#E2E2D9) is used on all cards to ensure structural definition even on low-quality displays.
- **Interactive Depth:** Buttons and interactive cards should transition to a slightly deeper shadow on hover, but never feel "bouncy" or overly animated.

## Shapes

The shape language is consistently **Rounded**. This softens the "disciplined" nature of the app, making it feel approachable rather than clinical.

- **Cards & Containers:** Use `rounded-lg` (1rem/16px) for main content areas and meal logs.
- **Buttons & Inputs:** Use `rounded-md` (0.5rem/8px) for primary actions to maintain a sturdy, clickable appearance.
- **Small Elements:** Chips and progress indicators utilize a full pill shape for clear distinction from structural containers.

## Components

- **Buttons:** Primary buttons use a solid Earthy Green background with white text. Secondary buttons use the Off-white background with a Green border. Large touch targets are mandatory for mobile habit-checking.
- **Meal Cards:** Soft-shadowed white cards with a Newsreader header. Meal items within the card are displayed in a clean, vertical list with subtle dividers.
- **Habit Grids:** Small, rounded-sm squares that fill with Sage Green (for tertiary/standard) or Terracotta (for priority) when completed. Avoid flashy animations; use a simple CSS color transition.
- **Input Fields:** Warm neutral backgrounds with 1px borders. Focus states should use a 2px Primary Green border with no glow effect.
- **Progress Bars:** Thin, horizontal tracks using the Tertiary Sage Green for the fill and a light neutral for the track.
- **Django Flash Messages:** Displayed as top-aligned, non-intrusive bars with the primary Green for success and Terracotta for errors, adhering to the standard HTMX swap patterns.