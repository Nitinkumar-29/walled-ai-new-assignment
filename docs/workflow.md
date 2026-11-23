# Walled AI workflow

## Overview

Walled AI is a standalone Windows desktop application. It launches a dedicated Chrome profile and
uses Chrome's local DevTools Protocol (CDP) to guard ChatGPT and Perplexity pages in that profile.
It does not install or rely on a browser extension, plugin, or add-on.

```text
User
  │
  ├─ Start Walled AI ──► Desktop controller ──► Dedicated Chrome profile
  │                                              (CDP bound to 127.0.0.1)
  │
  ├─ Open ChatGPT / Perplexity ──► Site tab
  │                                │
  │                                ├─ Prompt with marker ─┐
  │                                └─ File upload ────────┤
  │                                                       ▼
  │                                              Local scanner
  │                                          text / PDF / OCR image
  │                                                       │
  │                                  no match ────────────┤──► Continue
  │                                  match ──► Desktop decision dialog
  │                                             ├─ Continue ─► Site receives content
  │                                             └─ Cancel ───► Content held back
  └─ Close Walled AI ─────────────────────────────► Dedicated Chrome closes
```

## Start-up and browser setup

1. The user starts Walled AI and selects **Start protected Chrome**.
2. The app launches Chrome with a persistent profile at
   `%LOCALAPPDATA%\WalledAI\ChromeProfile`.
3. Chrome's DevTools endpoint is bound to the loopback interface. The app monitors page targets and
   attaches only to HTTPS pages on `chatgpt.com`, `perplexity.ai`, and `www.perplexity.ai`.
4. The user opens a supported site from the desktop app. On first use, the user signs in to the site
   in this dedicated profile.
5. The app installs its in-page guard through CDP. Tabs in regular Chrome profiles are not monitored.
6. The guard applies blue text styling to ChatGPT assistant messages and Perplexity answer content.

## Prompt submission

1. The page guard watches Enter and recognized Send/Submit buttons.
2. Prompts without `WALLED_SENSITIVE` are left to the site without opening a decision dialog.
3. When the marker is present (case-insensitive), the guard prevents the original submit action and
   sends the prompt to the local scanner over the CDP connection.
4. The desktop app scans the text and displays a dialog with a short matching excerpt.
5. **Continue** resumes submission. **Cancel**, closing the dialog, or a scanner/connection timeout
   keeps the prompt from being submitted.
6. If the prompt changes while the decision is pending, the changed prompt is checked again before
   the app resumes submission.

## File inspection

1. The page guard reads a selected, dropped, or pasted file locally in the browser page and passes
   its name, MIME type, and base64 content to the desktop app. Files larger than 8 MiB are rejected
   before transfer.
2. The local scanner supports UTF-8 text files, PDFs, and common raster images. Unknown types,
   unreadable files, files outside limits, and inspection errors are blocked.
3. PDFs are checked for embedded text. Image files and image-only PDF pages are inspected with OCR.
   Tesseract must be installed and available on `PATH`.
4. Files without the marker continue without a prompt. A matching file opens the desktop decision
   dialog. **Cancel** or an inspection error blocks the upload; **Continue** attempts to resume it.

## Shutdown and errors

- Closing Walled AI closes the dedicated Chrome session. The dedicated profile is retained for
  subsequent sign-ins.
- The app does not monitor pages in the user's other Chrome profiles or other browsers.
- If the app does not answer an inspection request within 60 seconds, the page guard blocks that
  action.
- Site DOM changes can invalidate the guarded selectors. A change to a submit control can cause an
  action not to be intercepted, so the app should not be treated as a general-purpose DLP guarantee.
- Resuming file drag/drop and paste uses synthetic browser events and can be affected by site
  behavior.

## Data handling

- Scanning and decision dialogs run locally.
- Walled AI does not send inspection data to its own service or save inspection copies.
- If the user chooses **Continue**, the target site receives the prompt or file as usual.
- The site and browser apply their own account, upload, and cache behavior.
