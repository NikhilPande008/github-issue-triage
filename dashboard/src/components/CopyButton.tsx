import { useState } from "react";

export function CopyButton({ value, label = "Copy" }: { value: string; label?: string }) {
  const [result, setResult] = useState<"idle" | "success" | "error">("idle");
  const copy = async () => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard access is unavailable");
      await navigator.clipboard.writeText(value);
      setResult("success");
    } catch {
      setResult("error");
    }
    window.setTimeout(() => setResult("idle"), 1600);
  };
  const feedback = result === "success" ? "Copied to clipboard." : result === "error" ? "Unable to copy to clipboard." : "";
  return <span className="copy-control"><button className="copy-button" type="button" onClick={copy} aria-label={label}>{result === "success" ? "Copied" : "Copy"}</button><span className="copy-feedback" role="status">{feedback}</span></span>;
}
