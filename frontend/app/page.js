"use client";

import { useState, useEffect, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const SAMPLE_QUERIES = [
  "Find me a mechanical keyboard under ₹3,000",
  "Recommend an ergonomic wireless mouse under ₹2,000",
  "Looking for noise cancelling gaming headphones",
];

// Helper to normalize spending limit from various backend API response shapes
function extractSpendingLimitInr(data) {
  if (data === null || data === undefined) return null;
  const raw = (typeof data === "object" && data.data && typeof data.data === "object")
    ? data.data
    : data;

  if (raw.spending_limit_inr !== undefined && raw.spending_limit_inr !== null) {
    const val = Number(raw.spending_limit_inr);
    if (!isNaN(val)) return val;
  }
  if (raw.limit_inr !== undefined && raw.limit_inr !== null) {
    const val = Number(raw.limit_inr);
    if (!isNaN(val)) return val;
  }
  if (raw.spending_limit_paise !== undefined && raw.spending_limit_paise !== null) {
    const val = Number(raw.spending_limit_paise);
    if (!isNaN(val)) return val / 100;
  }
  if (raw.limit_paise !== undefined && raw.limit_paise !== null) {
    const val = Number(raw.limit_paise);
    if (!isNaN(val)) return val / 100;
  }
  if (raw.limit !== undefined && raw.limit !== null) {
    const val = Number(raw.limit);
    if (!isNaN(val)) {
      return val > 100000 ? val / 100 : val;
    }
  }
  if (raw.spending_limit !== undefined && raw.spending_limit !== null) {
    const val = Number(raw.spending_limit);
    if (!isNaN(val)) {
      return val > 100000 ? val / 100 : val;
    }
  }
  if (typeof raw === "number") {
    return raw > 100000 ? raw / 100 : raw;
  }
  return null;
}

export default function ShoppingAgentDemo() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState("");
  const [threadId, setThreadId] = useState(null);
  const [orderId, setOrderId] = useState(null);
  const [requestId, setRequestId] = useState(null);
  const [activeAuditId, setActiveAuditId] = useState(null);

  // Flow states: 'idle' | 'pending_confirmation' | 'completed' | 'order_created' | 'blocked' | 'failed' | 'rejected'
  const [agentState, setAgentState] = useState("idle");
  const [pendingConfirmation, setPendingConfirmation] = useState(null);
  const [orderResult, setOrderResult] = useState(null);
  const [completedExplanation, setCompletedExplanation] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  // Spending Limit Policy Controls
  const [spendingLimit, setSpendingLimit] = useState(15000);
  const [limitSaved, setLimitSaved] = useState(false);

  // Audit trail
  const [auditEvents, setAuditEvents] = useState([]);
  const [auditExpanded, setAuditExpanded] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);

  // Load user's active spending limit from backend
  const loadSpendingLimit = useCallback(async () => {
    try {
      let res = await fetch(`${API_BASE}/accounts/limit/`);
      if (res.status === 404) {
        res = await fetch(`${API_BASE}/limit/`);
      }
      if (res.ok) {
        const data = await res.json();
        const parsedLimit = extractSpendingLimitInr(data);
        if (parsedLimit !== null && !isNaN(parsedLimit)) {
          setSpendingLimit(parsedLimit);
        }
      }
    } catch (err) {
      console.error("Failed to load spending limit:", err);
    }
  }, []);

  useEffect(() => {
    loadSpendingLimit();
  }, [loadSpendingLimit]);

  async function updateSpendingLimit(val) {
    const num = Number(val);
    if (isNaN(num) || num < 0) return;
    try {
      const payload = {
        spending_limit_inr: num,
        spending_limit_paise: Math.round(num * 100),
        limit: num,
        limit_paise: Math.round(num * 100),
      };
      let res = await fetch(`${API_BASE}/accounts/limit/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.status === 404) {
        res = await fetch(`${API_BASE}/limit/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      }
      if (res.ok) {
        const data = await res.json();
        const parsedLimit = extractSpendingLimitInr(data);
        if (parsedLimit !== null && !isNaN(parsedLimit)) {
          setSpendingLimit(parsedLimit);
        } else {
          setSpendingLimit(num);
        }
        setLimitSaved(true);
        setTimeout(() => setLimitSaved(false), 2000);
      }
    } catch (err) {
      console.error("Failed to update spending limit:", err);
    }
  }

  // Fetch audit trail for an order ID or request ID
  const fetchAuditEvents = useCallback(async (id) => {
    if (!id) return;
    setAuditLoading(true);
    try {
      const res = await fetch(`${API_BASE}/audit/${id}/`);
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

  // Poll/refresh audit trail if an active identifier exists
  useEffect(() => {
    if (activeAuditId) {
      fetchAuditEvents(activeAuditId);
    }
  }, [activeAuditId, fetchAuditEvents]);

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
    setRequestId(null);
    setActiveAuditId(null);

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
      if (data.request_id) {
        setRequestId(data.request_id);
        setActiveAuditId(data.request_id);
      }

      if (data.status === "pending_confirmation") {
        setPendingConfirmation(data.pending_confirmation);
        setAgentState("pending_confirmation");
      } else if (data.status === "completed") {
        setCompletedExplanation(data.explanation || "Request completed.");
        setOrderResult(data.order_result || null);
        setAgentState("completed");

        if (data.order_result?.id) {
          setOrderId(data.order_result.id);
          setActiveAuditId(data.order_result.id);
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
        ? "Processing purchase & evaluating policy controls..."
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
      const currentReqId = data.request_id || requestId;
      if (currentReqId) {
        setRequestId(currentReqId);
      }

      if (!approved || data.status === "rejected") {
        setAgentState("rejected");
        const auditTarget = currentReqId;
        if (auditTarget) {
          setActiveAuditId(auditTarget);
          fetchAuditEvents(auditTarget);
          setAuditExpanded(true);
        }
        return;
      }

      const result = data.order_result || {};
      setOrderResult(result);

      // 1. Check if policy gate BLOCKED the order
      if (data.status === "blocked" || result.status === "blocked") {
        setAgentState("blocked");
        setErrorMessage(
          result.reason || data.reason || "Order exceeds configured spending limits or category constraints."
        );
        const auditTarget = result.id || currentReqId;
        if (auditTarget) {
          setActiveAuditId(auditTarget);
          fetchAuditEvents(auditTarget);
          setAuditExpanded(true);
        }
        return;
      }

      // 2. Check if order failed (e.g. gateway timeout)
      if (data.status === "failed" || result.status === "failed") {
        setAgentState("failed");
        setErrorMessage(
          result.detail ||
            "The payment service encountered a temporary timeout. No funds were debited."
        );
        const auditTarget = result.id || currentReqId;
        if (auditTarget) {
          setActiveAuditId(auditTarget);
          fetchAuditEvents(auditTarget);
          setAuditExpanded(true);
        }
        return;
      }

      // 3. Normal Order Placed
      if (data.status === "order_created" && result.id) {
        setOrderId(result.id);
        setActiveAuditId(result.id);
        setAgentState("order_created");
        fetchAuditEvents(result.id);
        setAuditExpanded(true);
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
    setOrderId(null);
    setRequestId(null);
    setActiveAuditId(null);
    setAuditEvents([]);
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

      {/* Interactive Spending Limit Policy Bar */}
      {spendingLimit !== null && spendingLimit !== undefined && (
        <div className="policy-bar">
          <div className="policy-bar-left">
            <span className="policy-bar-icon">🛡️</span>
            <div>
              <div className="policy-bar-title">Active Spending Limit Policy</div>
              <div className="policy-bar-desc">Pre-order policy gate will automatically block purchases exceeding this amount</div>
            </div>
          </div>

          <div className="policy-bar-right">
            <div className="limit-input-wrap">
              <span className="currency-prefix">₹</span>
              <input
                type="number"
                className="limit-input"
                value={spendingLimit}
                onChange={(e) => setSpendingLimit(e.target.value)}
                onBlur={() => updateSpendingLimit(spendingLimit)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") updateSpendingLimit(spendingLimit);
                }}
                min="100"
                step="500"
                title="Click or enter new spending limit and press Enter"
              />
            </div>

            <div className="preset-chips">
              {[3000, 5000, 15000, 50000].map((preset) => (
                <button
                  key={preset}
                  type="button"
                  className={`preset-chip ${Number(spendingLimit) === preset ? "preset-chip-active" : ""}`}
                  onClick={() => {
                    setSpendingLimit(preset);
                    updateSpendingLimit(preset);
                  }}
                >
                  ₹{preset >= 1000 ? `${preset / 1000}k` : preset}
                </button>
              ))}
            </div>

            {limitSaved && <span className="limit-saved-tag">Saved ✓</span>}
          </div>
        </div>
      )}

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

      {/* Order Created State (Green Success — Only when confirmed) */}
      {agentState === "order_created" && orderResult && orderResult.status === "confirmed" && (
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

      {/* Policy Blocked State (Amber/Red Shield Container) */}
      {agentState === "blocked" && (
        <section className="state-box state-warning" style={{ border: "1px solid #f59e0b", background: "linear-gradient(180deg, #2c1404 0%, #150a02 100%)" }}>
          <div className="state-title-row">
            <span className="state-icon">🛡️</span>
            <div>
              <h2 className="state-title" style={{ color: "#fbbf24" }}>Order Blocked by Policy Gate</h2>
              <span style={{ fontSize: "0.75rem", color: "#fef08a", fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase" }}>
                Pre-Order Risk Enforcement
              </span>
            </div>
          </div>

          <div style={{ background: "rgba(0, 0, 0, 0.45)", border: "1px solid rgba(245, 158, 11, 0.4)", borderRadius: "12px", padding: "1.15rem" }}>
            <div style={{ fontSize: "0.75rem", textTransform: "uppercase", color: "#fde68a", fontWeight: 700, marginBottom: "0.35rem" }}>
              Policy Violation Reason
            </div>
            <p style={{ fontSize: "1.05rem", color: "#fff", fontWeight: 600, lineHeight: 1.4 }}>
              {errorMessage || orderResult?.reason || "Order total exceeds configured spending limits."}
            </p>
          </div>

          <p style={{ fontSize: "0.9rem", color: "#cbd5e1", lineHeight: 1.5 }}>
            The autonomous shopping agent halted the transaction before submitting it to the payment gateway. No funds were debited and no order was created.
          </p>

          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
            <button onClick={handleReset} className="btn-reset" style={{ borderColor: "#f59e0b", color: "#fef3c7" }}>
              ← Search for Another Product
            </button>
            <button
              onClick={() => {
                setAuditExpanded(true);
                if (activeAuditId) fetchAuditEvents(activeAuditId);
              }}
              className="btn-reset"
              style={{ borderColor: "#6366f1", color: "#c7d2fe" }}
            >
              🛡️ View Policy Decision in Audit Trail
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
            {orderId ? (
              <span style={{ fontSize: "0.8rem", color: "#818cf8" }}>
                (Order #{orderId})
              </span>
            ) : requestId ? (
              <span style={{ fontSize: "0.8rem", color: "#f59e0b" }}>
                (Risk & Policy Trail)
              </span>
            ) : null}
          </div>
          <button className="audit-toggle-btn" type="button">
            {auditLoading ? "Refreshing..." : auditExpanded ? "▲ Collapse" : "▼ Expand"}
          </button>
        </div>

        {auditExpanded && (
          <div className="audit-body">
            {activeAuditId && (
              <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "1rem" }}>
                <button
                  onClick={() => fetchAuditEvents(activeAuditId)}
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
                {activeAuditId
                  ? "Loading audit trail for this transaction..."
                  : "Audit trail records will automatically appear here once agent actions begin."}
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

                  const isPolicyChecked = item.event_type === "policy_checked";
                  const decision = isPolicyChecked
                    ? (item.payload?.decision || item.decision || (typeof item.reason === "string" && item.reason.toLowerCase().includes("block") ? "BLOCK" : "ALLOW"))
                    : null;

                  let dotStyle = undefined;
                  let badgeStyle = undefined;
                  let reasonStyle = undefined;
                  let decisionIcon = null;
                  let decisionLabel = null;

                  if (isPolicyChecked) {
                    if (decision === "BLOCK") {
                      dotStyle = { background: "#ef4444", boxShadow: "0 0 8px #ef4444" };
                      badgeStyle = { background: "rgba(239, 68, 68, 0.2)", color: "#fca5a5", border: "1px solid rgba(239, 68, 68, 0.4)" };
                      reasonStyle = { background: "rgba(239, 68, 68, 0.15)", color: "#fca5a5", border: "1px solid rgba(239, 68, 68, 0.3)" };
                      decisionIcon = "🚫";
                      decisionLabel = "Blocked";
                    } else if (decision === "NEEDS_APPROVAL") {
                      dotStyle = { background: "#f59e0b", boxShadow: "0 0 8px #f59e0b" };
                      badgeStyle = { background: "rgba(245, 158, 11, 0.2)", color: "#fcd34d", border: "1px solid rgba(245, 158, 11, 0.4)" };
                      reasonStyle = { background: "rgba(245, 158, 11, 0.15)", color: "#fcd34d", border: "1px solid rgba(245, 158, 11, 0.3)" };
                      decisionIcon = "⚠️";
                      decisionLabel = "Needs Approval";
                    } else if (decision === "ALLOW") {
                      dotStyle = { background: "#10b981", boxShadow: "0 0 8px #10b981" };
                      badgeStyle = { background: "rgba(16, 185, 129, 0.2)", color: "#6ee7b7", border: "1px solid rgba(16, 185, 129, 0.4)" };
                      reasonStyle = { background: "rgba(16, 185, 129, 0.12)", color: "#a7f3d0", border: "1px solid rgba(16, 185, 129, 0.25)" };
                      decisionIcon = "✅";
                      decisionLabel = "Passed";
                    }
                  } else {
                    reasonStyle = { background: "rgba(148, 163, 184, 0.1)", color: "#cbd5e1", border: "1px solid rgba(148, 163, 184, 0.2)" };
                  }

                  const reasonText = item.reason || item.payload?.reason || item.payload?.detail;

                  return (
                    <div key={item.id || index} className="timeline-item">
                      <div
                        className="timeline-dot"
                        style={dotStyle}
                      />
                      <div className="timeline-content">
                        <div className="timeline-meta">
                          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                            <span
                              className="timeline-event-badge"
                              style={badgeStyle}
                            >
                              {item.event_type}
                            </span>
                            {isPolicyChecked && decisionLabel && (
                              <span
                                style={{
                                  display: "inline-flex",
                                  alignItems: "center",
                                  gap: "0.25rem",
                                  fontSize: "0.75rem",
                                  fontWeight: 700,
                                  padding: "0.15rem 0.5rem",
                                  borderRadius: "6px",
                                  ...badgeStyle,
                                }}
                              >
                                <span>{decisionIcon}</span>
                                <span>{decisionLabel}</span>
                              </span>
                            )}
                          </div>
                          <span className="timeline-time">{timeFormatted}</span>
                        </div>
                        <div className="timeline-actor">
                          Actor: <span>{item.actor}</span>
                        </div>
                        {reasonText && (
                          <div
                            className="timeline-reason"
                            style={{
                              marginTop: "0.4rem",
                              padding: "0.35rem 0.6rem",
                              borderRadius: "6px",
                              fontSize: "0.8rem",
                              lineHeight: 1.5,
                              ...reasonStyle,
                            }}
                          >
                            {isPolicyChecked && decisionLabel ? (
                              <>
                                <strong>{decisionIcon} {decisionLabel}: </strong>
                                <span>{reasonText}</span>
                              </>
                            ) : (
                              reasonText
                            )}
                          </div>
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
