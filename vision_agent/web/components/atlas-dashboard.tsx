"use client";

import { useEffect, useMemo, useState } from "react";

import type { AtlasDashboardState } from "../lib/atlas/types";
import { Metric } from "./metric";
import { VisionIntake } from "./vision-intake";

type View = "situation" | "negotiation" | "approvals" | "vision";

type AtlasDashboardProps = {
  initialState?: AtlasDashboardState | null;
};

function statusLabel(value: string) {
  return value.replaceAll("_", " ");
}

export function AtlasDashboard({ initialState = null }: AtlasDashboardProps) {
  const [state, setState] = useState<AtlasDashboardState | null>(initialState);
  const [view, setView] = useState<View>("situation");
  const [busyApproval, setBusyApproval] = useState<string | null>(null);
  const [whyQuestion, setWhyQuestion] = useState("Why did ATLAS choose these sources?");
  const [whyAnswer, setWhyAnswer] = useState<string | null>(null);

  async function load() {
    const response = await fetch("/api/atlas/state", { cache: "no-store" });
    setState(await response.json());
  }

  useEffect(() => {
    if (!initialState) void load();
  }, [initialState]);

  const approvedCount = useMemo(
    () => state?.proposal.approvals.filter((approval) => approval.status === "approved").length ?? 0,
    [state],
  );

  async function decide(approvalId: string, decision: "approved" | "rejected") {
    setBusyApproval(approvalId);
    const response = await fetch(`/api/atlas/approvals/${approvalId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision }),
    });
    if (response.ok) setState(await response.json());
    setBusyApproval(null);
  }

  async function reset() {
    const response = await fetch("/api/atlas/demo", { method: "POST" });
    setState(await response.json());
    setView("situation");
  }

  async function askWhy() {
    const response = await fetch("/api/atlas/why", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: whyQuestion,
        evidence: { calculation: state?.proposal.calculation, allocations: state?.proposal.allocations },
      }),
    });
    const body = await response.json();
    setWhyAnswer(body.answer ?? body.error);
  }

  if (!state) return <main className="loading">Starting ATLAS coordination graph…</main>;
  const b = state.proposal.calculation;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">A</span><div><strong>ReliefLink</strong><small>ATLAS coordination</small></div></div>
        <nav>
          {(["situation", "negotiation", "approvals", "vision"] as View[]).map((item) => (
            <button key={item} className={view === item ? "active" : ""} onClick={() => setView(item)}>
              <span>{item === "situation" ? "◎" : item === "negotiation" ? "⇄" : item === "approvals" ? "✓" : "▣"}</span>
              {item === "vision" ? "Camera & intake" : item[0].toUpperCase() + item.slice(1)}
              {item === "approvals" ? <b>{state.proposal.approvals.length - approvedCount}</b> : null}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot"><span className="live-dot" /> Synthetic graph online<small>Human approval enforced</small></div>
      </aside>
      <main>
        <header className="topbar">
          <div><p className="eyebrow">Regional operations / Alameda County</p><h1>{view === "vision" ? "Inventory intake" : "ATLAS command center"}</h1></div>
          <div className="header-actions"><span className="pill synthetic">Synthetic demo</span><button className="button ghost" onClick={reset}>Reset scenario</button></div>
        </header>

        {view === "situation" ? <>
          <section className="impact-banner"><div className="severity">!</div><div><p>{state.activeImpact.severity} active impact</p><h2>{state.activeImpact.title}</h2><span>{state.activeImpact.source} · matched to {state.activeImpact.affectedSite}</span></div><button className="button light" onClick={() => setView("negotiation")}>Inspect response</button></section>
          <section className="metric-row">
            <Metric label="Forecast demand" value={b.forecastDemand} hint="baseline + observed + weather" />
            <Metric label="Calculated shortage" value={b.calculatedShortage} hint="includes safety stock" />
            <Metric label="Optimizer allocation" value={b.optimizerRecommendedQuantity} hint="feasible units" />
            <Metric label="Approvals" value={`${approvedCount} / ${state.proposal.approvals.length}`} hint={statusLabel(state.proposal.status)} />
          </section>
          <div className="two-column">
            <section className="panel">
              <div className="section-heading"><div><p className="eyebrow">Network response</p><h2>Who ATLAS brought in</h2></div><span className="pill neutral">4 organizations</span></div>
              <div className="network-list">{state.network.map((node) => <div key={node.name} className="network-node"><span className={`node-icon ${node.type}`}>{node.type === "food_bank" ? "FB" : node.type === "vendor" ? "V" : "L"}</span><div><strong>{node.name}</strong><small>{node.detail}</small></div><span className="node-status">{node.status}</span></div>)}</div>
            </section>
            <section className="panel allocation-card">
              <div className="section-heading"><div><p className="eyebrow">Proposed allocation</p><h2>150 units to Fremont</h2></div><span className={`pill status-${state.proposal.status}`}>{statusLabel(state.proposal.status)}</span></div>
              <p>{state.proposal.explanation}</p>
              {state.proposal.allocations.map((allocation) => <div className="allocation" key={allocation.sourceId}><div><strong>{allocation.sourceType === "site" ? "Oakland Food Bank" : "Bay Fresh Foods"}</strong><span>{allocation.distanceMiles} mi · pickup feasible</span></div><b>{allocation.quantity}</b></div>)}
              <button className="button primary full" onClick={() => setView("approvals")}>Review required approvals</button>
            </section>
          </div>
          <section className="panel evidence-panel"><div className="section-heading"><div><p className="eyebrow">Bullwhip controls</p><h2>Recommendation evidence</h2></div><span className="pill safe">Deterministic</span></div><div className="evidence-grid"><Metric label="Baseline demand" value={b.baselineDemand} /><Metric label="Recent demand" value={b.observedRecentDemand} /><Metric label="Weather multiplier" value={`${b.weatherAdjustment}×`} /><Metric label="On hand" value={b.onHandInventory} /><Metric label="Reserved" value={b.reservedInventory} /><Metric label="In transit" value={b.inTransitInventory} /><Metric label="Safety stock" value={b.safetyStock} /><Metric label="Requested" value={b.requestedQuantity} /></div><p className="helper">Forecast demand remains separate from requested, optimizer-recommended, and human-approved quantity. Smoothing, confidence thresholds, cooldowns, duplicate detection, and maximum order-change limits are applied before a request is published.</p></section>
        </> : null}

        {view === "negotiation" ? <section className="panel">
          <div className="section-heading"><div><p className="eyebrow">Negotiation {state.proposal.negotiationId}</p><h2>Persisted agent messages</h2></div><span className="pill neutral">Structured payloads</span></div>
          <div className="why-box"><div><strong>Ask ATLAS why</strong><small>Claude explains validated evidence; it cannot change the plan.</small></div><input value={whyQuestion} onChange={(event) => setWhyQuestion(event.target.value)} /><button className="button primary" onClick={askWhy}>Ask</button>{whyAnswer ? <p>{whyAnswer}</p> : null}</div>
          <div className="message-list">{state.messages.map((message) => <article key={message.id} className="message"><div className="message-meta"><span className="message-type">{statusLabel(message.messageType)}</span><time>{new Date(message.createdAt).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</time></div><h3>{message.explanation}</h3><pre>{JSON.stringify(message.payload, null, 2)}</pre><small>ID {message.id} · run {message.agentRunId}{message.parentMessageId ? ` · reply to ${message.parentMessageId}` : ""}</small></article>)}</div>
        </section> : null}

        {view === "approvals" ? <div className="two-column approvals-layout">
          <section className="panel"><div className="section-heading"><div><p className="eyebrow">Human authority</p><h2>Required commitments</h2></div><span className={`pill status-${state.proposal.status}`}>{statusLabel(state.proposal.status)}</span></div><p className="panel-intro">Each organization decides only its own commitment. Agents cannot press these controls or approve their own proposals.</p><div className="approval-list">{state.proposal.approvals.map((approval) => <div className="approval" key={approval.id}><div><strong>{approval.organizationName}</strong><small>{statusLabel(approval.approvalRole)}</small></div><span className={`decision ${approval.status}`}>{approval.status}</span>{approval.status === "pending" ? <div className="decision-buttons"><button disabled={busyApproval === approval.id} onClick={() => decide(approval.id, "rejected")}>Reject</button><button disabled={busyApproval === approval.id} onClick={() => decide(approval.id, "approved")}>Approve</button></div> : null}</div>)}</div></section>
          <section className="panel"><div className="section-heading"><div><p className="eyebrow">Audit trail</p><h2>Decision timeline</h2></div></div><div className="timeline">{state.timeline.map((event) => <div className={`timeline-event ${event.kind}`} key={event.id}><i /><div><span>{event.actor} · {new Date(event.timestamp).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</span><strong>{event.title}</strong><p>{event.detail}</p></div></div>)}</div></section>
        </div> : null}

        {view === "vision" ? <VisionIntake /> : null}
      </main>
    </div>
  );
}
