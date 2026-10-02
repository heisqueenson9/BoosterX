import type {
  UserInfo, AuthResponse, PlatformItem, ServiceItem, OrderPreviewQuote, OrderDetail, OrderListResponse,
  PaymentItem, WalletSummary, LedgerTxItem, AdminOverviewStats, AdminAuditLogItem
} from "./types";

let csrfToken: string | null = null;
let unauthorizedHandler: (() => void) | null = null;

export function setCsrfToken(token: string | null) {
  csrfToken = token;
}

export function getCsrfToken(): string | null {
  return csrfToken;
}

/** Called when a signed-in session is rejected (expired/revoked) by the server. */
export function setUnauthorizedHandler(handler: (() => void) | null) {
  unauthorizedHandler = handler;
}

// Endpoints where a 401 means "wrong credentials", not "session expired".
const CREDENTIAL_ENDPOINTS = ["/api/auth/login", "/api/auth/register", "/api/auth/logout"];

function friendlyError(status: number, data: any): string {
  const serverMessage = typeof data?.error === "string" ? data.error : typeof data?.message === "string" ? data.message : "";
  if (status >= 500) return "Something went wrong on our side. Please try again in a moment.";
  if (status === 429) return serverMessage || "Too many attempts. Please wait a minute and try again.";
  if (serverMessage) return serverMessage;
  if (status === 401) return "Please sign in to continue.";
  if (status === 403) return "You don't have permission to do that.";
  return "The request could not be completed. Please try again.";
}

async function request<T>(endpoint: string, options: RequestInit = {}, retried = false): Promise<T> {
  const headers: Record<string, string> = { ...(options.headers as Record<string, string> || {}) };
  // Let the browser set the multipart boundary for file uploads.
  if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  if (csrfToken && !headers["X-CSRF-Token"]) {
    headers["X-CSRF-Token"] = csrfToken;
  }

  let response: Response;
  try {
    response = await fetch(endpoint, { ...options, headers, credentials: "same-origin" });
  } catch {
    const err = new Error("Unable to reach the server. Please check your connection and try again.") as any;
    err.status = 0;
    throw err;
  }

  let data: any = {};
  if ((response.headers.get("content-type") || "").includes("application/json")) {
    try { data = await response.json(); } catch { data = {}; }
  }

  // Stale CSRF token (e.g. rotated by a login in another tab): fetch a fresh one once and retry.
  if (response.status === 403 && !retried && typeof data.error === "string" && data.error.includes("CSRF")) {
    try {
      const me = await fetch("/api/auth/me", { credentials: "same-origin" }).then(r => r.json());
      if (me?.authenticated && me.csrf_token) {
        csrfToken = me.csrf_token;
        return request<T>(endpoint, options, true);
      }
    } catch { /* fall through to the normal error path */ }
    csrfToken = null;
    unauthorizedHandler?.();
  }

  if (data.csrf_token) {
    csrfToken = data.csrf_token;
  }

  if (!response.ok) {
    if (response.status === 401 && !CREDENTIAL_ENDPOINTS.includes(endpoint)) {
      csrfToken = null;
      unauthorizedHandler?.();
    }
    const err = new Error(friendlyError(response.status, data)) as any;
    err.status = response.status;
    throw err;
  }

  return data as T;
}

export const api = {
  // Auth & Session
  getMe: async (): Promise<UserInfo> => {
    return request<UserInfo>("/api/auth/me");
  },

  login: async (identifier: string, password: string) => {
    return request<AuthResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ identifier, password }),
    });
  },

  register: async (data: { email: string; password: string; confirm_password: string; full_name: string }) => {
    return request<AuthResponse>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  logout: async () => {
    const res = await request<{ message: string }>("/api/auth/logout", { method: "POST" });
    csrfToken = null;
    return res;
  },

  changePassword: async (currentPassword: string, newPassword: string) => {
    return request<{ message: string }>("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
  },

  updateProfile: async (data: { full_name?: string; email?: string }) => {
    return request<{ message: string; full_name?: string; email?: string }>("/api/account/profile", {
      method: "PATCH",
      body: JSON.stringify(data),
    });
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
    return request<{ payment_id: string; status: string; expected_amount_ghs: string; detected_amount_ghs?: string; recipient?: string; reference?: string; rejection_reason?: string }>(
      `/api/payments/${encodeURIComponent(paymentId)}/screenshot`,
      { method: "POST", body: formData },
    );
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
  },

  testAdminProviderConnection: async () => {
    return request<{ status: string; connected: boolean; balance: number; currency: string; service_count: number; error: string | null }>("/api/admin/provider/test", { method: "POST" });
  }
};
