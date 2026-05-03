export type User = {
  id: number;
  email: string;
};

export type AuthResponse = {
  token: string;
  user: User;
};

export type PaymentMethod = {
  id: number;
  label: string;
  created_at: string;
};

export type Ride = {
  id: number;
  payment_method_id: number;
  payment_method_label: string;
  timestamp: string;
  created_at: string;
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
  };
};

export type Recommendation = {
  best_payment_method_id: number | null;
  message: string;
  warning: string | null;
  estimated_rides_until_free: number | null;
  methods: RecommendationMethod[];
};
