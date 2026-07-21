import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { InvestigationDetail } from "./pages/InvestigationDetail";
import { EvidenceBrief } from "./pages/EvidenceBrief";
import { EvidenceResults } from "./pages/EvidenceResults";
import { Investigations } from "./pages/Investigations";
import { ReviewerQueue } from "./pages/ReviewerQueue";
import { ReviewerPacket } from "./pages/ReviewerPacket";
import { WeeklyReportPage } from "./pages/WeeklyReport";
import { LiveDemo } from "./pages/LiveDemo";
import { CompareApproaches } from "./pages/CompareApproaches";
import { RetrospectiveEvaluation } from "./pages/RetrospectiveEvaluation";
import { api } from "./services/api";
import "./styles.css";

export function Header() {
  const [live, setLive] = useState(false); useEffect(() => { api.liveDemoConfig().then((config) => setLive(config.enabled)).catch(() => undefined); }, []);
  return <header className="app-header"><div className="shell header-content"><a className="brand" href="/" aria-label="Issue Triage, investigation list"><span className="brand-mark" aria-hidden="true">IT</span><span className="brand-copy"><strong>Issue Triage</strong><small>Evidence-first GitHub issue investigation</small></span></a><nav className="header-links" aria-label="Primary"><a href="/">Triage Queue</a><a href="?brief=1">Evidence Brief</a><a href="?results=1">Evidence Results</a><a href="?compare=1">Why evidence?</a><a href="?evaluation=1">Retrospective evaluation</a>{live && <a href="?live=1">Live demo</a>}</nav></div></header>;
}

export function App() {
  const currentId = () => new URLSearchParams(window.location.search).get("id");
  const reviewerMode = () => new URLSearchParams(window.location.search).get("reviewer") === "1";
  const reviewerPacket = () => new URLSearchParams(window.location.search).get("packet");
  const reportsMode = () => new URLSearchParams(window.location.search).get("reports") === "1";
  const briefMode = () => new URLSearchParams(window.location.search).get("brief") === "1";
  const resultsMode = () => new URLSearchParams(window.location.search).get("results") === "1";
  const liveMode = () => new URLSearchParams(window.location.search).get("live") === "1";
  const compareMode = () => new URLSearchParams(window.location.search).get("compare") === "1";
  const evaluationMode = () => new URLSearchParams(window.location.search).get("evaluation") === "1";
  const [id, setId] = useState(currentId);
  const [reviewer, setReviewer] = useState(reviewerMode);
  const [packet, setPacket] = useState(reviewerPacket);
  const [reports, setReports] = useState(reportsMode);
  const [brief, setBrief] = useState(briefMode);
  const [results, setResults] = useState(resultsMode);
  const [live, setLive] = useState(liveMode);
  const [compare, setCompare] = useState(compareMode);
  const [evaluation, setEvaluation] = useState(evaluationMode);
  useEffect(() => {
    const syncLocation = () => { setId(currentId()); setReviewer(reviewerMode()); setPacket(reviewerPacket()); setReports(reportsMode()); setBrief(briefMode()); setResults(resultsMode()); setLive(liveMode()); setCompare(compareMode()); setEvaluation(evaluationMode()); };
    window.addEventListener("popstate", syncLocation);
    return () => window.removeEventListener("popstate", syncLocation);
  }, []);
  return <><Header /><main className="shell">{evaluation ? <RetrospectiveEvaluation /> : compare ? <CompareApproaches /> : live ? <LiveDemo /> : results ? <EvidenceResults /> : brief ? <EvidenceBrief /> : reviewer ? reports ? <WeeklyReportPage /> : packet ? <ReviewerPacket packetId={packet} /> : <ReviewerQueue /> : id ? <InvestigationDetail id={id} /> : <Investigations />}</main></>;
}

const root = document.getElementById("root");
if (root) createRoot(root).render(<App />);
