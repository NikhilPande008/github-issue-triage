import { useState } from "react";
import { createRoot } from "react-dom/client";
import { InvestigationDetail } from "./pages/InvestigationDetail";
import { Investigations } from "./pages/Investigations";
import "./styles.css";

function App() {
  const [id, setId] = useState(() => new URLSearchParams(window.location.search).get("id"));
  const open = (investigationId: string) => { window.history.pushState({}, "", `?id=${investigationId}`); setId(investigationId); };
  const back = () => { window.history.pushState({}, "", "/"); setId(null); };
  return id ? <InvestigationDetail id={id} onBack={back} /> : <Investigations onOpen={open} />;
}

createRoot(document.getElementById("root")!).render(<App />);
