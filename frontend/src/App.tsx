import { FormEvent, useEffect, useState } from "react";
import { api } from "./api";
import { FareStatus, PaymentMethod, Recommendation, Ride, User } from "./types";

const TOKEN_KEY = "tapwise_token";
const USER_KEY = "tapwise_user";

type AuthMode = "login" | "register";

function formatDate(value: string | null) {
  if (!value) {
    return "Not started";
  }

  return new Date(value).toLocaleString();
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
  const [newMethodLabel, setNewMethodLabel] = useState("");
  const [manualRideTimestamp, setManualRideTimestamp] = useState("");
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
        const preferredId =
          recommendationPayload.best_payment_method_id ?? methods[0].id;
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
  }

  async function handleCreatePaymentMethod(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !newMethodLabel.trim()) {
      return;
    }

    try {
      await api.createPaymentMethod(token, newMethodLabel.trim());
      setNewMethodLabel("");
      await loadDashboard(token);
    } catch (error) {
      setAppError((error as Error).message);
    }
  }

  async function handleAddRide(useCurrentTime: boolean) {
    if (!token || !selectedMethodId) {
      return;
    }

    try {
      const timestamp = useCurrentTime
        ? undefined
        : manualRideTimestamp
          ? new Date(manualRideTimestamp).toISOString()
          : undefined;
      await api.createRide(token, selectedMethodId, timestamp);
      setManualRideTimestamp("");
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

        <article className="panel">
          <p className="panel-label">Payment Methods</p>
          <div className="selector-list">
            {paymentMethods.map((method) => (
              <button
                key={method.id}
                className={method.id === selectedMethodId ? "selector active" : "selector"}
                onClick={() => setSelectedMethodId(method.id)}
              >
                {method.label}
              </button>
            ))}
          </div>

          <form onSubmit={handleCreatePaymentMethod} className="inline-form">
            <input
              value={newMethodLabel}
              onChange={(event) => setNewMethodLabel(event.target.value)}
              placeholder="Add Apple Pay, Visa 1234, OMNY card..."
            />
            <button type="submit" className="primary-button">
              Add
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
              ? `Tracking ${selectedMethod.label}`
              : "Select a payment method to see status."}
          </p>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${progress}%` }} />
          </div>
          <div className="progress-meta">
            <span>{fareStatus?.rides_taken ?? 0} / 12 paid rides</span>
            <span>Window ends {formatDate(fareStatus?.window_end ?? null)}</span>
          </div>
        </article>

        <article className="panel">
          <p className="panel-label">Ride Logging</p>
          <div className="ride-actions">
            <button
              className="primary-button"
              onClick={() => void handleAddRide(true)}
              disabled={!selectedMethodId}
            >
              Add ride now
            </button>
            <div className="inline-form">
              <input
                type="datetime-local"
                value={manualRideTimestamp}
                onChange={(event) => setManualRideTimestamp(event.target.value)}
              />
              <button
                className="secondary-button"
                onClick={() => void handleAddRide(false)}
                type="button"
                disabled={!selectedMethodId}
              >
                Save manual ride
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
