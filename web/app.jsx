/* ReliefLink CRM dashboard. React (CDN, no build step), Salesforce-style, square corners. */

const { useState, useEffect, useCallback, useRef } = React;

const PATHS = ["/sites", "/inventory", "/forecasts", "/gaps", "/recommendations"];
const REFRESH_MS = 5000;

function useLedger() {
  const [data, setData] = useState({
    sites: [], inventory: [], forecasts: [], gaps: [], recommendations: [],
  });
  const [updatedAt, setUpdatedAt] = useState(null);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const [sites, inventory, forecasts, gaps, recommendations] = await Promise.all(
        PATHS.map((p) => fetch(p).then((r) => r.json()))
      );
      setData({ sites, inventory, forecasts, gaps, recommendations });
      setUpdatedAt(new Date());
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  return { data, updatedAt, error, refresh };
}

function DataTable({ columns, rows, search, empty }) {
  const needle = (search || "").toLowerCase();
  const visible = needle
    ? rows.filter((row) => JSON.stringify(row).toLowerCase().includes(needle))
    : rows;
  if (!visible.length) return <div className="empty">{empty || "Nothing here yet."}</div>;
  return (
    <table>
      <thead>
        <tr>{columns.map((c) => <th key={c.label} className={c.num ? "num" : ""}>{c.label}</th>)}</tr>
      </thead>
      <tbody>
        {visible.map((row, i) => (
          <tr key={row.id ?? i}>
            {columns.map((c) => (
              <td key={c.label} className={c.num ? "num" : ""}>
                {c.render ? c.render(row) : row[c.key]}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Card({ title, meta, children }) {
  return (
    <div className="card">
      <div className="card-header"><h2>{title}</h2>{meta && <span className="meta">{meta}</span>}</div>
      {children}
    </div>
  );
}

function Home({ data, siteName, search }) {
  const totalUnits = data.inventory.reduce((sum, s) => sum + s.count, 0);
  const shortages = data.gaps.filter((g) => g.gap > 0);
  const maxMult = Math.max(1, ...data.forecasts.map((f) => f.multiplier));
  return (
    <div>
      <div className="kpi-row">
        <div className="kpi"><div className="kpi-label">Sites</div><div className="kpi-value">{data.sites.length}</div></div>
        <div className="kpi"><div className="kpi-label">Units on hand</div><div className="kpi-value">{totalUnits.toLocaleString()}</div></div>
        <div className={"kpi" + (shortages.length ? " alert" : "")}>
          <div className="kpi-label">Shortages</div><div className="kpi-value">{shortages.length}</div>
        </div>
        <div className={"kpi" + (maxMult > 1.5 ? " alert" : "")}>
          <div className="kpi-label">Peak demand multiplier</div><div className="kpi-value">x{maxMult.toFixed(2)}</div>
        </div>
      </div>
      <Card title="Shortages needing action" meta="gap = predicted demand minus current stock">
        <DataTable
          search={search}
          empty="No shortages. All sites can cover predicted demand."
          columns={[
            { label: "Site", render: (g) => siteName(g.site_id) },
            { label: "Category", key: "category" },
            { label: "Current", key: "current", num: true },
            { label: "Predicted", key: "predicted_demand", num: true },
            { label: "Gap", num: true, render: (g) => <span className="badge shortage">short {g.gap}</span> },
          ]}
          rows={shortages.sort((a, b) => b.gap - a.gap)}
        />
      </Card>
    </div>
  );
}

function Inventory({ data, siteName, search }) {
  return (
    <Card title="Current inventory" meta="latest camera / spreadsheet count per site + category">
      <DataTable
        search={search}
        empty="No inventory yet. Point a camera at a shelf (/camera) or upload a spreadsheet."
        columns={[
          { label: "Site", render: (s) => siteName(s.site_id) },
          { label: "Category", key: "category" },
          { label: "Count", key: "count", num: true },
          { label: "Confidence", num: true, render: (s) => s.confidence.toFixed(2) },
          { label: "Source", render: (s) => <span className="badge">{s.source}</span> },
          { label: "Updated", render: (s) => new Date(s.created_at + "Z").toLocaleTimeString() },
        ]}
        rows={[...data.inventory].sort((a, b) => a.site_id - b.site_id)}
      />
    </Card>
  );
}

function Forecasts({ data, siteName, search }) {
  return (
    <Card title="Demand forecasts (next 48h)" meta="weather.gov + OpenFEMA driven">
      <DataTable
        search={search}
        empty="No forecasts yet. Run: python -m disruption_agent.agent --synthetic"
        columns={[
          { label: "Site", render: (f) => siteName(f.site_id) },
          { label: "Category", key: "category" },
          { label: "Predicted", key: "predicted_demand", num: true },
          {
            label: "Multiplier", num: true,
            render: (f) => (
              <span className={"badge " + (f.multiplier >= 2 ? "shortage" : f.multiplier > 1 ? "warn" : "ok")}>
                x{f.multiplier.toFixed(2)}
              </span>
            ),
          },
          { label: "Reason", key: "reason" },
        ]}
        rows={[...data.forecasts].sort((a, b) => b.multiplier - a.multiplier)}
      />
    </Card>
  );
}

function Gaps({ data, siteName, search }) {
  return (
    <Card title="Surplus / shortage per site + category" meta="what the reallocation agent consumes">
      <DataTable
        search={search}
        empty="No gaps computable yet: needs both inventory and forecasts."
        columns={[
          { label: "Site", render: (g) => siteName(g.site_id) },
          { label: "Category", key: "category" },
          { label: "Current", key: "current", num: true },
          { label: "Predicted", key: "predicted_demand", num: true },
          {
            label: "Status", num: true,
            render: (g) =>
              g.gap > 0
                ? <span className="badge shortage">short {g.gap}</span>
                : <span className="badge surplus">spare {-g.gap}</span>,
          },
        ]}
        rows={[...data.gaps].sort((a, b) => b.gap - a.gap)}
      />
    </Card>
  );
}

function Transfers({ data, siteName, search, refresh }) {
  const approve = async (id) => {
    await fetch(`/recommendations/${id}/approve`, { method: "POST" });
    refresh();
  };
  return (
    <Card title="Recommended transfers" meta="proposed by the reallocation agent">
      <DataTable
        search={search}
        empty="No recommendations yet. Run: python -m reallocation_agent.agent"
        columns={[
          { label: "From", render: (r) => siteName(r.from_site_id) },
          { label: "To", render: (r) => siteName(r.to_site_id) },
          { label: "Category", key: "category" },
          { label: "Qty", key: "quantity", num: true },
          { label: "Reason", key: "reason" },
          { label: "Status", render: (r) => <span className={"badge " + r.status}>{r.status}</span> },
          {
            label: "Action",
            render: (r) =>
              r.status === "proposed"
                ? <button className="btn primary" onClick={() => approve(r.id)}>Approve</button>
                : null,
          },
        ]}
        rows={data.recommendations}
      />
    </Card>
  );
}

function Spreadsheets({ refresh }) {
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);

  const upload = async () => {
    const file = fileRef.current.files[0];
    if (!file) return;
    setBusy(true);
    const body = new FormData();
    body.append("file", file);
    const response = await fetch("/spreadsheets/import", { method: "POST", body });
    setResult(await response.json());
    setBusy(false);
    refresh();
  };

  return (
    <div>
      <Card title="Upload your inventory spreadsheet" meta=".xlsx or .csv, headers: site / category / count">
        <div className="upload-zone">
          <div>Drop in any inventory sheet. Unknown sites are created automatically.</div>
          <input ref={fileRef} type="file" accept=".xlsx,.csv" />
          <button className="btn primary" onClick={upload} disabled={busy}>
            {busy ? "Importing..." : "Import into shared ledger"}
          </button>
        </div>
        {result && <pre className="result">{JSON.stringify(result, null, 2)}</pre>}
      </Card>
      <Card title="Your connected spreadsheet" meta="regenerated from the live ledger on every download">
        <div className="links">
          <a className="btn primary" href="/spreadsheets/export">Download live spreadsheet</a>
          <a className="btn" href="/spreadsheets/template">Download blank template</a>
        </div>
        <div className="empty">
          The exported workbook always reflects the ledger at download time: current inventory,
          forecasts, and gaps, plus an Upload sheet you can fill and re-import. Same link, always fresh.
        </div>
      </Card>
    </div>
  );
}

const TABS = ["Home", "Inventory", "Forecasts", "Gaps", "Transfers", "Spreadsheets"];

function App() {
  const { data, updatedAt, error, refresh } = useLedger();
  const [tab, setTab] = useState("Home");
  const [search, setSearch] = useState("");

  const siteName = (id) => (data.sites.find((s) => s.id === id) || { name: `site ${id}` }).name;
  const shared = { data, siteName, search, refresh };

  return (
    <div>
      <header className="global-header">
        <div className="logo">Relief<span>Link</span> CRM</div>
        <input
          type="search"
          placeholder="Search this list..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="env">
          {error ? "ledger unreachable" : updatedAt ? `live - updated ${updatedAt.toLocaleTimeString()}` : "loading"}
        </div>
      </header>
      <nav className="nav-tabs">
        {TABS.map((t) => (
          <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>{t}</button>
        ))}
        <a href="/camera">Live Camera</a>
        <a href="/docs" target="_blank" rel="noreferrer">API</a>
      </nav>
      <main className="page">
        {error && <Card title="Connection problem"><div className="empty">{error}. Is the server running?</div></Card>}
        {tab === "Home" && <Home {...shared} />}
        {tab === "Inventory" && <Inventory {...shared} />}
        {tab === "Forecasts" && <Forecasts {...shared} />}
        {tab === "Gaps" && <Gaps {...shared} />}
        {tab === "Transfers" && <Transfers {...shared} />}
        {tab === "Spreadsheets" && <Spreadsheets refresh={refresh} />}
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
