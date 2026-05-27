export type User = {
  id: number;
  email: string;
  username: string;
};

export type AuthResponse = {
  token: string;
  user: User;
};

export type PaymentMethod = {
  id: number;
  label: string;
  payment_type: string;
  identifier_code: string;
  masked_details: string;
  created_at: string;
};

export type Ride = {
  id: number;
  payment_method_id: number;
  payment_method_label: string;
  transit_mode: string;
  transit_line: string;
  entry_stop: string;
  exit_stop: string;
  timestamp: string;
  created_at: string;
  counts_toward_cap: boolean;
  is_transfer: boolean;
  transfer_source_ride_id: number | null;
  transfer_expires_at: string | null;
  transfer_target_mode: string | null;
};

export type TransitOptions = {
  subway: Record<string, string[]>;
  bus: Record<string, string[]>;
};

export type TransferStatus = {
  available: boolean;
  source_ride_id: number | null;
  source_transit_mode: string | null;
  target_transit_mode: string | null;
  started_at: string | null;
  expires_at: string | null;
  seconds_remaining: number;
};

export type FareStatus = {
  payment_method_id: number;
  label: string;
  rides_taken: number;
  rides_remaining: number;
  cap_reached: boolean;
  window_start: string | null;
  window_end: string | null;
  free_rides_active: boolean;
  latest_ride_timestamp: string | null;
  transfer_rides_taken: number;
  active_transfer: TransferStatus;
};

export type RecommendationMethod = {
  payment_method_id: number;
  label: string;
  status: {
    rides_taken: number;
    rides_remaining: number;
    cap_reached: boolean;
    window_start: string | null;
    window_end: string | null;
    free_rides_active: boolean;
    latest_ride_timestamp: string | null;
    transfer_rides_taken: number;
    active_transfer: TransferStatus;
  };
};

export type Recommendation = {
  best_payment_method_id: number | null;
  message: string;
  warning: string | null;
  estimated_rides_until_free: number | null;
  methods: RecommendationMethod[];
};
