import { FormEvent, useEffect, useState } from "react";
import { api } from "./api";
import {
  FareStatus,
  PaymentMethod,
  Recommendation,
  Ride,
  TransitOptions,
  User
} from "./types";

const TOKEN_KEY = "tapwise_token";
const USER_KEY = "tapwise_user";
const PAYMENT_TYPE_OPTIONS = [
  { value: "visa", label: "Visa" },
  { value: "mastercard", label: "Mastercard" },
  { value: "amex", label: "American Express" },
  { value: "discover", label: "Discover" },
  { value: "omny", label: "OMNY Card" },
  { value: "apple_pay", label: "Apple Pay" },
  { value: "google_pay", label: "Google Pay" },
  { value: "other", label: "Other" }
];

type AuthMode = "login" | "register";

type PaymentFormState = {
  label: string;
  paymentType: string;
  identifierCode: string;
};

type RideFormState = {
  transitMode: "subway" | "bus";
  transitLine: string;
  entryStop: string;
  exitStop: string;
};

type RideTimingMode = "now" | "manual";

const emptyPaymentForm: PaymentFormState = {
  label: "",
  paymentType: "visa",
  identifierCode: ""
};

const emptyRideForm: RideFormState = {
  transitMode: "subway",
  transitLine: "",
  entryStop: "",
  exitStop: ""
};

function formatDate(value: string | null) {
  if (!value) {
    return "Not started";
  }

  return new Date(value).toLocaleString();
}

function digitsOnly(value: string) {
  return value.replace(/\D/g, "");
}

function format4DigitCode(value: string) {
  return digitsOnly(value).slice(0, 4);
}

function formatLocalDateInput(value: Date) {
  const year = value.getFullYear();
  const month = `${value.getMonth() + 1}`.padStart(2, "0");
  const day = `${value.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatLocalTimeInput(value: Date) {
  const hours = `${value.getHours()}`.padStart(2, "0");
  const minutes = `${value.getMinutes()}`.padStart(2, "0");
  return `${hours}:${minutes}`;
}

function createManualRideDateTime() {
  const now = new Date();
  return {
    date: formatLocalDateInput(now),
    time: formatLocalTimeInput(now)
  };
}

function validatePaymentForm(form: PaymentFormState) {
  if (!form.label.trim()) {
    return "Payment method name is required.";
  }
  if (!form.paymentType) {
    return "Payment type is required.";
  }
  if (form.identifierCode.length !== 4) {
    return "Identifier code must be exactly 4 numbers.";
  }

  return null;
}

function validateRideForm(form: RideFormState) {
  if (!form.transitLine) {
    return "Select a train or bus line.";
  }
  if (!form.entryStop) {
    return "Select the stop where you entered.";
  }
  if (!form.exitStop) {
    return "Select the stop where you exited.";
  }
  return null;
}

async function sha256Hex(value: string) {
  const encoded = new TextEncoder().encode(value);
  const buffer = await window.crypto.subtle.digest("SHA-256", encoded);
  return Array.from(new Uint8Array(buffer))
    .map((item) => item.toString(16).padStart(2, "0"))
    .join("");
}

function App() {
  const [mode, setMode] = useState<AuthMode>("register");
  const [email, setEmail] = useState("demo@tapwise.app");
  const [password, setPassword] = useState("password123");
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState<User | null>(() => {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as User) : null;
  });
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [rides, setRides] = useState<Ride[]>([]);
  const [selectedMethodId, setSelectedMethodId] = useState<number | null>(null);
  const [fareStatus, setFareStatus] = useState<FareStatus | null>(null);
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [paymentForm, setPaymentForm] = useState<PaymentFormState>(emptyPaymentForm);
  const [rideForm, setRideForm] = useState<RideFormState>(emptyRideForm);
  const [transitOptions, setTransitOptions] = useState<TransitOptions | null>(null);
  const [rideTimingMode, setRideTimingMode] = useState<RideTimingMode>("now");
  const [manualRideDate, setManualRideDate] = useState(() => createManualRideDateTime().date);
  const [manualRideTime, setManualRideTime] = useState(() => createManualRideDateTime().time);
  const [showPaymentDetails, setShowPaymentDetails] = useState(false);
  const [authError, setAuthError] = useState("");
  const [appError, setAppError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!token) {
      return;
    }

    void loadDashboard(token);
  }, [token]);

  useEffect(() => {
    if (!token || !selectedMethodId) {
      setFareStatus(null);
      return;
    }

    void api
      .getFareStatus(token, selectedMethodId)
      .then(setFareStatus)
      .catch((error: Error) => setAppError(error.message));
  }, [selectedMethodId, token]);

  useEffect(() => {
    if (!token) {
      return;
    }

    void api
      .getTransitOptions(token)
      .then((options) => {
        setTransitOptions(options);
      })
      .catch((error: Error) => setAppError(error.message));
  }, [token]);

  useEffect(() => {
    if (!transitOptions) {
      return;
    }

    setRideForm((current) => {
      const modeOptions = transitOptions[current.transitMode];
      const lines = Object.keys(modeOptions);
      const transitLine =
        current.transitLine && modeOptions[current.transitLine]
          ? current.transitLine
          : (lines[0] ?? "");
      const stops = transitLine ? modeOptions[transitLine] ?? [] : [];
      const entryStop =
        current.entryStop && stops.includes(current.entryStop)
          ? current.entryStop
          : (stops[0] ?? "");
      const exitStop =
        current.exitStop && stops.includes(current.exitStop)
          ? current.exitStop
          : (stops[1] ?? stops[0] ?? "");

      if (
        current.transitLine === transitLine &&
        current.entryStop === entryStop &&
        current.exitStop === exitStop
      ) {
        return current;
      }

      return {
        ...current,
        transitLine,
        entryStop,
        exitStop
      };
    });
  }, [transitOptions, rideForm.transitMode]);

  async function loadDashboard(activeToken: string) {
    try {
      setLoading(true);
      setAppError("");
      const [methods, rideItems, recommendationPayload] = await Promise.all([
        api.getPaymentMethods(activeToken),
        api.getRides(activeToken),
        api.getRecommendation(activeToken)
      ]);

      setPaymentMethods(methods);
      setRides(rideItems);
      setRecommendation(recommendationPayload);

      if (methods.length > 0) {
        const preferredId = recommendationPayload.best_payment_method_id ?? methods[0].id;
        setSelectedMethodId((current) => {
          if (current && methods.some((method) => method.id === current)) {
            return current;
          }
          return preferredId;
        });
      } else {
        setSelectedMethodId(null);
      }
    } catch (error) {
      setAppError((error as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleAuthSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      setAuthError("");
      const response =
        mode === "register"
          ? await api.register(email, password)
          : await api.login(email, password);

      localStorage.setItem(TOKEN_KEY, response.token);
      localStorage.setItem(USER_KEY, JSON.stringify(response.user));
      setToken(response.token);
      setUser(response.user);
      const options = await api.getTransitOptions(response.token);
      setTransitOptions(options);
    } catch (error) {
      setAuthError((error as Error).message);
    }
  }

  function handleLogout() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setToken(null);
    setUser(null);
    setPaymentMethods([]);
    setRides([]);
    setSelectedMethodId(null);
    setFareStatus(null);
    setRecommendation(null);
    setTransitOptions(null);
  }

  function updatePaymentForm<K extends keyof PaymentFormState>(
    key: K,
    value: PaymentFormState[K]
  ) {
    setPaymentForm((current) => ({ ...current, [key]: value }));
  }

  function updateRideForm<K extends keyof RideFormState>(
    key: K,
    value: RideFormState[K]
  ) {
    setRideForm((current) => {
      const next = { ...current, [key]: value };
      if (key === "transitMode") {
        return {
          transitMode: value as RideFormState["transitMode"],
          transitLine: "",
          entryStop: "",
          exitStop: ""
        };
      }
      if (key === "transitLine") {
        const stops =
          transitOptions?.[current.transitMode][value as RideFormState["transitLine"]] ?? [];
        next.entryStop = stops[0] ?? "";
        next.exitStop = stops[1] ?? stops[0] ?? "";
      }
      return next;
    });
  }

  async function handleCreatePaymentMethod(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      return;
    }

    const validationError = validatePaymentForm(paymentForm);
    if (validationError) {
      setAppError(validationError);
      return;
    }

    try {
      setAppError("");
      const fingerprintSource = [
        paymentForm.paymentType,
        paymentForm.label.trim().toUpperCase(),
        paymentForm.identifierCode
      ].join("|");
      const detailsFingerprint = await sha256Hex(fingerprintSource);

      const createdMethod = await api.createPaymentMethod(token, {
        label: paymentForm.label.trim(),
        payment_type: paymentForm.paymentType,
        identifier_code: paymentForm.identifierCode,
        details_fingerprint: detailsFingerprint
      });

      setPaymentMethods((current) => [...current, createdMethod]);
      setSelectedMethodId(createdMethod.id);
      setPaymentForm(emptyPaymentForm);
      setShowPaymentDetails(false);
      await loadDashboard(token);
    } catch (error) {
      setAppError((error as Error).message);
    }
  }

  async function handleAddRide() {
    if (!token || !selectedMethodId) {
      return;
    }

    const validationError = validateRideForm(rideForm);
    if (validationError) {
      setAppError(validationError);
      return;
    }

    try {
      const manualTimestamp =
        rideTimingMode === "manual" && manualRideDate && manualRideTime
          ? new Date(`${manualRideDate}T${manualRideTime}`).toISOString()
          : undefined;
      await api.createRide(token, {
        payment_method_id: selectedMethodId,
        transit_mode: rideForm.transitMode,
        transit_line: rideForm.transitLine,
        entry_stop: rideForm.entryStop,
        exit_stop: rideForm.exitStop,
        ...(manualTimestamp ? { timestamp: manualTimestamp } : {})
      });
      const nextManualDateTime = createManualRideDateTime();
      setRideTimingMode("now");
      setManualRideDate(nextManualDateTime.date);
      setManualRideTime(nextManualDateTime.time);
      setRideForm((current) => ({ ...emptyRideForm, transitMode: current.transitMode }));
      await loadDashboard(token);
      const status = await api.getFareStatus(token, selectedMethodId);
      setFareStatus(status);
    } catch (error) {
      setAppError((error as Error).message);
    }
  }

  if (!token || !user) {
    return (
      <main className="shell auth-shell">
        <section className="hero-card">
          <p className="eyebrow">TapWise</p>
          <h1>NYC fare optimization for OMNY riders.</h1>
          <p className="lede">
            Track rides by card or device, model the 7-day cap window, and know
            which payment method gets you to free rides fastest.
          </p>
        </section>

        <section className="panel auth-panel">
          <div className="mode-toggle">
            <button
              type="button"
              className={mode === "register" ? "active" : ""}
              onClick={() => setMode("register")}
            >
              Register
            </button>
            <button
              type="button"
              className={mode === "login" ? "active" : ""}
              onClick={() => setMode("login")}
            >
              Login
            </button>
          </div>

          <form onSubmit={handleAuthSubmit} className="stack">
            <label>
              Email
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>
            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>
            {authError ? <p className="error">{authError}</p> : null}
            <button type="submit" className="primary-button">
              {mode === "register" ? "Create account" : "Sign in"}
            </button>
          </form>
        </section>
      </main>
    );
  }

  const availableLines = transitOptions
    ? Object.keys(transitOptions[rideForm.transitMode])
    : [];
  const availableStops =
    transitOptions && rideForm.transitLine
      ? transitOptions[rideForm.transitMode][rideForm.transitLine] ?? []
      : [];

  const selectedMethod = paymentMethods.find((method) => method.id === selectedMethodId) ?? null;
  const progress = fareStatus ? (fareStatus.rides_taken / 12) * 100 : 0;

  return (
    <main className="shell dashboard-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">TapWise Dashboard</p>
          <h1>Welcome back, {user.email}</h1>
        </div>
        <button onClick={handleLogout} className="secondary-button">
          Logout
        </button>
      </header>

      {appError ? <div className="banner error">{appError}</div> : null}

      <section className="grid">
        <article className="panel recommendation-panel">
          <p className="panel-label">Recommendation</p>
          <h2>{recommendation?.message ?? "Loading recommendation..."}</h2>
          <p className="muted">
            {recommendation?.warning ?? "TapWise recalculates this after every ride."}
          </p>
        </article>

        <article className="panel payment-panel">
          <div className="panel-header-row">
            <p className="panel-label">Payment Methods</p>
            <button
              type="button"
              className="secondary-button ghost-button"
              onClick={() => setShowPaymentDetails((current) => !current)}
            >
              {showPaymentDetails ? "Hide details" : "Show details"}
            </button>
          </div>

          <div className="selector-list method-list">
            {paymentMethods.map((method) => (
              <button
                key={method.id}
                className={method.id === selectedMethodId ? "selector active selector-card" : "selector selector-card"}
                onClick={() => setSelectedMethodId(method.id)}
              >
                <strong>{method.label}</strong>
                <span>{method.masked_details}</span>
              </button>
            ))}
          </div>

          <form onSubmit={handleCreatePaymentMethod} className="payment-form">
            <div className="form-grid">
              <label>
                Payment method name
                <input
                  value={paymentForm.label}
                  onChange={(event) => updatePaymentForm("label", event.target.value)}
                  placeholder="Work Visa, Personal OMNY, Apple Pay"
                  required
                />
              </label>
              <label>
                Payment type
                <select
                  value={paymentForm.paymentType}
                  onChange={(event) => updatePaymentForm("paymentType", event.target.value)}
                >
                  {PAYMENT_TYPE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                4-digit identifier code
                <input
                  type={showPaymentDetails ? "text" : "password"}
                  inputMode="numeric"
                  value={paymentForm.identifierCode}
                  onChange={(event) =>
                    updatePaymentForm("identifierCode", format4DigitCode(event.target.value))
                  }
                  placeholder="4821"
                  required
                />
              </label>
            </div>
            <p className="muted helper-copy">
              Please enter a 4-digit identifier code for this card or device. Do not
              enter the last 4 digits of your card number. Create your own code and
              name the payment method accordingly, such as "Work Visa" with code
              "4821". TapWise does not store, want, or need your actual card
              information to track rides and fare caps.
            </p>
            <button type="submit" className="primary-button">
              Save payment method
            </button>
          </form>
        </article>

        <article className="panel progress-panel">
          <p className="panel-label">Fare Cap Status</p>
          <h2>
            {fareStatus?.free_rides_active
              ? "Free rides active"
              : `${fareStatus?.rides_remaining ?? 12} rides left`}
          </h2>
          <p className="muted">
            {selectedMethod
              ? `Tracking ${selectedMethod.label} (${selectedMethod.masked_details})`
              : "Select a payment method to see status."}
          </p>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${progress}%` }} />
          </div>
          <div className="progress-meta">
            <span>{fareStatus?.rides_taken ?? 0} / 12 paid rides</span>
            <span>Window ends {formatDate(fareStatus?.window_end ?? null)}</span>
          </div>
          {selectedMethod ? (
            <div className="detail-chip-row">
              <span className="detail-chip">{selectedMethod.payment_type.replace("_", " ").toUpperCase()}</span>
              <span className="detail-chip">Code: {selectedMethod.identifier_code}</span>
            </div>
          ) : null}
        </article>

        <article className="panel">
          <p className="panel-label">Ride Logging</p>
          <div className="ride-actions">
            <div className="form-grid">
              <label>
                Transit mode
                <select
                  value={rideForm.transitMode}
                  onChange={(event) =>
                    updateRideForm(
                      "transitMode",
                      event.target.value as RideFormState["transitMode"]
                    )
                  }
                >
                  <option value="subway">Subway</option>
                  <option value="bus">Bus</option>
                </select>
              </label>
              <label>
                Line
                <select
                  value={rideForm.transitLine}
                  onChange={(event) => updateRideForm("transitLine", event.target.value)}
                >
                  <option value="">Select a line</option>
                  {availableLines.map((line) => (
                    <option key={line} value={line}>
                      {line}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Entry stop
                <select
                  value={rideForm.entryStop}
                  onChange={(event) => updateRideForm("entryStop", event.target.value)}
                >
                  <option value="">Select entry stop</option>
                  {availableStops.map((stop) => (
                    <option key={stop} value={stop}>
                      {stop}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Exit stop
                <select
                  value={rideForm.exitStop}
                  onChange={(event) => updateRideForm("exitStop", event.target.value)}
                >
                  <option value="">Select exit stop</option>
                  {availableStops.map((stop) => (
                    <option key={stop} value={stop}>
                      {stop}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="timing-panel">
              <div className="mode-toggle ride-timing-toggle">
                <button
                  type="button"
                  className={rideTimingMode === "now" ? "active" : ""}
                  onClick={() => setRideTimingMode("now")}
                >
                  Ride happened now
                </button>
                <button
                  type="button"
                  className={rideTimingMode === "manual" ? "active" : ""}
                  onClick={() => setRideTimingMode("manual")}
                >
                  Pick date and time
                </button>
              </div>
              {rideTimingMode === "manual" ? (
                <div className="manual-time-grid">
                  <label>
                    Ride date
                    <input
                      type="date"
                      value={manualRideDate}
                      onChange={(event) => setManualRideDate(event.target.value)}
                    />
                  </label>
                  <label>
                    Ride time
                    <input
                      type="time"
                      value={manualRideTime}
                      onChange={(event) => setManualRideTime(event.target.value)}
                    />
                  </label>
                </div>
              ) : (
                <p className="muted helper-copy">
                  Tap save to log this ride with the current local date and time.
                </p>
              )}
              <button
                className={rideTimingMode === "now" ? "primary-button" : "secondary-button"}
                onClick={() => void handleAddRide()}
                type="button"
                disabled={!selectedMethodId}
              >
                {rideTimingMode === "now" ? "Add ride now" : "Save dated ride"}
              </button>
            </div>
          </div>
        </article>

        <article className="panel ride-history">
          <p className="panel-label">Ride History</p>
          {loading ? <p className="muted">Loading rides...</p> : null}
          <div className="ride-list">
            {rides.map((ride) => (
              <div className="ride-row" key={ride.id}>
                <div>
                  <strong>{ride.payment_method_label}</strong>
                  <p>{formatDate(ride.timestamp)}</p>
                  <p>
                    {ride.transit_mode.toUpperCase()} {ride.transit_line}: {ride.entry_stop} to{" "}
                    {ride.exit_stop}
                  </p>
                </div>
                <span>Ride #{ride.id}</span>
              </div>
            ))}
            {rides.length === 0 ? <p className="muted">No rides logged yet.</p> : null}
          </div>
        </article>
      </section>
    </main>
  );
}

export default App;
