# Walled AI use cases

## Actors

| Actor | Responsibility |
|---|---|
| User | Starts the protected browser, uses the supported site, and decides whether matching content may proceed. |
| Walled AI desktop app | Starts Chrome, monitors supported pages in its dedicated profile, scans content locally, and presents decisions. |
| Supported site | Receives prompts and files only after the applicable guard check allows the action. |
| Local scanner | Detects `WALLED_SENSITIVE` in supported prompt and file content. |

## UC-01: Start the protected browser

**Goal:** Open a supported site in a browser session that Walled AI monitors.

**Preconditions:** Walled AI and Google Chrome are installed. For image and scanned-PDF OCR,
Tesseract is installed and available on `PATH`.

**Main flow:**

1. The user starts Walled AI.
2. The user selects **Start protected Chrome**.
3. Walled AI launches its dedicated Chrome profile and reports that it is ready.
4. The user selects **Open ChatGPT** or **Open Perplexity**.
5. The user signs in if needed and uses the site in this browser profile.

**Alternate flows:**

- Chrome is not found or fails to start: the app reports the error and does not claim that a page is
  protected.
- The user opens a supported site in ordinary Chrome: that page is outside Walled AI's monitoring
  scope.
- The user closes Walled AI: its dedicated Chrome session closes; the profile remains on disk.

## UC-02: Submit an ordinary prompt

**Goal:** Submit a prompt that does not contain the sensitive marker.

**Preconditions:** The user is on a supported page in the protected Chrome profile.

**Main flow:**

1. The user enters a prompt without `WALLED_SENSITIVE`.
2. The user presses Enter or clicks a recognized Send/Submit control.
3. Walled AI does not open a decision dialog.
4. The site receives the prompt.

## UC-03: Cancel a matching prompt

**Goal:** Prevent a prompt containing the marker from being submitted.

**Preconditions:** The user is on a supported page in the protected Chrome profile.

**Main flow:**

1. The user enters a prompt containing `WALLED_SENSITIVE`, in any letter case.
2. The user attempts to submit it.
3. Walled AI holds the submit action and scans the prompt locally.
4. The desktop dialog displays the prompt type and a short matching excerpt.
5. The user selects **Cancel** or closes the dialog.
6. The prompt is not submitted.

**Alternate flows:**

- The user changes the prompt while the dialog is pending: the changed content is checked again
  before a submission can resume.
- The app or CDP connection fails to respond: the pending action times out and is blocked.

## UC-04: Continue a matching prompt

**Goal:** Allow a matching prompt after an explicit user decision.

**Preconditions:** Same as UC-03.

**Main flow:**

1. The user enters and attempts to submit a prompt containing the marker.
2. Walled AI holds it, scans it, and displays the matching excerpt.
3. The user selects **Continue**.
4. Walled AI resumes the submission through the site's Send/Submit control.
5. The target site receives the prompt.

**Alternate flow:** If the site's control is no longer available or the prompt changed, Walled AI
rechecks where possible and reports a failure rather than silently treating a blocked action as sent.

## UC-05: Upload a supported file without a match

**Goal:** Inspect and upload a supported file that does not contain the marker.

**Preconditions:** The user is on a supported page in the protected Chrome profile. The file is no
larger than 8 MiB and is a supported text, PDF, or raster-image type.

**Main flow:**

1. The user selects, drops, or pastes the file.
2. Walled AI inspects it locally.
3. No marker is found.
4. The upload continues without a decision dialog.

## UC-06: Cancel a file containing the marker

**Goal:** Prevent a matching file from being uploaded.

**Preconditions:** Same as UC-05; the marker is detectable in the file's extracted or OCR text.

**Main flow:**

1. The user selects, drops, or pastes the file.
2. Walled AI holds the file action and scans the file locally.
3. The desktop dialog identifies the file and shows a short matching excerpt when available.
4. The user selects **Cancel** or closes the dialog.
5. The file is not passed to the site.

## UC-07: Continue a file containing the marker

**Goal:** Allow a matching file to be uploaded after explicit approval.

**Main flow:**

1. The user selects, drops, or pastes a file containing the marker.
2. Walled AI scans it and displays the decision dialog.
3. The user selects **Continue**.
4. Walled AI attempts to resume the file action.
5. The target site receives the file if it accepts the resumed browser event.

**Alternate flow:** A site may reject synthetic drag/drop or paste events. If it does, the user must
try the site's file picker and verify the site state before proceeding.

## UC-08: Block an uninspectable file or failed scan

**Goal:** Avoid sending files that Walled AI cannot inspect.

**Trigger:** The file is unsupported, exceeds the size/page/pixel limits, is unreadable, required OCR
software is unavailable, or inspection fails.

**Main flow:**

1. The user attempts a file action.
2. Walled AI detects that inspection cannot complete.
3. Walled AI blocks the file action and displays the reason when available.

## Supported file limits

| Type | Handling |
|---|---|
| `.txt`, `.csv`, `.md`, `.json`, `.log`, UTF-8 | Decode and search text for the marker. |
| PDF, up to 100 pages | Extract embedded text; OCR image-only pages. |
| PNG, JPEG, TIFF, BMP, WebP | OCR with Tesseract; maximum 40 megapixels. |
| Other types, unreadable content, over-limit files | Block because the content cannot be inspected. |

## Out of scope

- Monitoring regular Chrome profiles, other browsers, or pages outside the two supported services.
- General-purpose DLP, semantic sensitive-data detection, or a guarantee against site-selector drift.
- Detecting content that OCR fails to recognize.
