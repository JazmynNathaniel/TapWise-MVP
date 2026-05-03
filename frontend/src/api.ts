import {
  AuthResponse,
  FareStatus,
  PaymentMethod,
  Recommendation,
  Ride
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:5000/api";

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
  createPaymentMethod(token: string, label: string) {
    return request<PaymentMethod>(
      "/payment-methods",
      {
        method: "POST",
        body: JSON.stringify({ label })
      },
      token
    );
  },
  getRides(token: string) {
    return request<Ride[]>("/rides", {}, token);
  },
  createRide(token: string, paymentMethodId: number, timestamp?: string) {
    return request<Ride>(
      "/rides",
      {
        method: "POST",
        body: JSON.stringify({
          payment_method_id: paymentMethodId,
          ...(timestamp ? { timestamp } : {})
        })
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
