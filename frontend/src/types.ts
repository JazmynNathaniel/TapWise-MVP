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

export type TransitMode = "subway" | "bus" | "lirr" | "metro_north";

export type Ride = {
  id: number;
  payment_method_id: number;
  payment_method_label: string;
  transit_mode: TransitMode;
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
  rail_fare: RailFareEstimate | null;
};

export type TransitOptions = Record<TransitMode, Record<string, string[]>>;

export type RouteSummary = {
  transit_mode: TransitMode;
  line: string;
  stop_count: number;
  ride_count: number;
  is_frequent: boolean;
};

export type Arrival = {
  transit_mode: TransitMode;
  line: string;
  route_id: string;
  stop: string;
  stop_id: string;
  trip_id: string;
  direction: string;
  direction_id: number | null;
  arrival_time: string;
  minutes_until: number;
};

export type ArrivalResponse = {
  status: "ok" | "empty" | "partial" | "unavailable";
  message: string;
  generated_at: string;
  arrivals: Arrival[];
};

export type ServiceAlert = {
  id: string;
  transit_mode: TransitMode;
  line: string | null;
  route_ids: string[];
  title: string;
  description: string;
  effect: string;
  cause: string;
  active_periods: Array<{
    start: string | null;
    end: string | null;
  }>;
};

export type ServiceAlertResponse = {
  status: "ok" | "empty" | "partial" | "unavailable";
  message: string;
  generated_at: string;
  alerts: ServiceAlert[];
};

export type TravelStatus = {
  status: "in_service" | "service_alert" | "no_service" | "no_departures" | "unavailable";
  service_state: "in_service" | "service_alert" | "no_service" | "no_departures" | "unavailable";
  mode: TransitMode;
  line: string;
  origin: string;
  destination: string;
  timestamp: string;
  generated_at: string;
  message: string;
  arrivals_status: ArrivalResponse["status"];
  arrivals_message: string;
  arrivals: Arrival[];
  alerts_status: ServiceAlertResponse["status"];
  alerts_message: string;
  alerts: ServiceAlert[];
  blocking_alerts: ServiceAlert[];
};

export type RouteSuggestion = {
  mode: TransitMode;
  line: string;
  origin: string;
  destination: string;
  service_state: TravelStatus["service_state"];
  score: number;
  stop_count: number;
  message: string;
  next_arrivals: Arrival[];
  alerts: ServiceAlert[];
  blocking_alerts: ServiceAlert[];
  rail_fare: RailFareEstimate | null;
  counts_toward_cap: boolean;
};

export type RouteSuggestionResponse = {
  status: "ok" | "empty";
  generated_at: string;
  timestamp: string;
  origin: string;
  destination: string;
  message: string;
  fare_status: FareStatus | null;
  suggestions: RouteSuggestion[];
};

export type RailFareEstimate = {
  status: "ok" | "unavailable";
  mode: TransitMode;
  line: string;
  origin: string;
  destination: string;
  timestamp: string;
  currency: "USD";
  effective_date: string;
  message: string;
  origin_zone: number | null;
  destination_zone: number | null;
  peak_price: number | null;
  off_peak_price: number | null;
  estimated_price: number | null;
  estimated_period: "peak" | "off_peak" | "intermediate" | null;
  source_label: string;
  source_url: string;
};

export type FrequentRoute = {
  transit_mode: TransitMode;
  line: string;
  entry_stop: string;
  exit_stop: string;
  ride_count: number;
  last_used_at: string;
  notifications_enabled: boolean;
  alerts: ServiceAlert[];
  alert_status: string;
};

export type PersonalizedNotification = {
  id: string;
  transit_mode: TransitMode;
  line: string;
  entry_stop: string;
  title: string;
  message: string;
  created_at: string;
};

export type PersonalizedAlerts = {
  routes: FrequentRoute[];
  notifications: PersonalizedNotification[];
};

export type NotificationPreference = {
  id: number;
  transit_mode: TransitMode;
  transit_line: string;
  entry_stop: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
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
