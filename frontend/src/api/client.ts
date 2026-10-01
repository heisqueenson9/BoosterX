import type {
  UserInfo, PlatformItem, ServiceItem, OrderPreviewQuote, OrderDetail, OrderListResponse,
  PaymentItem, WalletSummary, LedgerTxItem, AdminOverviewStats, AdminAuditLogItem
} from "./types";

let csrfToken: string | null = null;

export function setCsrfToken(token: string | null) {
  csrfToken = token;
}

export function getCsrfToken(): string | null {
  return csrfToken;
}

async function request<T>(endpoint: string, options: RequestInit = {}, retried = false): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> || {}),
  };

  if (csrfToken && !headers["X-CSRF-Token"]) {
    headers["X-CSRF-Token"] = csrfToken;
  }

  let response = await fetch(endpoint, {
    ...options,
    headers,
    credentials: "same-origin",
  });

  // Stale/missing CSRF token (e.g. session cookie expired): refresh once and retry.
  if (response.status === 403 && !retried && endpoint !== "/api/session") {
    const body = await response.clone().json().catch(() => ({}));
    if (typeof body.error === "string" && body.error.includes("CSRF")) {
      const init = await fetch("/api/session", { method: "POST", credentials: "same-origin" });
      const initData = await init.json().catch(() => ({}));
      if (initData.csrf_token) csrfToken = initData.csrf_token;
      const { ["X-CSRF-Token"]: _drop, ...rest } = (options.headers as Record<string, string>) || {};
      return request<T>(endpoint, { ...options, headers: rest }, true);
    }
  }

  const contentType = response.headers.get("content-type") || "";
  let data: any = {};
  if (contentType.includes("application/json")) {
    data = await response.json();
  }

  if (data.csrf_token) {
    csrfToken = data.csrf_token;
  }

  if (!response.ok) {
    const errorMsg = data.error || data.message || `Request failed with status ${response.status}`;
    const err = new Error(errorMsg) as any;
    err.status = response.status;
    err.details = data.details || data;
    throw err;
  }

  return data as T;
}

export const api = {
  // Auth & Session
  initSession: async (): Promise<{ status: string; csrf_token: string; is_guest: boolean }> => {
    const res = await request<{ status: string; csrf_token: string; is_guest: boolean }>("/api/session", { method: "POST" });
    if (res.csrf_token) csrfToken = res.csrf_token;
    return res;
  },

  getMe: async (): Promise<UserInfo> => {
    const res = await request<UserInfo>("/api/auth/me");
    if (res.csrf_token) csrfToken = res.csrf_token;
    return res;
  },

  login: async (identifier: string, password: string) => {
    return request<{ redirect_path: string; csrf_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ identifier, password }),
    });
  },

  register: async (data: { username?: string; phone?: string; email?: string; password: string; full_name?: string }) => {
    return request<{ redirect_path: string; csrf_token: string }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  logout: async () => {
    return request<{ message: string }>("/api/auth/logout", { method: "POST" });
  },

  // Catalog
  getPlatforms: async (): Promise<{ platforms: PlatformItem[] }> => {
    return request<{ platforms: PlatformItem[] }>("/api/platforms");
  },

  getServices: async (platform?: string): Promise<{ services: ServiceItem[] }> => {
    const url = platform ? `/api/services?platform=${encodeURIComponent(platform)}` : "/api/services";
    return request<{ services: ServiceItem[] }>(url);
  },

  getServiceDetail: async (id: number): Promise<ServiceItem> => {
    return request<ServiceItem>(`/api/services/${id}`);
  },

  previewOrder: async (serviceId: number, quantity: number): Promise<OrderPreviewQuote> => {
    return request<OrderPreviewQuote>("/api/orders/preview", {
      method: "POST",
      body: JSON.stringify({ service_id: serviceId, quantity }),
    });
  },

  // Orders
  createOrder: async (data: { service_id: number; target: string; quantity: number; idempotency_key?: string }): Promise<{ order: OrderDetail }> => {
    const headers: Record<string, string> = {};
    if (data.idempotency_key) {
      headers["Idempotency-Key"] = data.idempotency_key;
    }
    return request<{ order: OrderDetail }>("/api/orders", {
      method: "POST",
      headers,
      body: JSON.stringify(data),
    });
  },

  getOrderDetail: async (publicId: string): Promise<{ order: OrderDetail }> => {
    return request<{ order: OrderDetail }>(`/api/orders/${encodeURIComponent(publicId)}`);
  },

  getOrderStatus: async (publicId: string): Promise<{ public_order_id: string; status: string; start_count: number; remains: number; progress_percent: number }> => {
    return request<{ public_order_id: string; status: string; start_count: number; remains: number; progress_percent: number }>(`/api/orders/${encodeURIComponent(publicId)}/status`);
  },

  cancelOrder: async (publicId: string): Promise<{ message: string; refund_amount_ghs: string }> => {
    return request<{ message: string; refund_amount_ghs: string }>(`/api/orders/${encodeURIComponent(publicId)}/cancel`, { method: "POST" });
  },

  refillOrder: async (publicId: string): Promise<{ message: string; refill_id: string }> => {
    return request<{ message: string; refill_id: string }>(`/api/orders/${encodeURIComponent(publicId)}/refill`, { method: "POST" });
  },

  getAccountOrders: async (params?: { page?: number; per_page?: number; search?: string; status?: string }): Promise<OrderListResponse> => {
    const query = new URLSearchParams();
    if (params?.page) query.append("page", String(params.page));
    if (params?.per_page) query.append("per_page", String(params.per_page));
    if (params?.search) query.append("search", params.search);
    if (params?.status) query.append("status", params.status);
    const url = `/api/account/orders${query.toString() ? `?${query.toString()}` : ""}`;
    return request<OrderListResponse>(url);
  },

  getAccountWallet: async (): Promise<WalletSummary> => {
    return request<WalletSummary>("/api/account/wallet");
  },

  getAccountTransactions: async (params?: { page?: number; per_page?: number }): Promise<{ transactions: LedgerTxItem[]; total: number; page: number; per_page: number }> => {
    const query = new URLSearchParams();
    if (params?.page) query.append("page", String(params.page));
    if (params?.per_page) query.append("per_page", String(params.per_page));
    return request<{ transactions: LedgerTxItem[]; total: number; page: number; per_page: number }>(`/api/account/transactions?${query.toString()}`);
  },

  // Payments
  createPayment: async (amount_ghs: number, network: string = "Telecel"): Promise<PaymentItem> => {
    return request<PaymentItem>("/api/payments", {
      method: "POST",
      body: JSON.stringify({ amount_ghs, network }),
    });
  },

  uploadScreenshot: async (paymentId: string, file: File): Promise<{ payment_id: string; status: string; expected_amount_ghs: string; detected_amount_ghs?: string; recipient?: string; reference?: string; rejection_reason?: string }> => {
    const formData = new FormData();
    formData.append("file", file);

    const headers: Record<string, string> = {};
    if (csrfToken) {
      headers["X-CSRF-Token"] = csrfToken;
    }

    const res = await fetch(`/api/payments/${encodeURIComponent(paymentId)}/screenshot`, {
      method: "POST",
      headers,
      body: formData,
      credentials: "same-origin",
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || "Upload failed");
    }
    return data;
  },

  getPaymentDetail: async (paymentId: string): Promise<PaymentItem> => {
    return request<PaymentItem>(`/api/payments/${encodeURIComponent(paymentId)}`);
  },

  listPayments: async (): Promise<{ payments: PaymentItem[] }> => {
    return request<{ payments: PaymentItem[] }>("/api/payments");
  },

  // Admin API
  getAdminOverview: async (): Promise<AdminOverviewStats> => {
    return request<AdminOverviewStats>("/api/admin/overview");
  },

  getAdminPayments: async (params?: { page?: number; status?: string; search?: string }) => {
    const query = new URLSearchParams();
    if (params?.page) query.append("page", String(params.page));
    if (params?.status) query.append("status", params.status);
    if (params?.search) query.append("search", params.search);
    return request<{ payments: any[]; total: number; page: number; per_page: number }>(`/api/admin/payments?${query.toString()}`);
  },

  adminVerifyPayment: async (paymentId: string, reference?: string) => {
    return request<{ message: string }>(`/api/admin/payments/${encodeURIComponent(paymentId)}/verify`, {
      method: "POST",
      body: JSON.stringify({ reference }),
    });
  },

  adminRejectPayment: async (paymentId: string, reason?: string) => {
    return request<{ message: string }>(`/api/admin/payments/${encodeURIComponent(paymentId)}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
  },

  getAdminOrders: async (params?: { page?: number; status?: string; platform?: string; needs_attention?: boolean; search?: string }) => {
    const query = new URLSearchParams();
    if (params?.page) query.append("page", String(params.page));
    if (params?.status) query.append("status", params.status);
    if (params?.platform) query.append("platform", params.platform);
    if (params?.needs_attention !== undefined) query.append("needs_attention", String(params.needs_attention));
    if (params?.search) query.append("search", params.search);
    return request<{ orders: OrderDetail[]; total: number; page: number; per_page: number }>(`/api/admin/orders?${query.toString()}`);
  },

  adminOrderAction: async (publicId: string, action: string, extra?: Record<string, any>) => {
    return request<{ message: string }>(`/api/admin/orders/${encodeURIComponent(publicId)}/action`, {
      method: "POST",
      body: JSON.stringify({ action, ...(extra || {}) }),
    });
  },

  getAdminServices: async () => {
    return request<{ services: any[] }>("/api/admin/services");
  },

  updateAdminService: async (id: number, data: { enabled?: boolean; rate_usd_per_1000?: number; min_qty?: number; max_qty?: number }) => {
    return request<{ message: string }>(`/api/admin/services/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  syncAdminServices: async () => {
    return request<any>("/api/admin/services/sync", { method: "POST" });
  },

  getAdminPlatforms: async () => {
    return request<{ platforms: any[] }>("/api/admin/platforms");
  },

  updateAdminPlatform: async (id: number, active: boolean) => {
    return request<{ message: string }>(`/api/admin/platforms/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ active }),
    });
  },

  getAdminUsers: async (params?: { page?: number; search?: string; status?: string }) => {
    const query = new URLSearchParams();
    if (params?.page) query.append("page", String(params.page));
    if (params?.search) query.append("search", params.search);
    if (params?.status) query.append("status", params.status);
    return request<{ users: any[]; total: number; page: number; per_page: number }>(`/api/admin/users?${query.toString()}`);
  },

  updateAdminUserStatus: async (id: number, status: string) => {
    return request<{ message: string }>(`/api/admin/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
  },

  getAdminAuditLogs: async (page: number = 1) => {
    return request<{ audit_logs: AdminAuditLogItem[]; total: number; page: number; per_page: number }>(`/api/admin/audit-logs?page=${page}`);
  },

  getAdminHealth: async () => {
    return request<any>("/api/admin/system/health");
  },

  getAdminPricing: async () => {
    return request<{ usd_to_ghs_rate: string; flat_markup_ghs: string }>("/api/admin/pricing");
  },

  updateAdminPricing: async (usd_to_ghs_rate?: string, flat_markup_ghs?: string) => {
    return request<{ message: string }>("/api/admin/pricing", {
      method: "POST",
      body: JSON.stringify({ usd_to_ghs_rate, flat_markup_ghs }),
    });
  },

  getAdminProviderBalance: async () => {
    return request<{ balance: string; currency: string }>("/api/admin/provider/balance");
  }
};
