"use client";

import { useState } from "react";

import type { VisionResult } from "../lib/vision";

export function VisionIntake() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<VisionResult | null>(null);
  const [count, setCount] = useState(0);
  const [busy, setBusy] = useState(false);
  const [cloud, setCloud] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reviewStatus, setReviewStatus] = useState<"draft" | "pending" | "approved">("draft");

  async function analyze() {
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.set("image", file);
    form.set("synthetic", cloud ? "false" : "true");
    const response = await fetch("/api/vision/analyze", { method: "POST", body: form });
    const body = await response.json();
    if (!response.ok) setError(body.error ?? "Analysis failed");
    else {
      setResult(body);
      setCount(body.visibleObjectCount);
    }
    setBusy(false);
  }

  async function intakeAction(action: "submit" | "approve") {
    if (!result) return;
    const response = await fetch("/api/atlas/demo/intake", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, detectionCount: result.visibleObjectCount, confirmedCount: count }),
    });
    const body = await response.json();
    if (!response.ok) setError(body.error);
    else setReviewStatus(body.status);
  }

  return (
    <section className="panel vision-panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Still-image intake</p>
          <h2>Count first. Classify second. Human confirms.</h2>
        </div>
        <span className="pill neutral">No continuous tracking</span>
      </div>
      <div className="vision-grid">
        <div className="upload-zone">
          <input id="food-image" type="file" accept="image/*" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          <label htmlFor="food-image">
            <span className="upload-icon">＋</span>
            <strong>{file ? file.name : "Choose a phone photo"}</strong>
            <small>JPEG, PNG, or HEIC-compatible browser upload · max 8 MB</small>
          </label>
          <button className="button primary" disabled={!file || busy} onClick={analyze}>
            {busy ? "Running package detection…" : cloud ? "Run cloud analysis" : "Run synthetic review"}
          </button>
          <label className="cloud-toggle"><input type="checkbox" checked={cloud} onChange={(event) => setCloud(event.target.checked)} />Use configured Roboflow + vision LLM</label>
          <p className="helper">Synthetic mode exercises the full review UI without Roboflow or an LLM key. Cloud mode is enabled by server configuration.</p>
          {error ? <p className="error">{error}</p> : null}
        </div>
        {result ? (
          <div className="analysis-result">
            <div className="annotated-image">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={result.imageDataUrl} alt="Uploaded food packages with detection overlay" />
              {result.detections.map((detection, index) => (
                <span
                  key={`${detection.x}-${detection.y}-${index}`}
                  className="detection-box"
                  style={{
                    left: `${((detection.x - detection.width / 2) / result.imageWidth) * 100}%`,
                    top: `${((detection.y - detection.height / 2) / result.imageHeight) * 100}%`,
                    width: `${(detection.width / result.imageWidth) * 100}%`,
                    height: `${(detection.height / result.imageHeight) * 100}%`,
                  }}
                ><b>{index + 1}</b></span>
              ))}
            </div>
            <div className="vision-summary">
              <div><span>Detection mode</span><strong>{result.mode === "cloud" ? "Roboflow cloud" : "Synthetic demo"}</strong></div>
              <div><span>Detector model</span><strong>{result.yoloModel}</strong></div>
              <div><span>Visible detections</span><strong>{result.visibleObjectCount}</strong></div>
              <div><span>Average confidence</span><strong>{Math.round(result.averageConfidence * 100)}%</strong></div>
              <div><span>Product / category</span><strong>{result.classification.product} · {result.classification.category}</strong></div>
              <div><span>Classification source</span><strong>{result.classification.source.replaceAll("_", " ")}</strong></div>
            </div>
            <label className="correction-field">
              Human-confirmed count
              <input type="number" min="0" value={count} onChange={(event) => setCount(Number(event.target.value))} />
            </label>
            {result.classification.uncertainty ? <p className="warning">{result.classification.uncertainty}</p> : null}
            {reviewStatus === "draft" ? <button className="button secondary" onClick={() => intakeAction("submit")}>Submit observation for site review</button> : null}
            {reviewStatus === "pending" ? <button className="button primary" onClick={() => intakeAction("approve")}>Approve as Oakland site reviewer</button> : null}
            {reviewStatus === "approved" ? <p className="success">Approved · Oakland shared inventory increased by {count} units.</p> : null}
            <p className="helper">{reviewStatus === "pending" ? "Pending review: inventory is unchanged and the operator cannot self-approve in persistent mode." : "Approval creates an immutable intake transaction in the shared ledger."}</p>
          </div>
        ) : (
          <div className="empty-vision"><span>Detection overlay</span><p>Bounding boxes, confidence, count, classification, and disagreements appear here.</p></div>
        )}
      </div>
    </section>
  );
}
