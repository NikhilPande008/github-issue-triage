import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { InvestigationDetail } from "./pages/InvestigationDetail";
import { EvidenceBrief } from "./pages/EvidenceBrief";
import { EvidenceResults } from "./pages/EvidenceResults";
import { Investigations } from "./pages/Investigations";
import { ReviewerQueue } from "./pages/ReviewerQueue";
import { WeeklyReportPage } from "./pages/WeeklyReport";
import "./styles.css";

export function Header() {
  return <header className="app-header"><div className="shell header-content"><a className="brand" href="/" aria-label="EvidenceTrail, investigation list"><span>EvidenceTrail</span><small>Autonomous evidence-based investigation of GitHub issues, powered by GPT‑5.6 + Codex</small></a><nav className="header-links" aria-label="Primary"><a href="/">Triage Queue</a><a href="?brief=1">Evidence Brief</a><a href="?results=1">Evidence Results</a></nav></div></header>;
}

export function App() {
  const currentId = () => new URLSearchParams(window.location.search).get("id");
  const reviewerMode = () => new URLSearchParams(window.location.search).get("reviewer") === "1";
  const reportsMode = () => new URLSearchParams(window.location.search).get("reports") === "1";
  const briefMode = () => new URLSearchParams(window.location.search).get("brief") === "1";
  const resultsMode = () => new URLSearchParams(window.location.search).get("results") === "1";
  const [id, setId] = useState(currentId);
  const [reviewer, setReviewer] = useState(reviewerMode);
  const [reports, setReports] = useState(reportsMode);
  const [brief, setBrief] = useState(briefMode);
  const [results, setResults] = useState(resultsMode);
  useEffect(() => {
    const syncLocation = () => { setId(currentId()); setReviewer(reviewerMode()); setReports(reportsMode()); setBrief(briefMode()); setResults(resultsMode()); };
    window.addEventListener("popstate", syncLocation);
    return () => window.removeEventListener("popstate", syncLocation);
  }, []);
  return <><Header /><main className="shell">{results ? <EvidenceResults /> : brief ? <EvidenceBrief /> : reviewer ? reports ? <WeeklyReportPage /> : <ReviewerQueue /> : id ? <InvestigationDetail id={id} /> : <Investigations />}</main></>;
}

const root = document.getElementById("root");
if (root) createRoot(root).render(<App />);
