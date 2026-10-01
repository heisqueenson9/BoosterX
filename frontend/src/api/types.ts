export interface UserInfo {
  authenticated: boolean;
  user_id?: string;
  full_name?: string;
  role?: string;
  email?: string;
  phone?: string;
  csrf_token?: string;
}

export interface AuthResponse extends UserInfo {
  redirect_path: string;
}

export interface PlatformItem {
  id: number;
  name: string;
}

export interface ServiceItem {
  id: number;
  platform: string;
  category: string;
  name: string;
  description: string;
  min_quantity: number;
  max_quantity: number;
  price_per_1000_ghs: string;
  refill_available: boolean;
  speed?: string;
}

export interface OrderPreviewQuote {
  service_cost_ghs: string;
  processing_fee_ghs: string;
  total_ghs: string;
  balance_ghs: string;
  sufficient: boolean;
}

export interface OrderEventItem {
  id: number;
  event_type: string;
  description: string;
  created_at: string;
}

export interface OrderDetail {
  id: number;
  public_order_id: string;
  platform: string;
  service_id: number;
  service_name: string;
  target: string;
  quantity: number;
  charge_ghs: string;
  status: string;
  start_count: number;
  remains: number;
  progress_percent: number;
  needs_attention?: boolean;
  created_at: string;
  completed_at?: string;
  events?: OrderEventItem[];
}

export interface OrderListResponse {
  orders: OrderDetail[];
  total: number;
  page: number;
  per_page: number;
}

export interface PaymentItem {
  payment_id: string;
  amount_ghs: string;
  network: string;
  status: string;
  reference?: string;
  detected_amount_ghs?: string;
  recipient?: string;
  rejection_reason?: string;
  created_at: string;
}

export interface WalletSummary {
  available_balance: string;
  total_spent: string;
  total_deposited: string;
}

export interface LedgerTxItem {
  id: number;
  type: string;
  amount_ghs: string;
  status: string;
  reference?: string;
  description?: string;
  balance_before: string;
  balance_after: string;
  created_at: string;
}

export interface AdminOverviewStats {
  revenue_24h_ghs: string;
  active_orders: number;
  pending_payment_reviews: number;
  total_users: number;
  failed_orders: number;
  total_orders: number;
  provider_balance: string;
}

export interface AdminAuditLogItem {
  id: number;
  admin_id: number;
  action: string;
  target_type: string;
  target_id: string;
  old_value?: string;
  new_value?: string;
  created_at: string;
}
