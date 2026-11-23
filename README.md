# Walled AI

Walled AI is a standalone Windows desktop application. It launches a dedicated Chrome profile and
guards ChatGPT and Perplexity tabs through Chrome's local DevTools Protocol. It does **not** install,
require, or use a browser extension, plugin, or add-on.

The app checks for `WALLED_SENSITIVE` (case-insensitive) in prompts and supported uploads. Matching
content is held for an explicit Continue/Cancel decision. Canceling, unsupported files, or inspection
errors block the action. Scanning and dialogs run locally; Walled AI does not send content to its own
service or save inspection copies. If you choose Continue, the target website receives the prompt or
file as usual.

## Run from source

Requirements: Windows 10/11, Python 3.10+, Google Chrome, and (for image or scanned-PDF OCR)
Tesseract OCR available on `PATH`.

```powershell
python -m venv .desktop-venv
.\.desktop-venv\Scripts\python.exe -m pip install -r requirements.txt
.\.desktop-venv\Scripts\python.exe -m desktop_app.main
```

In the Walled AI window, click **Start protected Chrome**, then use **Open ChatGPT** or
**Open Perplexity**. Sign into each site in the new, dedicated Chrome profile the first time.
Subsequent runs reuse that profile. Only tabs in this app-launched profile are monitored; tabs in
your regular Chrome windows are not.

Keep Walled AI running while using those tabs. Closing Walled AI closes the dedicated browser
session. The DevTools endpoint is bound to `127.0.0.1` and uses a separate Chrome profile.

## Architecture

The Tkinter desktop app starts and controls a dedicated Chrome profile over the local Chrome DevTools
Protocol. An in-page guard intercepts supported prompt submissions and file selections before the
site receives them, then sends their contents to the local Python scanner. The scanner checks text
and PDF content directly and uses Tesseract for images and scanned PDF pages. Matching content is
held for a native desktop Continue/Cancel dialog. The guard also applies blue text styling to
assistant responses on ChatGPT and answer content on Perplexity. No browser extension is used.

## Build a standalone executable

```powershell
.\scripts\build-windows.ps1
```

The packaged app is `dist\WalledAI.exe`. It contains the Python runtime and scanner libraries.
Install Tesseract separately for image and scanned-PDF OCR. The app creates its persistent browser
profile under `%LOCALAPPDATA%\WalledAI\ChromeProfile`.

## Inspected content

- Prompts submitted with Enter or recognized Send/Submit buttons on `chatgpt.com` and
  `www.perplexity.ai`.
- Text files (`.txt`, `.csv`, `.md`, `.json`, `.log`), PDFs, and common raster images selected from
  a file picker or dropped onto the page.
- File limit: 8 MiB. PDFs over 100 pages and images over 40 megapixels are blocked.
- PDFs are parsed with pypdf. Scanned PDFs and images use Tesseract OCR.

The sites' compose controls can change. If a selector changes, the guard may not detect a submission;
verify behavior against current site versions before using this as a compliance control.

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Automated tests cover site filtering, prompt/file confirmation decisions, file limits, text and PDF
scanning, and image/scanned-PDF OCR. Prompt and upload interception plus response colors must still
be manually checked in the protected Chrome profile on both supported sites because their page
structures can change.

## Documentation

- [Workflow](docs/workflow.md): app, browser, scan, decision, and shutdown flows.
- [Use cases](docs/use-cases.md): actors, preconditions, normal and alternate flows, and limits.

## Limitations

- This app controls a dedicated Chrome profile; it does not monitor unrelated browser windows.
- The application relies on the sites' current DOM selectors. Site changes can require updates.
- Drag/drop resumption uses synthetic browser events and may be affected by site changes.
- OCR can miss content because of image quality, layout, language, or handwriting. This is a local
  marker check, not a general-purpose DLP or security guarantee.
