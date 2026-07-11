import DOMPurify from "dompurify";
import { marked } from "marked";

marked.setOptions({
  breaks: true,
  gfm: true,
});

export function stripAssistantInternalMarkers(value: unknown) {
  return String(value || "")
    .replace(/\[(?:E|K):[^\]]*(?:\]|$)/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function renderAssistantMarkdown(value: unknown) {
  const source = stripAssistantInternalMarkers(value);
  if (!source) return "";
  const rendered = marked.parse(source, { async: false }) as string;
  const sanitized = DOMPurify.sanitize(rendered, {
    FORBID_TAGS: ["script", "style", "iframe", "object", "embed", "form", "input", "button", "select", "textarea"],
    FORBID_ATTR: ["style", "srcdoc"],
    USE_PROFILES: { html: true },
  });

  const container = document.createElement("div");
  container.innerHTML = sanitized;
  container.querySelectorAll("a").forEach((link) => {
    link.setAttribute("target", "_blank");
    link.setAttribute("rel", "noopener noreferrer");
  });
  return container.innerHTML;
}
