import { useEffect, useState } from "react";
import { InvestigationTable } from "../components/InvestigationTable";
import { api, type Classification, type Investigation } from "../services/api";

export function Investigations({ onOpen }: { onOpen: (id: string) => void }) {
  const [items, setItems] = useState<Investigation[]>([]); const [error, setError] = useState<string>(); const [classification, setClassification] = useState<Classification | undefined>(); const [page, setPage] = useState(1); const [total, setTotal] = useState(0); const pageSize = 20;
  useEffect(() => { api.investigations(page, classification).then((result) => { setItems(result.items); setTotal(result.total); }).catch((err: Error) => setError(err.message)); }, [classification, page]);
  return <main><h1>Investigations</h1><label>Classification filter <select aria-label="Classification filter" value={classification ?? ""} onChange={(event) => { setClassification((event.target.value || undefined) as Classification | undefined); setPage(1); }}><option value="">All</option>{["REPRODUCED", "NEEDS_INFO", "WONT_REPRO", "NOT_A_BUG", "DUPLICATE"].map((value) => <option key={value}>{value}</option>)}</select></label>{error ? <p className="error">Unable to load investigations: {error}</p> : <><InvestigationTable items={items} onOpen={onOpen} /><div className="pagination"><button disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button><span>Page {page}</span><button disabled={page * pageSize >= total} onClick={() => setPage(page + 1)}>Next</button></div></>}</main>;
}
