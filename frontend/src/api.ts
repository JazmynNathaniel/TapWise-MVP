import {
  AuthResponse,
  FareStatus,
  PaymentMethod,
  Recommendation,
  Ride,
  TransitOptions
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

type PaymentMethodPayload = {
  label: string;
  payment_type: string;
  cardholder_name: string;
  last4: string;
  details_fingerprint: string;
};

type RidePayload = {
  payment_method_id: number;
  transit_mode: string;
  transit_line: string;
  entry_stop: string;
  exit_stop: string;
  timestamp?: string;
};

async function request<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {})
    }
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error ?? "Request failed.");
  }

  return response.json() as Promise<T>;
}

export const api = {
  register(email: string, password: string) {
    return request<AuthResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password })
    });
  },
  login(email: string, password: string) {
    return request<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password })
    });
  },
  getPaymentMethods(token: string) {
    return request<PaymentMethod[]>("/payment-methods", {}, token);
  },
  createPaymentMethod(token: string, payload: PaymentMethodPayload) {
    return request<PaymentMethod>(
      "/payment-methods",
      {
        method: "POST",
        body: JSON.stringify(payload)
      },
      token
    );
  },
  getRides(token: string) {
    return request<Ride[]>("/rides", {}, token);
  },
  getTransitOptions(token: string) {
    return request<TransitOptions>("/transit-options", {}, token);
  },
  createRide(token: string, payload: RidePayload) {
    return request<Ride>(
      "/rides",
      {
        method: "POST",
        body: JSON.stringify(payload)
      },
      token
    );
  },
  getFareStatus(token: string, paymentMethodId: number) {
    return request<FareStatus>(`/fare-status/${paymentMethodId}`, {}, token);
  },
  getRecommendation(token: string) {
    return request<Recommendation>("/recommendation", {}, token);
  }
};
