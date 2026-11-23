(() => {
  if (window.__walledAiInstalled) return;
  window.__walledAiInstalled = true;

  const MARKER = "WALLED_SENSITIVE";
  const MAX_FILE_BYTES = 8 * 1024 * 1024;
  const RESPONSE_COLOR = "#2563EB";
  const EDITOR_SELECTOR = [
    '[data-testid="prompt-textarea"]',
    "textarea",
    '[contenteditable="true"]',
    '[role="textbox"]'
  ].join(",");
  const SEND_SELECTOR = [
    'button[data-testid="send-button"]',
    'button[aria-label="Submit"]',
    'button[aria-label="Send message"]',
    'button[aria-label="Send"]'
  ].join(",");
  const resolvers = new Map();
  const approvedFiles = new WeakSet();
  let nextRequestId = 0;

  function installResponseColor() {
    const styleId = "walled-ai-response-text-color";
    if (document.getElementById(styleId)) return;

    const selectors = location.hostname === "chatgpt.com"
      ? ['[data-message-author-role="assistant"]']
      : ["main .prose", 'main [data-testid="answer-content"]'];
    const style = document.createElement("style");
    style.id = styleId;
    style.textContent = selectors
      .map((selector) => `${selector}, ${selector} * { color: ${RESPONSE_COLOR} !important; }`)
      .join("\n");

    const attachStyle = () => {
      const parent = document.head || document.documentElement;
      if (!parent) {
        document.addEventListener("DOMContentLoaded", attachStyle, { once: true });
        return;
      }
      if (!document.getElementById(styleId)) parent.append(style);
    };
    attachStyle();
  }

  installResponseColor();

  function containsMarker(text) {
    return text.toUpperCase().includes(MARKER);
  }

  function editorText(editor) {
    return typeof editor.value === "string"
      ? editor.value
      : editor.innerText || editor.textContent || "";
  }

  function requestScan(data) {
    return new Promise((resolve) => {
      const requestId = `${Date.now()}-${++nextRequestId}`;
      const timeout = setTimeout(() => {
        resolvers.delete(requestId);
        resolve({ approved: false, error: "Walled AI did not respond within 60 seconds." });
      }, 60000);
      resolvers.set(requestId, (result) => {
        clearTimeout(timeout);
        resolve(result);
      });
      window.__walledAiBridge(JSON.stringify({ ...data, request_id: requestId }));
    });
  }

  window.__walledAiResolve = (requestId, result) => {
    const resolve = resolvers.get(requestId);
    if (!resolve) return;
    resolvers.delete(requestId);
    resolve(result);
  };

  function notify(message) {
    const host = document.createElement("div");
    host.setAttribute("role", "alert");
    host.style.cssText = "position:fixed;z-index:2147483647;top:12px;right:12px";
    const shadow = host.attachShadow({ mode: "closed" });
    const box = document.createElement("div");
    box.textContent = message;
    box.style.cssText = "max-width:380px;padding:12px 16px;border-radius:8px;background:#7f1d1d;color:white;font:14px/1.45 system-ui,sans-serif;box-shadow:0 4px 16px #0005";
    shadow.append(box);
    document.documentElement.append(host);
    setTimeout(() => host.remove(), 6000);
  }

  function hold(event) {
    event.preventDefault();
    event.stopImmediatePropagation();
  }

  async function checkPrompt(editor, text, retry) {
    const result = await requestScan({ action: "scan_text", text });
    if (!result?.approved) {
      if (result?.error) notify(`Walled AI blocked this submission: ${result.error}`);
      return;
    }

    const currentText = editorText(editor);
    if (currentText !== text && containsMarker(currentText)) {
      checkPrompt(editor, currentText, retry);
      return;
    }
    retry();
  }

  function sendButtonFor(editor) {
    return editor.closest("form")?.querySelector(SEND_SELECTOR)
      || document.querySelector(SEND_SELECTOR);
  }

  document.addEventListener("keydown", (event) => {
    if (!event.isTrusted || event.key !== "Enter" || event.shiftKey || event.isComposing) return;
    const editor = event.target instanceof Element ? event.target.closest(EDITOR_SELECTOR) : null;
    if (!editor) return;
    const text = editorText(editor);
    if (!containsMarker(text)) return;
    hold(event);
    checkPrompt(editor, text, () => {
      const button = sendButtonFor(editor);
      if (button && !button.disabled) button.click();
      else {
        const form = editor.closest("form");
        if (form?.requestSubmit) form.requestSubmit();
        else notify("Approved, but the site's Send control could not be found.");
      }
    });
  }, true);

  document.addEventListener("click", (event) => {
    if (!event.isTrusted || !(event.target instanceof Element)) return;
    const button = event.target.closest(SEND_SELECTOR);
    if (!button) return;
    const editor = button.closest("form")?.querySelector(EDITOR_SELECTOR)
      || document.querySelector(EDITOR_SELECTOR);
    if (!editor) return;
    const text = editorText(editor);
    if (!containsMarker(text)) return;
    hold(event);
    checkPrompt(editor, text, () => {
      if (button.isConnected && !button.disabled) button.click();
      else notify("Approved, but the site's Send control is no longer available.");
    });
  }, true);

  async function base64(file) {
    const buffer = await file.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let offset = 0; offset < bytes.length; offset += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
    }
    return btoa(binary);
  }

  async function inspectFile(file) {
    if (approvedFiles.has(file)) return true;
    if (file.size > MAX_FILE_BYTES) {
      notify(`${file.name} exceeds the 8 MiB inspection limit.`);
      return false;
    }
    try {
      const result = await requestScan({
        action: "scan_file",
        name: file.name,
        mime_type: file.type,
        content_base64: await base64(file)
      });
      if (!result?.approved) {
        if (result?.error) notify(`Walled AI blocked this file: ${result.error}`);
        return false;
      }
      approvedFiles.add(file);
      return true;
    } catch (error) {
      notify(`Walled AI could not inspect this file: ${error.message}`);
      return false;
    }
  }

  document.addEventListener("change", async (event) => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement) || input.type !== "file") return;
    const files = Array.from(input.files || []);
    if (!files.length || files.every((file) => approvedFiles.has(file))) return;
    hold(event);
    for (const file of files) {
      if (!(await inspectFile(file))) {
        input.value = "";
        return;
      }
    }
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }, true);

  document.addEventListener("drop", async (event) => {
    if (!event.isTrusted || !event.dataTransfer?.files?.length) return;
    const files = Array.from(event.dataTransfer.files);
    if (files.every((file) => approvedFiles.has(file))) return;
    hold(event);
    for (const file of files) {
      if (!(await inspectFile(file))) return;
    }
    const transfer = new DataTransfer();
    for (const file of files) transfer.items.add(file);
    event.target.dispatchEvent(new DragEvent("drop", {
      bubbles: true,
      cancelable: true,
      composed: true,
      dataTransfer: transfer,
      clientX: event.clientX,
      clientY: event.clientY
    }));
  }, true);

  document.addEventListener("paste", async (event) => {
    if (!event.isTrusted || !event.clipboardData?.files?.length) return;
    const files = Array.from(event.clipboardData.files);
    if (files.every((file) => approvedFiles.has(file))) return;
    hold(event);
    for (const file of files) {
      if (!(await inspectFile(file))) return;
    }
    const transfer = new DataTransfer();
    for (const file of files) transfer.items.add(file);
    event.target.dispatchEvent(new ClipboardEvent("paste", {
      bubbles: true,
      cancelable: true,
      composed: true,
      clipboardData: transfer
    }));
  }, true);
})();
