---
name: Headless phone viewport checks
description: How to avoid false phone-width results when using the Replit Chromium binary.
---

The Replit Chromium binary can keep a roughly 500px minimum CSS layout viewport when launched with only `--window-size`, even when the output screenshot is physically 320px wide. The result looks like a phone capture but is actually a cropped wider layout.

**Why:** Responsive checks initially appeared to pass at phone sizes while Chromium reported a wider `innerWidth`; true device emulation exposed different wrapping and overflow behavior.

**How to apply:** For sub-500px responsive verification, use the Chrome DevTools Protocol `Emulation.setDeviceMetricsOverride` and assert `window.innerWidth` before evaluating layout. Treat `--window-size` alone as insufficient.