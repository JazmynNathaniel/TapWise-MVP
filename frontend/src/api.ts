import {
  AuthResponse,
  ArrivalResponse,
  FareStatus,
  NotificationPreference,
  PaymentMethod,
  PersonalizedAlerts,
  RailFareEstimate,
  Recommendation,
  Ride,
  RouteSuggestionResponse,
  RouteSummary,
  ServiceAlertResponse,
  TransitOptions,
  TravelTimeMode,
  TravelStatus
} from "./types";

function normalizeApiBase(rawValue?: string) {
  const value = (rawValue || "/api").replace(/\/+$/, "");

  return value.endsWith("/api") ? value : `${value}/api`;
}

const API_BASE = normalizeApiBase(import.meta.env.VITE_API_BASE_URL);
const GENERIC_ERROR_MESSAGE = "Something went wrong on our side. Please try again in a moment.";
const NETWORK_ERROR_MESSAGE =
  "TapWise is having trouble connecting. Please check your connection and try again.";
const SLOW_RESPONSE_MESSAGE =
  "TapWise is taking longer than expected. Please try again in a moment.";
const REQUEST_TIMEOUT_MS = 10000;

type PaymentMethodPayload = {
  label: string;
  payment_type: string;
  identifier_code: string;
};

type RidePayload = {
  payment_method_id: number;
  transit_mode: string;
  transit_line: string;
  entry_stop: string;
  exit_stop: string;
  timestamp?: string;
};

type NotificationPreferencePayload = {
  transit_mode: string;
  transit_line: string;
  entry_stop?: string;
  enabled: boolean;
};

function friendlyErrorMessage(path: string, status: number) {
  if (path.startsWith("/auth/login") && (status === 400 || status === 401)) {
    return "Incorrect login information.";
  }
  if (path.startsWith("/auth/register")) {
    if (status === 409) {
      return "We couldn't create that account. Please try different details.";
    }
    if (status === 400) {
      return "Please check your sign-up details and try again.";
    }
  }
  if (status === 400) {
    return "Please check your information and try again.";
  }
  if (status === 401) {
    return "Your session has ended. Please sign in again.";
  }
  if (status === 403) {
    return "You do not have access to that action.";
  }
  if (status === 404) {
    return "We couldn't find that information.";
  }
  if (status === 409) {
    return "That information is already in use.";
  }
  if (status === 429) {
    return "Please wait a moment and try again.";
  }
  return GENERIC_ERROR_MESSAGE;
}

async function request<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  let response: Response;
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers ?? {})
      }
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(SLOW_RESPONSE_MESSAGE);
    }
    throw new Error(NETWORK_ERROR_MESSAGE);
  } finally {
    window.clearTimeout(timeoutId);
  }

  if (!response.ok) {
    throw new Error(friendlyErrorMessage(path, response.status));
  }

  return response.json() as Promise<T>;
}

export const api = {
  register(username: string, email: string, password: string) {
    return request<AuthResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, email, password })
    });
  },
  login(email: string, password: string) {
    return request<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password })
    });
  },
  logout(token: string) {
    return request<{ message: string }>("/auth/logout", { method: "POST" }, token);
  },
  deleteProfile(token: string) {
    return request<{ message: string }>("/auth/profile", { method: "DELETE" }, token);
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
  getRoutes(token: string, mode?: string) {
    const query = mode ? `?mode=${encodeURIComponent(mode)}` : "";
    return request<{ routes: RouteSummary[] }>(`/routes${query}`, {}, token);
  },
  getArrivals(token: string, mode: string, line: string, stop: string) {
    const query = new URLSearchParams({
      mode,
      line,
      stop,
      limit: "12"
    });
    return request<ArrivalResponse>(`/arrivals?${query.toString()}`, {}, token);
  },
  getServiceAlerts(token: string, mode: string, line: string) {
    const query = new URLSearchParams({
      mode,
      line
    });
    return request<ServiceAlertResponse>(`/service-alerts?${query.toString()}`, {}, token);
  },
  getTravelStatus(
    token: string,
    mode: string,
    line: string,
    origin: string,
    destination: string,
    timeMode: TravelTimeMode,
    timestamp?: string
  ) {
    const query = new URLSearchParams({
      mode,
      line,
      origin,
      destination,
      time_mode: timeMode,
      limit: "12"
    });
    if (timestamp) {
      query.set("timestamp", timestamp);
    }
    return request<TravelStatus>(`/travel-status?${query.toString()}`, {}, token);
  },
  getRouteSuggestions(
    token: string,
    origin: string,
    destination: string,
    timeMode: TravelTimeMode,
    timestamp?: string,
    mode?: string,
    line?: string,
    paymentMethodId?: number | null
  ) {
    const query = new URLSearchParams({
      origin,
      destination,
      time_mode: timeMode,
      limit: "4"
    });
    if (timestamp) {
      query.set("timestamp", timestamp);
    }
    if (mode) {
      query.set("mode", mode);
    }
    if (line) {
      query.set("line", line);
    }
    if (paymentMethodId) {
      query.set("payment_method_id", `${paymentMethodId}`);
    }
    return request<RouteSuggestionResponse>(`/route-suggestions?${query.toString()}`, {}, token);
  },
  getRailFareEstimate(
    token: string,
    mode: string,
    line: string,
    origin: string,
    destination: string,
    timestamp?: string
  ) {
    const query = new URLSearchParams({
      mode,
      line,
      origin,
      destination
    });
    if (timestamp) {
      query.set("timestamp", timestamp);
    }
    return request<RailFareEstimate>(`/rail-fare-estimate?${query.toString()}`, {}, token);
  },
  getPersonalizedAlerts(token: string) {
    return request<PersonalizedAlerts>("/personalized-alerts", {}, token);
  },
  updateNotificationPreference(token: string, payload: NotificationPreferencePayload) {
    return request<NotificationPreference>(
      "/notification-preferences",
      {
        method: "POST",
        body: JSON.stringify(payload)
      },
      token
    );
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
