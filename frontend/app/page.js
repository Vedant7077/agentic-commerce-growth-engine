"use client";

import { useState, useEffect, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const SAMPLE_QUERIES = [
  "Find me a mechanical keyboard under ₹3,000",
  "Recommend an ergonomic wireless mouse under ₹2,000",
  "Looking for noise cancelling gaming headphones",
];

export default function ShoppingAgentDemo() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState("");
  const [threadId, setThreadId] = useState(null);
  const [orderId, setOrderId] = useState(null);

  // Flow states: 'idle' | 'pending_confirmation' | 'completed' | 'order_created' | 'failed' | 'rejected'
  const [agentState, setAgentState] = useState("idle");
  const [pendingConfirmation, setPendingConfirmation] = useState(null);
  const [orderResult, setOrderResult] = useState(null);
  const [completedExplanation, setCompletedExplanation] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  // Audit trail
  const [auditEvents, setAuditEvents] = useState([]);
  const [auditExpanded, setAuditExpanded] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);

  // Fetch audit trail for an order
  const fetchAuditEvents = useCallback(async (oid) => {
    if (!oid) return;
    setAuditLoading(true);
    try {
      const res = await fetch(`${API_BASE}/audit/${oid}/`);
      if (res.ok) {
        const data = await res.json();
        setAuditEvents(data);
      }
    } catch (err) {
      console.error("Failed to load audit events:", err);
    } finally {
      setAuditLoading(false);
    }
  }, []);

  // Poll/refresh audit trail if an order exists
  useEffect(() => {
    if (orderId) {
      fetchAuditEvents(orderId);
      setAuditExpanded(true);
    }
  }, [orderId, fetchAuditEvents]);

  // Handle initial shopping query
  async function handleSubmit(e) {
    if (e) e.preventDefault();
    if (!query.trim() || loading) return;

    setLoading(true);
    setLoadingStep("Agent is extracting requirements & scanning catalogue...");
    setErrorMessage("");
    setOrderResult(null);
    setPendingConfirmation(null);
    setCompletedExplanation("");
    setAuditEvents([]);
    setOrderId(null);

    try {
      const res = await fetch(`${API_BASE}/agent/start/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: query.trim(), user_id: 1 }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Server returned error (${res.status})`);
      }

      const data = await res.json();
      setThreadId(data.thread_id);

      if (data.status === "pending_confirmation") {
        setPendingConfirmation(data.pending_confirmation);
        setAgentState("pending_confirmation");
      } else if (data.status === "completed") {
        setCompletedExplanation(data.explanation || "Request completed.");
        setOrderResult(data.order_result || null);
        setAgentState("completed");

        if (data.order_result?.id) {
          setOrderId(data.order_result.id);
        }
      } else {
        throw new Error(`Unexpected agent status: ${data.status}`);
      }
    } catch (err) {
      setAgentState("failed");
      setErrorMessage(err.message || "Failed to start agent pipeline.");
    } finally {
      setLoading(false);
      setLoadingStep("");
    }
  }

  // Handle human confirmation (Approve or Cancel)
  async function handleConfirm(approved) {
    if (!threadId || loading) return;

    setLoading(true);
    setLoadingStep(
      approved
        ? "Processing purchase & initializing Razorpay order..."
        : "Cancelling purchase..."
    );
    setErrorMessage("");

    try {
      const res = await fetch(`${API_BASE}/agent/${threadId}/confirm/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved: Boolean(approved) }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Error confirming order (${res.status})`);
      }

      const data = await res.json();

      if (!approved || data.status === "rejected") {
        setAgentState("rejected");
        return;
      }

      const result = data.order_result || {};
      setOrderResult(result);

      if (result.id) {
        setOrderId(result.id);
      }

      // Check if order failed (e.g. gateway timeout)
      if (result.status === "failed" || data.status === "failed") {
        setAgentState("failed");
        setErrorMessage(
          result.detail ||
            "The payment service encountered a temporary timeout. No funds were debited."
        );
      } else if (data.status === "order_created") {
        setAgentState("order_created");
      } else {
        setAgentState("completed");
      }
    } catch (err) {
      setAgentState("failed");
      setErrorMessage(err.message || "An unexpected error occurred during confirmation.");
    } finally {
      setLoading(false);
      setLoadingStep("");
    }
  }

  function handleReset() {
    setAgentState("idle");
    setPendingConfirmation(null);
    setOrderResult(null);
    setCompletedExplanation("");
    setErrorMessage("");
    setThreadId(null);
    setQuery("");
  }

  return (
    <div className="container">
      {/* Top Header */}
      <header className="header">
        <div className="brand">
          <div className="brand-icon">⚡</div>
          <div>
            <h1 className="brand-title">Agentic Commerce Engine</h1>
            <p className="brand-subtitle">Autonomous Shopping Agent with Human-in-the-Loop Checkout</p>
          </div>
        </div>
        <div className="status-badge">
          <div className="status-indicator" />
          <span>Agent Online</span>
        </div>
      </header>

      {/* Query Input Section */}
      <section className="card">
        <h2 className="card-title">🛒 What are you looking to buy today?</h2>

        <div className="sample-queries">
          {SAMPLE_QUERIES.map((sample, idx) => (
            <button
              key={idx}
              className="query-chip"
              disabled={loading}
              onClick={() => {
                setQuery(sample);
              }}
            >
              {sample}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="chat-form">
          <input
            type="text"
            className="chat-input"
            placeholder="e.g. Find me a wireless gaming mouse under ₹2,000..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={loading}
          />
          <button
            type="submit"
            className="btn-primary"
            disabled={loading || !query.trim()}
          >
            {loading ? "Agent Thinking..." : "Ask Agent →"}
          </button>
        </form>
      </section>

      {/* Loading Box */}
      {loading && (
        <div className="loading-box">
          <div className="spinner" />
          <p style={{ color: "#cbd5e1", fontSize: "0.95rem" }}>
            {loadingStep || "Processing agent workflow..."}
          </p>
        </div>
      )}

      {/* Pending Confirmation: Recommendation Card */}
      {agentState === "pending_confirmation" && pendingConfirmation && !loading && (
        <section className="card card-recommendation">
          <div className="badge-tag">Approval Needed</div>
          <div className="rec-header">
            <h2 className="rec-product-name">
              {pendingConfirmation.product_name || pendingConfirmation.product || "Recommended Product"}
            </h2>
            <div className="rec-price">
              {pendingConfirmation.price_display ||
                (pendingConfirmation.price_paise
                  ? `₹${(pendingConfirmation.price_paise / 100).toFixed(2)}`
                  : "₹0.00")}
            </div>
          </div>

          <div className="rec-explanation-box">
            <div className="rec-explanation-label">Why the Agent Picked This</div>
            <p className="rec-explanation-text">
              {pendingConfirmation.explanation || "Selected based on optimal rating and budget fit."}
            </p>
          </div>

          <div className="rec-actions">
            <button
              onClick={() => handleConfirm(true)}
              className="btn-confirm"
              disabled={loading}
            >
              ✓ Confirm Purchase
            </button>
            <button
              onClick={() => handleConfirm(false)}
              className="btn-cancel"
              disabled={loading}
            >
              ✕ Cancel
            </button>
          </div>
        </section>
      )}

      {/* Order Created State (Green Success) */}
      {agentState === "order_created" && orderResult && (
        <section className="state-box state-success">
          <div className="state-title-row">
            <span className="state-icon">✅</span>
            <h2 className="state-title">Order Successfully Placed!</h2>
          </div>
          <p style={{ fontSize: "0.95rem", opacity: 0.9 }}>
            The agent successfully reserved your item and initiated the Razorpay checkout.
          </p>

          <div className="state-details-grid">
            <div className="state-detail-item">
              <span className="state-detail-label">Order ID</span>
              <span className="state-detail-value">#{orderResult.id || orderId}</span>
            </div>
            <div className="state-detail-item">
              <span className="state-detail-label">Status</span>
              <span className="state-detail-value" style={{ textTransform: "capitalize" }}>
                {orderResult.status || "Confirmed"}
              </span>
            </div>
            <div className="state-detail-item">
              <span className="state-detail-label">Total Amount</span>
              <span className="state-detail-value">
                ₹{orderResult.total_paise ? (orderResult.total_paise / 100).toFixed(2) : "0.00"}
              </span>
            </div>
            <div className="state-detail-item">
              <span className="state-detail-label">Razorpay Order ID</span>
              <span className="state-detail-value" style={{ fontSize: "0.85rem" }}>
                {orderResult.razorpay_order_id || "N/A"}
              </span>
            </div>
          </div>

          <div>
            <button onClick={handleReset} className="btn-reset">
              ← Search for Another Product
            </button>
          </div>
        </section>
      )}

      {/* Completed State (Direct / No confirmation required) */}
      {agentState === "completed" && (
        <section className="card">
          <h3 className="card-title">ℹ️ Agent Completed</h3>
          <p style={{ color: "#e2e8f0", lineHeight: 1.6, marginBottom: "1rem" }}>
            {completedExplanation}
          </p>
          {orderResult && (
            <div className="state-details-grid" style={{ marginBottom: "1rem" }}>
              <div className="state-detail-item">
                <span className="state-detail-label">Status</span>
                <span className="state-detail-value">{orderResult.status || "Completed"}</span>
              </div>
              {orderResult.id && (
                <div className="state-detail-item">
                  <span className="state-detail-label">Order ID</span>
                  <span className="state-detail-value">#{orderResult.id}</span>
                </div>
              )}
            </div>
          )}
          <button onClick={handleReset} className="btn-reset">
            Start New Search
          </button>
        </section>
      )}

      {/* Failed State (Amber Alert) */}
      {agentState === "failed" && (
        <section className="state-box state-warning">
          <div className="state-title-row">
            <span className="state-icon">⚠️</span>
            <h2 className="state-title">Order Processing Notice</h2>
          </div>
          <p style={{ fontSize: "0.95rem", lineHeight: 1.6 }}>
            {errorMessage || "The checkout workflow could not be completed at this time."}
          </p>
          <div>
            <button onClick={handleReset} className="btn-reset" style={{ borderColor: "#d97706", color: "#fef3c7" }}>
              Try Another Request
            </button>
          </div>
        </section>
      )}

      {/* Rejected State (Neutral Slate) */}
      {agentState === "rejected" && (
        <section className="state-box state-neutral">
          <div className="state-title-row">
            <span className="state-icon">⏹</span>
            <h2 className="state-title">Purchase Cancelled</h2>
          </div>
          <p style={{ fontSize: "0.95rem", color: "#94a3b8" }}>
            You cancelled this recommendation. No payment was charged and no order was created.
          </p>
          <div>
            <button onClick={handleReset} className="btn-reset">
              Start Over
            </button>
          </div>
        </section>
      )}

      {/* Audit Trail Panel (Collapsible, visible throughout) */}
      <section className="audit-panel">
        <div
          className="audit-header"
          onClick={() => setAuditExpanded(!auditExpanded)}
        >
          <div className="audit-title">
            <span>🛡️ Decision Audit Trail</span>
            {auditEvents.length > 0 && (
              <span className="audit-count">{auditEvents.length} events</span>
            )}
            {orderId && (
              <span style={{ fontSize: "0.8rem", color: "#818cf8" }}>
                (Order #{orderId})
              </span>
            )}
          </div>
          <button className="audit-toggle-btn" type="button">
            {auditLoading ? "Refreshing..." : auditExpanded ? "▲ Collapse" : "▼ Expand"}
          </button>
        </div>

        {auditExpanded && (
          <div className="audit-body">
            {orderId && (
              <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "1rem" }}>
                <button
                  onClick={() => fetchAuditEvents(orderId)}
                  className="btn-reset"
                  style={{ marginTop: 0, padding: "0.35rem 0.75rem", fontSize: "0.75rem" }}
                  disabled={auditLoading}
                >
                  🔄 Refresh Trail
                </button>
              </div>
            )}

            {auditEvents.length === 0 ? (
              <div className="audit-empty">
                {orderId
                  ? "Loading audit trail for this order..."
                  : "Audit trail records will automatically appear here once an order ID is established."}
              </div>
            ) : (
              <div className="timeline">
                {auditEvents.map((item, index) => {
                  const eventTime = item.created_at || item.timestamp;
                  const timeFormatted = eventTime
                    ? new Date(eventTime).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                      })
                    : "";

                  return (
                    <div key={item.id || index} className="timeline-item">
                      <div className="timeline-dot" />
                      <div className="timeline-content">
                        <div className="timeline-meta">
                          <span className="timeline-event-badge">{item.event_type}</span>
                          <span className="timeline-time">{timeFormatted}</span>
                        </div>
                        <div className="timeline-actor">
                          Actor: <span>{item.actor}</span>
                        </div>
                        {item.reason && (
                          <div className="timeline-reason">{item.reason}</div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
