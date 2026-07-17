"use client";

import { useEffect, useRef, useState } from "react";

import type { VisionResult } from "../lib/vision";

export function VisionIntake() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<VisionResult | null>(null);
  const [count, setCount] = useState(0);
  const [busy, setBusy] = useState(false);
  const [cloud, setCloud] = useState(true);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reviewStatus, setReviewStatus] = useState<"draft" | "pending" | "approved">("draft");
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => () => stopCamera(), []);

  useEffect(() => {
    if (!cameraOpen || !videoRef.current || !streamRef.current) return;
    videoRef.current.srcObject = streamRef.current;
    void videoRef.current.play();
  }, [cameraOpen]);

  function stopCamera() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraOpen(false);
  }

  async function startCamera() {
    setCameraError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError("Camera access is unavailable in this browser. Choose a still image instead.");
      return;
    }
    try {
      stopCamera();
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } },
      });
      streamRef.current = stream;
      setCameraOpen(true);
    } catch (cameraException) {
      setCameraError(cameraException instanceof Error && cameraException.name === "NotAllowedError"
        ? "Camera permission was denied. Allow camera access in the browser, then try again."
        : "The camera could not be opened. Choose a still image instead.");
    }
  }

  function captureFrame() {
    const video = videoRef.current;
    if (!video || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || !video.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      if (!blob) return;
      setFile(new File([blob], `shelf-${new Date().toISOString().replaceAll(":", "-")}.jpg`, { type: "image/jpeg" }));
      setResult(null);
      setReviewStatus("draft");
      stopCamera();
    }, "image/jpeg", 0.88);
  }

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
          <div className="camera-actions">
            {!cameraOpen ? <button className="button secondary" onClick={() => void startCamera()}>Open phone camera</button> : null}
            {cameraOpen ? <>
              <button className="button primary" onClick={captureFrame}>Capture shelf photo</button>
              <button className="button ghost" onClick={stopCamera}>Close camera</button>
            </> : null}
          </div>
          <p className="helper">Cloud mode counts visible packages with the configured Roboflow detector. The camera captures one still image; it does not continuously track people or inventory.</p>
          {cameraError ? <p className="error">{cameraError}</p> : null}
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
          <div className="empty-vision">
            {cameraOpen ? <video ref={videoRef} className="camera-preview" muted playsInline aria-label="Live shelf camera preview" /> : <><span>Detection overlay</span><p>Open the camera or choose a still image. Bounding boxes, confidence, count, classification, and disagreements appear here.</p></>}
          </div>
        )}
      </div>
    </section>
  );
}
