# django-http-inspector Design System

## Intent

A focused developer at a desk scans dense webhook traffic and needs one anomalous request to become obvious without visual noise. The interface is light, neutral, precise, and optimized for sustained inspection.

## Color

The strategy is restrained. Neutral surfaces carry the data; crimson is reserved for brand, selection, focus, and primary actions. Semantic colors always appear with text.

```css
--di-bg: oklch(1 0 0);
--di-surface: oklch(0.975 0.004 10);
--di-surface-strong: oklch(0.945 0.006 10);
--di-ink: oklch(0.19 0.015 10);
--di-muted: oklch(0.47 0.018 10);
--di-border: oklch(0.88 0.009 10);
--di-primary: oklch(0.52 0.20 10.4);
--di-accent: oklch(0.60 0.13 245);
--di-success: oklch(0.54 0.13 150);
--di-warning: oklch(0.68 0.14 75);
--di-danger: oklch(0.52 0.20 25);
```

## Typography

Use the system UI sans stack for controls and prose. Use the system monospace stack for URLs, headers, payloads, methods, status codes, sizes, and timings. The product uses a compact fixed type scale from 12px to 20px; no display typography.

## Layout

- 52px top bar.
- Desktop master-detail split: request stream is 340px; detail fills the remaining width.
- Dense 58px request rows with consistent alignment.
- At widths below 760px, selecting a request navigates to a full-width detail surface.
- Body viewers use scrollable preformatted blocks and never force the page wider.

## Components

- Buttons: 6px radius, 34px height, clear focus ring; primary uses white on crimson.
- Tabs: underline/current-ink treatment, no pills.
- Panels: dividers and surface contrast, not floating cards or broad shadows.
- Method/status labels: compact monospace text; color supplements rather than replaces the label.
- Notices: full-width inline rows with explicit text.

## Motion

Only state transitions use motion, 150–180ms ease-out. Respect `prefers-reduced-motion`; content is visible without animation.

## Reference Boundary

Borrow ngrok `:4040`'s request-stream/detail hierarchy and contextual replay workflow. Do not copy ngrok colors, logo, typography, or proprietary assets.
