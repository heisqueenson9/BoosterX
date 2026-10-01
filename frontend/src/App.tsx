import { useEffect, useMemo, useState, lazy, Suspense, type ReactNode } from "react";
import logo from "./imports/boosterx-logo-rocket.svg";
import { api, setCsrfToken } from "./api/client";
import type { OrderDetail, ServiceItem, PaymentItem, WalletSummary, LedgerTxItem, UserInfo } from "./api/types";
import { TrackOrderPage } from "./components/TrackOrder";
import { HelpFAQPage } from "./components/HelpFAQ";
import { LegalPage } from "./components/LegalPages";
import { NotFoundPage } from "./components/NotFound";

type IconName =
  | "home" | "plus" | "orders" | "services" | "wallet" | "transactions"
  | "support" | "user" | "settings" | "search" | "bell" | "sun"
  | "moon" | "menu" | "close" | "arrow" | "copy" | "logout" | "check"
  | "clock" | "eye" | "users" | "chart" | "card" | "shield";

const paths: Record<IconName, ReactNode> = {
  home: <><path d="m3 10 9-7 9 7"/><path d="M5 9v11h14V9M9 20v-6h6v6"/></>,
  plus: <><path d="M12 5v14M5 12h14"/></>,
  orders: <><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></>,
  services: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  wallet: <><path d="M4 6h14a2 2 0 0 1 2 2v11H4a2 2 0 0 1-2-2V6.5A2.5 2.5 0 0 1 4.5 4H17"/><path d="M15 12h5v4h-5a2 2 0 0 1 0-4Z"/></>,
  transactions: <><path d="m7 7 3-3 3 3M10 4v12M17 17l-3 3-3-3M14 20V8"/></>,
  support: <><circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.6 2.6 0 1 1 4.2 2c-1 .7-1.7 1.2-1.7 2.5M12 17h.01"/></>,
  user: <><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/></>,
  search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></>,
  sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></>,
  moon: <path d="M20 15.2A8 8 0 0 1 8.8 4a8 8 0 1 0 11.2 11.2Z"/>,
  menu: <path d="M4 6h16M4 12h16M4 18h16"/>,
  close: <path d="m6 6 12 12M18 6 6 18"/>,
  arrow: <path d="m9 18 6-6-6-6"/>,
  copy: <><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></>,
  logout: <><path d="M10 17l5-5-5-5M15 12H3M15 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4"/></>,
  check: <path d="m5 12 4 4L19 6"/>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  eye: <><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="2.5"/></>,
  users: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/></>,
  chart: <><path d="M4 19V9M10 19V5M16 19v-7M22 19V2"/><path d="M2 19h22"/></>,
  card: <><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/></>,
  shield: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/></>,
};

export type { IconName };

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

export function SocialIcon({ platform }: { platform: string }) {
  const filename = platform.toLowerCase();
  return <span className="platform-mark"><img src={`/social/${filename}.svg`} alt="" /></span>;
}

export function Button({ children, variant = "primary", icon, onClick, type = "button", disabled, full }: { children: ReactNode; variant?: "primary" | "secondary" | "ghost"; icon?: IconName; onClick?: () => void; type?: "button" | "submit"; disabled?: boolean; full?: boolean }) {
  return <button type={type} disabled={disabled} onClick={onClick} className={`btn ${variant} ${full ? "full" : ""}`}>{icon && <Icon name={icon} />}{children}</button>;
}

export function Field({ label, placeholder, value, type = "text", onChange }: { label?: string; placeholder?: string; value?: string; type?: string; onChange?: (value: string) => void }) {
  return <label className="field">{label && <span>{label}</span>}<input type={type} placeholder={placeholder} value={value || ""} onChange={(e) => onChange?.(e.target.value)} /></label>;
}

export function SelectField({ label, value, children, onChange }: { label?: string; value?: string; children: ReactNode; onChange?: (value: string) => void }) {
  return <label className="field">{label && <span>{label}</span>}<select value={value} onChange={(e) => onChange?.(e.target.value)}>{children}</select></label>;
}

export function PageTitle({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return <div className="page-title"><div><h1>{title}</h1>{description && <p>{description}</p>}</div>{action}</div>;
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`card ${className}`}>{children}</section>;
}

export function Status({ children }: { children: ReactNode }) { return <span className={`status ${String(children).toLowerCase()}`}>{children}</span>; }

const navGroups = [
  { label: "Main", links: [["dashboard", "Dashboard", "home"], ["new-order", "New Order", "plus"], ["orders", "My Orders", "orders"], ["services", "Services", "services"]] },
  { label: "Finance", links: [["wallet", "Wallet", "wallet"], ["transactions", "Transactions", "transactions"], ["payment", "Payment History", "card"]] },
  { label: "Help", links: [["support", "Support", "support"], ["track", "Track Order", "search"], ["help", "FAQ", "support"]] },
  { label: "Account", links: [["profile", "Profile", "user"], ["settings", "Settings", "settings"]] },
] as const;

function OrderTable({ orders, onView }: { orders: OrderDetail[]; onView: (id: string) => void }) {
  return <div className="table-wrap"><table><thead><tr><th>Order ID</th><th>Platform</th><th>Service</th><th>Quantity</th><th>Price</th><th>Status</th><th>Date</th><th></th></tr></thead><tbody>
    {orders.map((order) => <tr key={order.public_order_id}><td><strong>{order.public_order_id}</strong></td><td>{order.platform}</td><td>{order.service_name}</td><td>{order.quantity.toLocaleString()}</td><td>GHS {order.charge_ghs}</td><td><Status>{order.status}</Status></td><td>{new Date(order.created_at).toLocaleDateString()}</td><td><button className="icon-btn" onClick={() => onView(order.public_order_id)} aria-label={`View ${order.public_order_id}`}><Icon name="arrow" /></button></td></tr>)}
  </tbody></table></div>;
}

function Dashboard({ go, user }: { go: (page: string) => void; user: UserInfo | null }) {
  const [wallet, setWallet] = useState<WalletSummary>({ available_balance: "0.00", total_spent: "0.00", total_deposited: "0.00" });
  const [recentOrders, setRecentOrders] = useState<OrderDetail[]>([]);

  useEffect(() => {
    api.getAccountWallet().then(setWallet).catch(() => {});
    api.getAccountOrders({ per_page: 5 }).then(res => setRecentOrders(res.orders)).catch(() => {});
  }, []);

  const stats = [
    ["Total Orders", recentOrders.length.toString(), "Account orders", "orders"],
    ["Completed Orders", recentOrders.filter(o => o.status === "Completed").length.toString(), "Delivered", "check"],
    ["Pending Orders", recentOrders.filter(o => o.status === "Pending" || o.status === "Processing").length.toString(), "In progress", "clock"],
    ["Wallet Balance", `GHS ${wallet.available_balance}`, "Available to spend", "wallet"],
  ] as const;

  const displayName = user?.full_name || (user?.email ? user.email.split("@")[0] : "Guest");

  return <><PageTitle title={`Welcome back, ${displayName}`} description="Manage your orders and social media growth from one place." action={<Button icon="plus" onClick={() => go("new-order")}>Create New Order</Button>} />
    <div className="stats">{stats.map(([label, value, note, icon]) => <Card className="stat" key={label}><div className="stat-head"><span>{label}</span><span className="icon-tile"><Icon name={icon} /></span></div><strong>{value}</strong><small>{note}</small></Card>)}</div>
    <div className="dashboard-grid">
      <Card className="chart-card"><div className="card-head"><div><span className="eyebrow">Order activity</span><h2>Growth overview</h2></div><div className="segmented"><button className="active">30D</button></div></div>
        <div className="chart-legend"><span><i className="dot primary"/>Completed</span><span><i className="dot secondary"/>Placed</span></div>
        <div className="chart"><svg viewBox="0 0 700 230" preserveAspectRatio="none"><g className="grid"><path d="M0 20H700M0 72H700M0 124H700M0 176H700M0 228H700"/></g><path className="line-secondary" d="M0 190 C70 160 90 180 150 145 S250 125 300 145 S390 70 450 105 S540 40 600 70 S660 24 700 35"/><path className="line-primary" d="M0 208 C55 195 105 155 150 175 S250 100 310 120 S380 92 440 76 S530 82 590 42 S660 58 700 18"/></svg><div className="x-axis"><span>1 Sep</span><span>8 Sep</span><span>15 Sep</span><span>22 Sep</span><span>30 Sep</span></div></div>
      </Card>
      <Card className="quick-card"><span className="eyebrow">Quick order</span><h2>Start growing today</h2><p>Choose a platform and launch a new campaign in minutes.</p>
        <div className="platform-list">{["Instagram", "TikTok", "Facebook", "X", "Telegram"].map((p) => <button onClick={() => go("new-order")} key={p}><SocialIcon platform={p}/><span>{p}</span><Icon name="arrow" /></button>)}</div>
      </Card>
    </div>
    <Card><div className="card-head"><div><span className="eyebrow">Latest activity</span><h2>Recent orders</h2></div><Button variant="secondary" onClick={() => go("orders")}>View all orders</Button></div><OrderTable orders={recentOrders} onView={(id) => go(`order-details?id=${id}`)} /></Card>
  </>;
}

function NewOrder({ go }: { go: (page: string) => void }) {
  const [platform, setPlatform] = useState("Instagram");
  const [services, setServices] = useState<ServiceItem[]>([]);
  const [selectedServiceId, setSelectedServiceId] = useState<number>(0);
  const [target, setTarget] = useState("");
  const [quantity, setQuantity] = useState("1000");
  const [placedOrder, setPlacedOrder] = useState<OrderDetail | null>(null);
  const [error, setError] = useState("");
  const [serviceError, setServiceError] = useState("");
  const [loadingServices, setLoadingServices] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setLoadingServices(true);
    setServiceError("");
    api.getServices(platform).then(res => {
      setServices(res.services);
      if (res.services.length > 0) {
        setSelectedServiceId(res.services[0].id);
      } else {
        setSelectedServiceId(0);
        setServiceError(`No active services currently available for ${platform}. Please select another platform or check back soon.`);
      }
    }).catch((err: any) => {
      setServices([]);
      setSelectedServiceId(0);
      setServiceError(err.message || `Failed to load services for ${platform}.`);
    }).finally(() => {
      setLoadingServices(false);
    });
  }, [platform]);

  const activeService = services.find(s => s.id === selectedServiceId) || services[0];
  const unitPrice = activeService ? parseFloat(activeService.price_per_1000_ghs) : 20.0;
  const total = ((Number(quantity || 0) / 1000) * unitPrice + 5).toFixed(2);

  const handlePlaceOrder = async () => {
    if (!activeService || !target) {
      setError("Please fill in all fields.");
      return;
    }
    setError("");
    setSubmitting(true);
    try {
      const res = await api.createOrder({
        service_id: activeService.id,
        target,
        quantity: Number(quantity)
      });
      setPlacedOrder(res.order);
    } catch (err: any) {
      setError(err.message || "Failed to place order.");
    } finally {
      setSubmitting(false);
    }
  };

  return <><PageTitle title="Create New Order" description="Launch a new campaign in a few simple steps." />
    <div className="form-layout">
      <Card><div className="form-section"><div className="number">01</div><div><h2>Select a platform</h2><p>Choose where you want to grow your audience.</p></div></div>
        <div className="platform-grid">{["Instagram", "TikTok", "Facebook", "X", "Telegram"].map((p) => <button className={platform === p ? "selected" : ""} onClick={() => setPlatform(p)} key={p}><SocialIcon platform={p}/>{p}{platform === p && <Icon name="check" />}</button>)}</div>
        <hr/>
        <div className="form-section"><div className="number">02</div><div><h2>Order details</h2><p>Tell us exactly what you need.</p></div></div>
        <div className="fields-grid">
          <SelectField label="Service" value={selectedServiceId.toString()} onChange={(v) => setSelectedServiceId(Number(v))}>
            {loadingServices ? (
              <option value="0">Loading services for {platform}...</option>
            ) : services.length === 0 ? (
              <option value="0">No active services available for {platform}</option>
            ) : (
              services.map(s => <option key={s.id} value={s.id}>{s.name} - GHS {s.price_per_1000_ghs}/1,000</option>)
            )}
          </SelectField>
          <Field label="Target URL or username" placeholder="https://instagram.com/yourprofile" value={target} onChange={setTarget} />
        </div>
        {serviceError && <div className="payment-warning" style={{ marginTop: "0.5rem" }}><strong>{serviceError}</strong></div>}
        <div className="fields-grid" style={{ marginTop: "1rem" }}>
          <Field label="Quantity" value={quantity} type="number" onChange={setQuantity}/>
          <div className="info-box"><span>Service limits</span><strong>Min {activeService?.min_quantity || 100} · Max {(activeService?.max_quantity || 100000).toLocaleString()}</strong><small>Estimated delivery: 10–30 minutes</small></div>
        </div>
        {error && <div className="payment-warning" style={{ marginTop: "1rem" }}><strong>{error}</strong></div>}
      </Card>
      <Card className="summary"><span className="eyebrow">Order summary</span><h2>Review your order</h2>
        <dl>
          <div><dt>Platform</dt><dd>{platform}</dd></div>
          <div><dt>Service</dt><dd>{activeService?.name || "Service"}</dd></div>
          <div><dt>Quantity</dt><dd>{Number(quantity || 0).toLocaleString()}</dd></div>
          <div><dt>Service cost</dt><dd>GHS {((Number(quantity || 0) / 1000) * unitPrice).toFixed(2)}</dd></div>
          <div><dt>Processing fee</dt><dd>GHS 5.00</dd></div>
        </dl>
        <div className="total"><span>Total</span><strong>GHS {total}</strong></div>
        <Button full icon="arrow" disabled={!quantity || submitting} onClick={handlePlaceOrder}>{submitting ? "Placing Order..." : "Place Order"}</Button>
        <small className="secure"><Icon name="shield" size={14}/> Secure guest checkout. No account required.</small>
      </Card>
    </div>
    {placedOrder && <div className="modal-backdrop"><div className="modal"><button className="modal-close" onClick={() => setPlacedOrder(null)}><Icon name="close"/></button><span className="success-icon"><Icon name="check" size={28}/></span><h2>Order created</h2><p>Your order <strong>{placedOrder.public_order_id}</strong> is ready for payment. Pay the exact amount and upload your receipt.</p><div className="receipt-total"><span>Amount due</span><strong>GHS {placedOrder.charge_ghs}</strong></div><Button full onClick={() => go("payment")}>Continue to payment</Button><Button full variant="ghost" onClick={() => setPlacedOrder(null)}>Pay later</Button></div></div>}
  </>;
}

function Orders({ go }: { go: (page: string) => void }) {
  const [filter, setFilter] = useState("All");
  const [orders, setOrders] = useState<OrderDetail[]>([]);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    const statusParam = filter === "All" ? undefined : filter;
    api.getAccountOrders({ status: statusParam }).then(res => {
      setOrders(res.orders);
      setTotal(res.total);
    }).catch(() => {});
  }, [filter]);

  return <><PageTitle title="My Orders" description="Track and manage all your campaigns." action={<Button icon="plus" onClick={() => go("new-order")}>New Order</Button>} />
    <Card><div className="filters"><div className="search"><Icon name="search"/><input placeholder="Search by order ID or service..." /></div><SelectField value={filter} onChange={setFilter}><option>All</option><option>Pending</option><option>Processing</option><option>Completed</option><option>Cancelled</option></SelectField></div>
      <div className="tabs">{["All", "Pending", "Processing", "Completed", "Cancelled"].map((x) => <button onClick={() => setFilter(x)} className={filter === x ? "active" : ""} key={x}>{x}</button>)}</div>
      <OrderTable orders={orders} onView={(id) => go(`order-details?id=${id}`)} />
      <div className="pagination"><span>Showing {orders.length} of {total} orders</span></div>
    </Card>
  </>;
}

function OrderDetails({ go }: { go: (page: string) => void }) {
  const [order, setOrder] = useState<OrderDetail | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(location.hash.split("?")[1] || "");
    const id = params.get("id");
    if (id) {
      api.getOrderDetail(id).then(res => setOrder(res.order)).catch(() => {});
    }
  }, []);

  if (!order) return <Card><p>Loading order details...</p></Card>;

  return <><button className="back-link" onClick={() => go("orders")}>← Back to orders</button><PageTitle title={`Order ${order.public_order_id}`} description={`Placed on ${new Date(order.created_at).toLocaleString()}`} action={<Status>{order.status}</Status>} />
    <Card className="tracking"><div className="card-head"><div><span className="eyebrow">Delivery progress</span><h2>{order.quantity - (order.remains ?? order.quantity)} of {order.quantity.toLocaleString()} delivered</h2></div><strong>{order.progress_percent}%</strong></div><div className="progress"><span style={{ width: `${order.progress_percent}%` }}/></div><div className="tracking-labels"><span>Start count: {order.start_count ?? 0}</span><span>{order.remains ?? order.quantity} remaining</span></div></Card>
    <div className="details-grid"><Card><h2>Order details</h2><dl className="detail-list">{[["Platform",order.platform],["Service",order.service_name],["Target",order.target],["Quantity",order.quantity.toLocaleString()],["Price",`GHS ${order.charge_ghs}`]].map(([a,b]) => <div key={a}><dt>{a}</dt><dd>{b}</dd></div>)}</dl></Card>
    </div>
  </>;
}

function Services({ go }: { go: (page: string) => void }) {
  const [services, setServices] = useState<ServiceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    api.getServices().then(res => {
      setServices(res.services);
      if (res.services.length === 0) {
        setError("No services are currently available in the catalog.");
      }
    }).catch(err => {
      setError(err.message || "Failed to load services catalog.");
    }).finally(() => {
      setLoading(false);
    });
  }, []);

  return <><PageTitle title="Services" description="Explore our complete catalog of social growth services." />
    <Card>
      {loading ? (
        <div style={{ padding: "32px", textAlign: "center" }}>Loading service catalog...</div>
      ) : error && services.length === 0 ? (
        <div style={{ padding: "32px", textAlign: "center", color: "#f87171" }}>{error}</div>
      ) : (
        <div className="table-wrap"><table><thead><tr><th>Platform</th><th>Service</th><th>Description</th><th>Min / Max</th><th>Price / 1,000</th><th>Speed</th><th></th></tr></thead><tbody>{services.map((s) => <tr key={s.id}><td><span className="platform-cell"><SocialIcon platform={s.platform}/>{s.platform}</span></td><td><strong>{s.name}</strong></td><td>{s.description}</td><td>{s.min_quantity.toLocaleString()} / {s.max_quantity.toLocaleString()}</td><td><strong>GHS {s.price_per_1000_ghs}</strong></td><td><Status>{s.speed || "Fast"}</Status></td><td><Button variant="secondary" onClick={() => go("new-order")}>Order now</Button></td></tr>)}</tbody></table></div>
      )}
    </Card>
  </>;
}

function Wallet({ go }: { go: (page: string) => void }) {
  const [wallet, setWallet] = useState<WalletSummary>({ available_balance: "0.00", total_spent: "0.00", total_deposited: "0.00" });
  const [txs, setTxs] = useState<LedgerTxItem[]>([]);

  useEffect(() => {
    api.getAccountWallet().then(setWallet).catch(() => {});
    api.getAccountTransactions().then(res => setTxs(res.transactions)).catch(() => {});
  }, []);

  return <><PageTitle title="Wallet" description="Manage your balance and payments." action={<Button icon="plus" onClick={() => go("payment")}>Add Funds</Button>} />
    <Card className="balance-hero"><div><span>Available balance</span><strong>GHS {wallet.available_balance}</strong><p>Ready to use on any BoostX service.</p></div><div><Button variant="secondary" onClick={() => go("payment")}>Add funds</Button></div></Card>
    <Card><div className="card-head"><div><span className="eyebrow">Recent activity</span><h2>Transaction history</h2></div></div>
      <div className="table-wrap"><table><thead><tr><th>Reference</th><th>Type</th><th>Description</th><th>Amount</th><th>Status</th><th>Date</th></tr></thead><tbody>{txs.map((r) => <tr key={r.id}><td><strong>{r.reference || `#TX-${r.id}`}</strong></td><td>{r.type}</td><td>{r.description}</td><td><strong>GHS {r.amount_ghs}</strong></td><td><Status>{r.status}</Status></td><td>{new Date(r.created_at).toLocaleDateString()}</td></tr>)}</tbody></table></div>
    </Card>
  </>;
}

function Payment({ go }: { go: (page: string) => void }) {
  const [amount, setAmount] = useState("100");
  const [network, setNetwork] = useState("Telecel");
  const [upload, setUpload] = useState<"idle" | "uploading" | "verified" | "rejected" | "review">("idle");
  const [filename, setFilename] = useState("");
  const [paymentId, setPaymentId] = useState("");
  const [error, setError] = useState("");

  const selectFile = async (file?: File) => {
    if (!file) return;
    setFilename(file.name);
    setUpload("uploading");
    setError("");

    try {
      const p = await api.createPayment(Number(amount), network);
      setPaymentId(p.payment_id);
      const res = await api.uploadScreenshot(p.payment_id, file);

      if (res.status === "Verified") setUpload("verified");
      else if (res.status === "Rejected") setUpload("rejected");
      else setUpload("review");
    } catch (err: any) {
      setError(err.message || "Upload failed");
      setUpload("idle");
    }
  };

  return <><PageTitle title="Complete Payment" description="Send the exact amount, then upload your payment screenshot." />
    <div className="payment-layout">
      <div className="payment-main">
        <Card><div className="card-head"><div><span className="eyebrow">Amount to send</span><h2>Choose your payment amount</h2></div><span className="icon-tile"><Icon name="wallet"/></span></div><Field label="Amount in Ghana Cedi" value={amount} type="number" onChange={setAmount}/><div className="amounts">{["50","100","250","500"].map(a => <button className={amount === a ? "selected" : ""} onClick={() => setAmount(a)} key={a}>GHS {a}</button>)}</div></Card>
        <Card><span className="eyebrow">Mobile money</span><h2>Select your network</h2><div className="network-tabs">{["Telecel","MTN","AirtelTigo"].map(n => <button className={network === n ? "active" : ""} onClick={() => setNetwork(n)} key={n}>{n}</button>)}</div>
          <div className="payment-account"><div><small>Send payment to</small><strong>0202979378</strong><span>Telecel Cash · Account name: BOOSTX</span></div></div>
        </Card>
        <Card><span className="eyebrow">Payment proof</span><h2>Upload your screenshot</h2>
          <label className={`upload-zone ${upload !== "idle" ? "has-file" : ""}`}>
            <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => selectFile(e.target.files?.[0])}/>
            <span className="upload-icon"><Icon name={upload === "verified" ? "check" : "plus"} size={22}/></span>
            <strong>{upload === "idle" ? "Drop your payment screenshot here" : upload === "uploading" ? "Uploading screenshot…" : filename}</strong>
            {upload === "idle" && <span className="browse">Choose file</span>}
          </label>
          {error && <div className="payment-warning" style={{ marginTop: "1rem" }}><strong>{error}</strong></div>}
        </Card>
      </div>
      <div className="payment-side">
        <Card className="summary"><span className="eyebrow">Payment summary</span><h2>Review payment</h2><div className="total"><span>Exact amount due</span><strong>GHS {Number(amount || 0).toFixed(2)}</strong></div></Card>
        {upload === "verified" && <Card className="verification-result"><Status>Verified</Status><h2>Payment confirmed</h2><Button full onClick={() => go("orders")}>Continue to Orders</Button></Card>}
        {upload === "rejected" && <Card className="verification-result"><Status>Rejected</Status><h2>Payment could not be verified</h2><Button full variant="secondary" onClick={() => setUpload("idle")}>Upload New Screenshot</Button></Card>}
      </div>
    </div>
  </>;
}

function Transactions() {
  const [txs, setTxs] = useState<LedgerTxItem[]>([]);
  useEffect(() => { api.getAccountTransactions().then(res => setTxs(res.transactions)).catch(() => {}); }, []);
  return <><PageTitle title="Transactions" description="A complete record of money moving through your account." /><Card><div className="table-wrap"><table><thead><tr><th>ID</th><th>Type</th><th>Description</th><th>Amount</th><th>Status</th><th>Date</th></tr></thead><tbody>{txs.map(r => <tr key={r.id}><td><strong>#TX{r.id}</strong></td><td>{r.type}</td><td>{r.description}</td><td><strong>GHS {r.amount_ghs}</strong></td><td><Status>{r.status}</Status></td><td>{new Date(r.created_at).toLocaleDateString()}</td></tr>)}</tbody></table></div></Card></>;
}

function Support() {
  return <><PageTitle title="Support Center" description="Find answers or get help from our team." /><Card><p>Need help? Contact support@boostx.com or open a ticket in your dashboard.</p></Card></>;
}

function Profile({ user }: { user: UserInfo | null }) {
  return <><PageTitle title="Profile" description="Manage your personal information." />
    <Card><div className="profile-head"><div><h2>{user?.full_name || user?.email || "Guest User"}</h2><p>{user?.email || user?.phone || "Guest Session"}</p><Status>{user?.authenticated ? "Registered Account" : "Guest Checkout Session"}</Status></div></div></Card>
  </>;
}

function Settings({ dark, setDark }: { dark: boolean; setDark: (v: boolean) => void }) {
  return <><PageTitle title="Settings" description="Control your account preferences and security." /><Card><span className="eyebrow">Appearance</span><h2>Choose your theme</h2><div className="theme-cards"><button className={!dark ? "selected" : ""} onClick={() => setDark(false)}><span><Icon name="sun"/>Light mode</span></button><button className={dark ? "selected" : ""} onClick={() => setDark(true)}><span><Icon name="moon"/>Dark mode</span></button></div></Card></>;
}

function Auth({ mode, go, onAuthed }: { mode: "login" | "register"; go: (page: string) => void; onAuthed: (user: UserInfo) => void }) {
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = mode === "login"
        ? await api.login(identifier, password)
        : await api.register({ email: identifier, password, full_name: fullName });
      // Load the freshly authenticated user before navigating, otherwise the
      // app keeps rendering the stale guest state from the initial /auth/me.
      const me = await api.getMe();
      onAuthed(me);
      go(me.role === "admin" || res.redirect_path === "/admin" ? "admin" : "dashboard");
    } catch (err: any) {
      setError(err.message || "Authentication failed.");
    } finally {
      setLoading(false);
    }
  };

  return <div className="auth-page"><div className="auth-brand"><img src={logo} alt="BoostX"/><div><span className="eyebrow">Social growth, simplified</span><h1>Build momentum.<br/>Reach more people.</h1></div></div>
    <div className="auth-form"><Card>
      <h2>{mode === "login" ? "Sign in to BoostX" : "Start growing with BoostX"}</h2>
      <form onSubmit={handleSubmit}>
        {mode === "register" && <Field label="Full name" value={fullName} onChange={setFullName}/>}
        <Field label="Email or phone" value={identifier} onChange={setIdentifier}/>
        <Field label="Password" type="password" value={password} onChange={setPassword}/>
        {error && <div className="payment-warning" style={{ margin: "1rem 0" }}><strong>{error}</strong></div>}
        <Button full type="submit" disabled={loading}>{loading ? "Processing..." : mode === "login" ? "Sign in" : "Create account"}</Button>
      </form>
      <div className="auth-switch">{mode === "login" ? "New to BoostX?" : "Already have an account?"}<button onClick={() => go(mode === "login" ? "register" : "login")}>{mode === "login" ? "Create an account" : "Sign in"}</button></div>
      <Button full variant="secondary" onClick={() => go("new-order")}>Continue as guest</Button>
    </Card></div>
  </div>;
}

const adminNavGroups = [
  { label: "Admin Core", links: [["admin", "Overview", "chart"], ["admin-payments", "Payments", "card"], ["admin-orders", "Orders", "orders"], ["admin-services", "Services", "services"], ["admin-platforms", "Platforms", "shield"]] },
  { label: "System Config", links: [["admin-pricing", "Pricing", "wallet"], ["admin-health", "System Health", "shield"], ["admin-audit", "Audit Logs", "clock"]] },
  { label: "Storefront", links: [["dashboard", "Main Storefront", "home"]] },
] as const;

function Shell({ page, go, children, dark, setDark, user, onLoggedOut }: { page: string; go: (page: string) => void; children: ReactNode; dark: boolean; setDark: (v: boolean) => void; user: UserInfo | null; onLoggedOut: () => void }) {
  const [open, setOpen] = useState(false);
  const handleLogout = async () => {
    await api.logout().catch(() => {});
    onLoggedOut();
    go("login");
  };

  const activeGroups = page.startsWith("admin") ? adminNavGroups : navGroups;

  return <div className="app-shell" data-admin={page.startsWith("admin") ? "true" : undefined}><aside className={open ? "open" : ""}><div className="sidebar-logo"><img src={logo} alt="BoostX"/><button onClick={() => setOpen(false)}><Icon name="close"/></button></div><nav>{activeGroups.map(g => <div className="nav-group" key={g.label}><span>{g.label}</span>{g.links.map(([id,label,icon]) => <button className={page === id ? "active" : ""} onClick={() => { go(id); setOpen(false); }} key={id}><Icon name={icon as IconName}/>{label}</button>)}</div>)}</nav><div className="sidebar-bottom"><button onClick={() => setDark(!dark)}><Icon name={dark ? "sun" : "moon"}/>{dark ? "Light mode" : "Dark mode"}</button>{user?.authenticated && <button onClick={handleLogout}><Icon name="logout"/>Log out</button>}</div></aside>{open && <button className="drawer-backdrop" onClick={() => setOpen(false)} aria-label="Close menu"/>}
    <div className="main"><header><button className="mobile-menu" onClick={() => setOpen(true)}><Icon name="menu"/></button><div className="top-search"><Icon name="search"/><input placeholder="Search orders, services..."/></div><div className="top-actions"><button className="user-menu" onClick={() => go(user?.authenticated ? "profile" : "login")}><span className="avatar">{user?.full_name ? user.full_name.substring(0, 2).toUpperCase() : "BX"}</span><span><strong>{user?.full_name || "Guest"}</strong><small>{user?.role || "Customer"}</small></span></button></div></header><main>{children}</main></div>
  </div>;
}

// Lazy loaded Admin screens
const AdminDashboard = lazy(() => import("./components/AdminComponents").then(m => ({ default: m.AdminDashboard })));
const AdminPayments = lazy(() => import("./components/AdminComponents").then(m => ({ default: m.AdminPayments })));
const AdminPaymentReview = lazy(() => import("./components/AdminComponents").then(m => ({ default: m.AdminPaymentReview })));
const AdminOrders = lazy(() => import("./components/AdminComponents").then(m => ({ default: m.AdminOrders })));
const AdminServices = lazy(() => import("./components/AdminComponents").then(m => ({ default: m.AdminServices })));
const AdminPlatforms = lazy(() => import("./components/AdminComponents").then(m => ({ default: m.AdminPlatforms })));
const AdminConfigPage = lazy(() => import("./components/AdminComponents").then(m => ({ default: m.AdminConfigPage })));

export default function App() {
  const initial = location.hash.replace("#/", "").split("?")[0] || "dashboard";
  const [page, setPage] = useState(initial);
  const [user, setUser] = useState<UserInfo | null>(null);
  const [dark, setDarkState] = useState(() => localStorage.getItem("boostx-theme") === "dark");

  const setDark = (value: boolean) => { setDarkState(value); localStorage.setItem("boostx-theme", value ? "dark" : "light"); };

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
  }, [dark]);

  useEffect(() => {
    api.initSession().then(() => {
      api.getMe().then(setUser).catch(() => {});
    }).catch(() => {});
  }, []);

  useEffect(() => {
    const sync = () => setPage(location.hash.replace("#/", "").split("?")[0] || "dashboard");
    addEventListener("hashchange", sync);
    return () => removeEventListener("hashchange", sync);
  }, []);

  const go = (next: string) => {
    location.hash = `/${next}`;
    setPage(next.split("?")[0]);
    scrollTo({ top: 0, behavior: "smooth" });
  };

  const screen = useMemo(() => {
    switch (page) {
      case "dashboard": return <Dashboard go={go} user={user} />;
      case "new-order": return <NewOrder go={go} />;
      case "orders": return <Orders go={go} />;
      case "order-details": return <OrderDetails go={go} />;
      case "services": return <Services go={go} />;
      case "wallet": return <Wallet go={go} />;
      case "payment": return <Payment go={go} />;
      case "transactions": return <Transactions />;
      case "support": return <Support />;
      case "profile": return <Profile user={user} />;
      case "settings": return <Settings dark={dark} setDark={setDark} />;
      case "track": return <TrackOrderPage go={go} />;
      case "help": return <HelpFAQPage />;
      case "terms": case "privacy": case "refunds": case "cookies": case "security": case "disclaimer":
        return <LegalPage type={page} />;
      case "404": return <NotFoundPage go={go} />;
      default: return <Dashboard go={go} user={user} />;
    }
  }, [page, dark, user]);

  if (page === "login" || page === "register") return <Auth mode={page} go={go} onAuthed={setUser}/>;

  let content: ReactNode = screen;

  if (page.startsWith("admin")) {
    content = (
      <Suspense fallback={<Card><p>Loading admin panel...</p></Card>}>
        {page === "admin" && <AdminDashboard go={go} />}
        {page === "admin-payments" && <AdminPayments go={go} />}
        {page === "admin-payment-review" && <AdminPaymentReview go={go} />}
        {page === "admin-orders" && <AdminOrders />}
        {page === "admin-services" && <AdminServices />}
        {page === "admin-platforms" && <AdminPlatforms />}
        {page.startsWith("admin-") && !["admin-payments","admin-payment-review","admin-orders","admin-services","admin-platforms"].includes(page) && (
          <AdminConfigPage type={page.replace("admin-", "")} />
        )}
      </Suspense>
    );
  }

  return <Shell page={page} go={go} dark={dark} setDark={setDark} user={user} onLoggedOut={() => { setUser(null); api.initSession().then(() => api.getMe().then(setUser)).catch(() => {}); }}>{content}</Shell>;
}
