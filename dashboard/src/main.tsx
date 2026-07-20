import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { InvestigationDetail } from "./pages/InvestigationDetail";
import { Investigations } from "./pages/Investigations";
import "./styles.css";

function App() {
  const currentId = () => new URLSearchParams(window.location.search).get("id");
  const [id, setId] = useState(currentId);
  useEffect(() => {
    const syncLocation = () => setId(currentId());
    window.addEventListener("popstate", syncLocation);
    return () => window.removeEventListener("popstate", syncLocation);
  }, []);
  return <><header className="app-header"><div className="shell"><a className="brand" href="/" aria-label="Issue Triage, investigation list"><span>Issue Triage</span><small>Autonomous evidence-based investigation of GitHub issues, powered by GPT‑5.6 + Codex</small></a></div></header><main className="shell">{id ? <InvestigationDetail id={id} /> : <Investigations />}</main></>;
}

createRoot(document.getElementById("root")!).render(<App />);
