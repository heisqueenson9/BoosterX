import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AdminOverviewStats, AdminAuditLogItem } from "../api/types";
import { Button, Card, Field, Icon, PageTitle, Status, type IconName } from "../App";

export function AdminDashboard({ go }: { go: (page: string) => void }) {
  const [overview, setOverview] = useState<AdminOverviewStats | null>(null);
  const [connResult, setConnResult] = useState<string | null>(null);

  useEffect(() => {
    api.getAdminOverview().then(setOverview).catch(() => {});
  }, []);

  const handleTestConnection = async () => {
    try {
      const res = await api.testAdminProviderConnection();
      if (res.connected) {
        setConnResult(`Status: Connected | Balance: ${res.balance} ${res.currency} | Active Services: ${res.service_count}`);
      } else {
        setConnResult(`Connection Failed: ${res.error || "Unknown error"}`);
      }
    } catch (err: any) {
      setConnResult(`Test Failed: ${err.message || "Network error"}`);
    }
  };

  const handleCheckBalance = async () => {
    try {
      const res = await api.getAdminProviderBalance();
      setConnResult(`Provider Balance: ${res.balance} ${res.currency}`);
    } catch (err: any) {
      setConnResult(`Balance Check Failed: ${err.message || "Network error"}`);
    }
  };

  return (
    <div className="admin-page">
      <PageTitle title="Admin Overview" description="Live platform performance and operational health." />

      <div className="stats admin-stats">
        {[
          ["24h Revenue", `GHS ${overview?.revenue_24h_ghs || "0.00"}`, "wallet"],
          ["Active Orders", (overview?.active_orders || 0).toString(), "orders"],
          ["Pending Payment Reviews", (overview?.pending_payment_reviews || 0).toString(), "card"],
          ["Total Registered Users", (overview?.total_users || 0).toString(), "users"],
          ["Failed Orders", (overview?.failed_orders || 0).toString(), "close"],
          ["Total System Orders", (overview?.total_orders || 0).toString(), "chart"],
          ["Provider Balance", overview?.provider_balance || "Loading...", "wallet"],
          ["Provider Connection", overview?.provider_connection_status || "Checking...", "shield"],
          ["Active Services", (overview?.active_services_count || 0).toString(), "services"],
          ["Last Catalog Sync", overview?.last_sync_timestamp && overview.last_sync_timestamp !== "Never" ? new Date(overview.last_sync_timestamp).toLocaleString() : "Never", "clock"]
        ].map(([label, val, icon]) => (
          <Card className="stat" key={label}>
            <div className="stat-head">
              <span>{label}</span>
              <div className="icon-tile"><Icon name={icon as IconName} /></div>
            </div>
            <strong>{val}</strong>
            <small>Updated live</small>
          </Card>
        ))}
      </div>

      {connResult && (
        <Card>
          <p className="payment-warning"><strong>Provider Diagnostic:</strong> {connResult}</p>
        </Card>
      )}

      <Card>
        <div className="card-head">
          <div>
            <span className="eyebrow">Control Center</span>
            <h2>Quick Actions & Provider API Controls</h2>
          </div>
        </div>
        <div className="admin-order-actions">
          <Button variant="primary" icon="card" onClick={() => go("admin-payments")}>Review Payments ({overview?.pending_payment_reviews || 0})</Button>
          <Button variant="secondary" icon="orders" onClick={() => go("admin-orders")}>Manage Orders ({overview?.active_orders || 0} active)</Button>
          <Button variant="secondary" icon="services" onClick={() => go("admin-services")}>Service Catalog</Button>
          <Button variant="secondary" icon="shield" onClick={handleTestConnection}>Test API Connection</Button>
          <Button variant="secondary" icon="wallet" onClick={handleCheckBalance}>Check Balance</Button>
          <Button variant="secondary" icon="clock" onClick={() => go("admin-audit")}>Audit Logs</Button>
        </div>
      </Card>
    </div>
  );
}

export function AdminPayments({ go }: { go: (page: string) => void }) {
  const [payments, setPayments] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getAdminPayments().then(res => {
      setPayments(res.payments);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  return (
    <div className="admin-page">
      <PageTitle title="Payment Reviews" description="Review AI-verified payments and resolve exceptions." />

      <Card>
        {loading ? <p>Loading payments...</p> : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Payment ID</th>
                  <th>Amount</th>
                  <th>Network</th>
                  <th>Status</th>
                  <th>Reference</th>
                  <th>Created</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {payments.map(p => (
                  <tr key={p.payment_id}>
                    <td><strong>{p.payment_id}</strong></td>
                    <td>GHS {p.amount_ghs}</td>
                    <td>{p.network}</td>
                    <td><Status>{p.status}</Status></td>
                    <td>{p.reference || "N/A"}</td>
                    <td>{new Date(p.created_at).toLocaleString()}</td>
                    <td>
                      <Button variant="secondary" icon="eye" onClick={() => go(`admin-payment-review?id=${p.payment_id}`)}>
                        Review
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

export function AdminPaymentReview({ go }: { go: (page: string) => void }) {
  const [payment, setPayment] = useState<any | null>(null);
  const [reference, setReference] = useState("");
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState("");
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(location.hash.split("?")[1] || "");
    const id = params.get("id");
    if (id) {
      api.getAdminPayments({ search: id }).then(res => {
        if (res.payments.length > 0) setPayment(res.payments[0]);
      }).catch(() => {});
    }
  }, []);

  const handleApprove = async () => {
    if (!payment) return;
    try {
      const res = await api.adminVerifyPayment(payment.payment_id, reference || undefined);
      setMsg(res.message);
    } catch (err: any) {
      setMsg(err.message || "Failed to approve payment");
    }
  };

  const handleReject = async () => {
    if (!payment) return;
    try {
      const res = await api.adminRejectPayment(payment.payment_id, reason || undefined);
      setMsg(res.message);
    } catch (err: any) {
      setMsg(err.message || "Failed to reject payment");
    }
  };

  if (!payment) return <Card><p>Loading payment details...</p></Card>;

  return (
    <div className="admin-page">
      <Button variant="ghost" icon="arrow" onClick={() => go("admin-payments")}>Back to payments</Button>
      <PageTitle
        title={`Review Payment ${payment.payment_id}`}
        description={`Amount: GHS ${payment.amount_ghs} · Network: ${payment.network}`}
        action={<Status>{payment.status}</Status>}
      />

      <div className="payment-review-grid">
        <Card>
          <h2>Payment Details</h2>
          <dl className="detail-list">
            <div><dt>Payment ID</dt><dd>{payment.payment_id}</dd></div>
            <div><dt>Amount</dt><dd>GHS {payment.amount_ghs}</dd></div>
            <div><dt>Detected Amount</dt><dd>{payment.detected_amount_ghs ? `GHS ${payment.detected_amount_ghs}` : "N/A"}</dd></div>
            <div><dt>Network</dt><dd>{payment.network}</dd></div>
            <div><dt>Reference</dt><dd>{payment.reference || "N/A"}</dd></div>
            <div><dt>Status</dt><dd><Status>{payment.status}</Status></dd></div>
            {payment.rejection_reason && (
              <div><dt>Rejection Reason</dt><dd style={{ color: "#f87171" }}>{payment.rejection_reason}</dd></div>
            )}
          </dl>
          {payment.screenshot_filename && (
            <div style={{ marginTop: "1rem" }}>
              <Button variant="secondary" icon="eye" onClick={() => setShowModal(true)}>View Payment Screenshot</Button>
            </div>
          )}
        </Card>

        <Card>
          <h2>Admin Decision</h2>
          <Field label="Override Reference (optional)" value={reference} onChange={setReference} placeholder="MANUAL-REF-123" />
          <Field label="Rejection Reason (optional)" value={reason} onChange={setReason} placeholder="Unclear screenshot" />
          {msg && <div className="payment-warning"><strong>{msg}</strong></div>}
          <div className="admin-order-actions">
            <Button variant="primary" icon="check" onClick={handleApprove}>Approve & Credit</Button>
            <Button variant="secondary" icon="close" onClick={handleReject}>Reject Payment</Button>
          </div>
        </Card>
      </div>

      {showModal && (
        <div style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.75)", zIndex: 9999, display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem" }} onClick={() => setShowModal(false)}>
          <div style={{ background: "var(--surface-1, #1e293b)", padding: "1.5rem", borderRadius: "12px", maxWidth: "90vw", maxHeight: "90vh", overflow: "auto", position: "relative", color: "#fff" }} onClick={e => e.stopPropagation()}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
              <h3 style={{ margin: 0 }}>Payment Screenshot ({payment.payment_id})</h3>
              <Button variant="ghost" icon="close" onClick={() => setShowModal(false)}>Close</Button>
            </div>
            <img
              src={`/api/admin/payments/${encodeURIComponent(payment.payment_id)}/screenshot`}
              alt="Payment Evidence Screenshot"
              style={{ maxWidth: "100%", maxHeight: "70vh", borderRadius: "8px", objectFit: "contain" }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

export function AdminOrders() {
  const [orders, setOrders] = useState<any[]>([]);

  useEffect(() => {
    api.getAdminOrders().then(res => setOrders(res.orders)).catch(() => {});
  }, []);

  const handleAction = async (publicId: string, action: string) => {
    try {
      await api.adminOrderAction(publicId, action);
      const res = await api.getAdminOrders();
      setOrders(res.orders);
    } catch (err: any) {
      alert(err.message || "Action failed");
    }
  };

  return (
    <div className="admin-page">
      <PageTitle title="Order Management" description="Track fulfillment status and resolve order issues." />

      <Card>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Order ID</th>
                <th>Platform</th>
                <th>Service</th>
                <th>Target</th>
                <th>Status</th>
                <th>Attention</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {orders.map(o => (
                <tr key={o.public_order_id}>
                  <td><strong>{o.public_order_id}</strong></td>
                  <td>{o.platform}</td>
                  <td>{o.service_name}</td>
                  <td>{o.target}</td>
                  <td><Status>{o.status}</Status></td>
                  <td>{o.needs_attention ? <Status>Rejected</Status> : "Normal"}</td>
                  <td>
                    <div className="admin-order-actions">
                      {o.needs_attention && <Button variant="secondary" icon="check" onClick={() => handleAction(o.public_order_id, "clear-attention")}>Clear Flag</Button>}
                      <Button variant="secondary" icon="plus" onClick={() => handleAction(o.public_order_id, "mark-submitted")}>Mark Submitted</Button>
                      <Button variant="ghost" icon="close" onClick={() => handleAction(o.public_order_id, "cancel")}>Cancel</Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

export function AdminServices() {
  const [services, setServices] = useState<any[]>([]);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  useEffect(() => {
    api.getAdminServices().then(res => setServices(res.services)).catch(err => alert(err.message || "Failed to load admin services."));
  }, []);

  const toggleService = async (id: number, currentEnabled: boolean) => {
    try {
      await api.updateAdminService(id, { enabled: !currentEnabled });
      const res = await api.getAdminServices();
      setServices(res.services);
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleSync = async () => {
    try {
      const resSync = await api.syncAdminServices();
      const res = await api.getAdminServices();
      setServices(res.services);
      setStatusMsg(`Catalog Synced: ${resSync.added || 0} added, ${resSync.updated || 0} updated, ${resSync.deactivated || 0} deactivated.`);
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleTestConnection = async () => {
    try {
      const res = await api.testAdminProviderConnection();
      if (res.connected) {
        setStatusMsg(`Status: Connected | Balance: ${res.balance} ${res.currency} | Active Services: ${res.service_count}`);
      } else {
        setStatusMsg(`Connection Failed: ${res.error || "Unknown error"}`);
      }
    } catch (err: any) {
      setStatusMsg(`Test Failed: ${err.message || "Network error"}`);
    }
  };

  return (
    <div className="admin-page">
      <PageTitle
        title="Services Catalog"
        description="Control service availability and provider rates."
        action={
          <div style={{ display: "flex", gap: "8px" }}>
            <Button variant="secondary" icon="shield" onClick={handleTestConnection}>Test Connection</Button>
            <Button variant="primary" icon="transactions" onClick={handleSync}>REFRESH SERVICES</Button>
          </div>
        }
      />

      {statusMsg && (
        <Card>
          <p className="payment-warning"><strong>Catalog Diagnostic:</strong> {statusMsg}</p>
        </Card>
      )}

      <Card>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Platform</th>
                <th>Service Name</th>
                <th>Rate (USD / 1k)</th>
                <th>Min/Max</th>
                <th>Refill</th>
                <th>Enabled</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {services.map(s => (
                <tr key={s.id}>
                  <td>{s.id}</td>
                  <td>{s.platform}</td>
                  <td><strong>{s.name}</strong></td>
                  <td>${s.rate_usd_per_1000}</td>
                  <td>{s.min_qty} / {s.max_qty.toLocaleString()}</td>
                  <td>{s.refill_available ? "Yes" : "No"}</td>
                  <td><Status>{s.enabled ? "Completed" : "Cancelled"}</Status></td>
                  <td>
                    <Button variant="secondary" onClick={() => toggleService(s.id, s.enabled)}>
                      {s.enabled ? "Disable" : "Enable"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

export function AdminPlatforms() {
  const [platforms, setPlatforms] = useState<any[]>([]);

  useEffect(() => {
    api.getAdminPlatforms().then(res => setPlatforms(res.platforms)).catch(() => {});
  }, []);

  const togglePlatform = async (id: number, currentActive: boolean) => {
    try {
      await api.updateAdminPlatform(id, !currentActive);
      const res = await api.getAdminPlatforms();
      setPlatforms(res.platforms);
    } catch (err: any) {
      alert(err.message);
    }
  };

  return (
    <div className="admin-page">
      <PageTitle title="Platforms" description="Manage active social platforms on BoostX." />

      <div className="platform-admin-grid">
        {platforms.map(p => (
          <Card key={p.id}>
            <h2>{p.name}</h2>
            <p>Status: <Status>{p.active ? "Completed" : "Cancelled"}</Status></p>
            <div className="admin-order-actions">
              <Button variant="secondary" onClick={() => togglePlatform(p.id, p.active)}>
                {p.active ? "Disable Platform" : "Enable Platform"}
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

export function AdminConfigPage({ type }: { type: string }) {
  const [auditLogs, setAuditLogs] = useState<AdminAuditLogItem[]>([]);
  const [health, setHealth] = useState<any>(null);
  const [rate, setRate] = useState("10.70");
  const [markup, setMarkup] = useState("5.00");
  const [msg, setMsg] = useState("");

  const [healthLoading, setHealthLoading] = useState(false);

  const fetchHealth = () => {
    setHealthLoading(true);
    api.getAdminHealth()
      .then(setHealth)
      .catch(() => {})
      .finally(() => setHealthLoading(false));
  };

  useEffect(() => {
    if (type === "audit") {
      api.getAdminAuditLogs().then(res => setAuditLogs(res.audit_logs)).catch(() => {});
    } else if (type === "health") {
      fetchHealth();
      const interval = setInterval(fetchHealth, 30000);
      return () => clearInterval(interval);
    } else if (type === "pricing") {
      api.getAdminPricing().then(res => {
        setRate(res.usd_to_ghs_rate);
        setMarkup(res.flat_markup_ghs);
      }).catch(() => {});
    }
  }, [type]);

  const handleUpdatePricing = async () => {
    try {
      const res = await api.updateAdminPricing(rate, markup);
      setMsg(res.message);
    } catch (err: any) {
      setMsg(err.message);
    }
  };

  if (type === "audit") {
    return (
      <div className="admin-page">
        <PageTitle title="Audit Logs" description="Immutable record of administrator actions." />

        <Card>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Admin ID</th>
                  <th>Action</th>
                  <th>Target Type</th>
                  <th>Target ID</th>
                  <th>Old Value</th>
                  <th>New Value</th>
                  <th>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {auditLogs.map(l => (
                  <tr key={l.id}>
                    <td>Admin #{l.admin_id}</td>
                    <td><strong>{l.action}</strong></td>
                    <td>{l.target_type}</td>
                    <td>{l.target_id}</td>
                    <td>{l.old_value || "—"}</td>
                    <td>{l.new_value || "—"}</td>
                    <td>{new Date(l.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    );
  }

  if (type === "health") {
    const provHealth = health?.provider || {};
    const isConn = provHealth.status === "CONNECTED";
    const isDegraded = provHealth.status === "DEGRADED";
    const isNotConfig = provHealth.status === "NOT_CONFIGURED";
    
    const statusLabel = isConn ? "Connected" : (
      isDegraded ? "Degraded" : (
        isNotConfig ? "Not Configured" : (
          provHealth.status === "DISCONNECTED" ? "Disconnected" : "Error"
        )
      )
    );

    const overallStatusLabel = health?.status === "HEALTHY" ? "Healthy" : (
      health?.status === "DEGRADED" ? "Degraded" : "Error"
    );

    return (
      <div className="admin-page">
        <PageTitle
          title="System Health"
          description="Live status of database and SMM Africa provider services."
          action={
            <Button
              variant="secondary"
              icon="clock"
              onClick={fetchHealth}
              disabled={healthLoading}
            >
              {healthLoading ? "Checking..." : "Refresh Health"}
            </Button>
          }
        />

        <Card>
          <div className="card-head">
            <div>
              <span className="eyebrow">Overall System Health</span>
              <h2>Status: <Status>{overallStatusLabel}</Status></h2>
            </div>
          </div>
          <dl className="detail-list">
            <div>
              <dt>Database Service</dt>
              <dd><Status>{health?.database?.status === "CONNECTED" || health?.database?.status === "ok" ? "Connected" : "Error"}</Status></dd>
            </div>
            <div>
              <dt>Provider Name</dt>
              <dd><strong>{provHealth.provider || "SMM Africa"}</strong></dd>
            </div>
            <div>
              <dt>Provider API Connection</dt>
              <dd><Status>{statusLabel}</Status></dd>
            </div>
            <div>
              <dt>API Reachability</dt>
              <dd><Status>{provHealth.apiReachable ? "Online" : "Offline"}</Status></dd>
            </div>
            <div>
              <dt>Authentication Status</dt>
              <dd><Status>{provHealth.authenticated ? "Valid" : (isNotConfig ? "Not Configured" : "Invalid")}</Status></dd>
            </div>
            <div>
              <dt>Services Catalog Sync</dt>
              <dd><Status>{provHealth.servicesSync || "Healthy"}</Status></dd>
            </div>
            <div>
              <dt>Provider Balance</dt>
              <dd><strong>{provHealth.providerBalance || "Unable to Check"}</strong></dd>
            </div>
            <div>
              <dt>Last Checked</dt>
              <dd>{provHealth.lastChecked ? new Date(provHealth.lastChecked).toLocaleString() : (health?.timestamp ? new Date(health.timestamp).toLocaleString() : "N/A")}</dd>
            </div>
          </dl>

          {provHealth.reason && (
            <div className="payment-warning" style={{ marginTop: "16px" }}>
              <strong>Health Diagnostic:</strong> {provHealth.reason}
            </div>
          )}
        </Card>
      </div>
    );
  }

  if (type === "pricing") {
    return (
      <div className="admin-page">
        <PageTitle title="Pricing Configuration" description="Set exchange rates and flat markups for customer prices." />

        <Card className="admin-settings-card">
          <Field label="USD to GHS Exchange Rate" value={rate} onChange={setRate} placeholder="10.70" />
          <Field label="Flat Processing Fee Markup (GHS)" value={markup} onChange={setMarkup} placeholder="5.00" />
          {msg && <div className="payment-warning"><strong>{msg}</strong></div>}
          <div className="admin-order-actions">
            <Button variant="primary" icon="check" onClick={handleUpdatePricing}>
              Save Pricing Settings
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <PageTitle title={`Admin Settings (${type})`} description="System configuration panel." />
      <Card>
        <p>Admin configuration page for {type}.</p>
      </Card>
    </div>
  );
}
