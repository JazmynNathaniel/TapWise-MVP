import { FormEvent, useEffect, useRef, useState, type CSSProperties } from "react";
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
const HAS_AUTHENTICATED_BEFORE_KEY = "tapwise_has_authenticated_before";
const THEME_KEY = "tapwise_theme";
const SILENCED_TRANSFER_NOTIFICATIONS_KEY = "tapwise_silenced_transfer_notifications";
const FARE_CAP_RIDES = 12;
const TRANSFER_WINDOW_SECONDS = 2 * 60 * 60;
const TRANSFER_REMINDER_SECONDS = 30 * 60;
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
type ThemeMode = "dark" | "light";

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

type ActiveTransferNotice = {
  paymentMethodId: number;
  paymentMethodLabel: string;
  sourceRideId: number | null;
  sourceTransitMode: string | null;
  targetTransitMode: string | null;
  startedAt: string | null;
  expiresAt: string;
  secondsRemaining: number;
  isSelectedMethod: boolean;
};

function getTransferNoticeKey(notice: ActiveTransferNotice) {
  return [
    notice.paymentMethodId,
    notice.sourceRideId ?? notice.startedAt ?? notice.expiresAt
  ].join(":");
}

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

function formatShortDate(value: string | null) {
  if (!value) {
    return "No rides yet";
  }

  return new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  });
}

function getPaymentTypeLabel(value: string) {
  return PAYMENT_TYPE_OPTIONS.find((option) => option.value === value)?.label ?? value;
}

function formatPaymentType(value: string) {
  return getPaymentTypeLabel(value).toUpperCase();
}

function formatTransitLabel(value: string | null) {
  if (value === "subway") {
    return "train";
  }
  if (value === "bus") {
    return "bus";
  }
  return "ride";
}

function formatCountdown(totalSeconds: number) {
  const seconds = Math.max(0, totalSeconds);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainingSeconds = seconds % 60;

  return [hours, minutes, remainingSeconds]
    .map((part) => `${part}`.padStart(2, "0"))
    .join(":");
}

function getSecondsUntil(value: string | null, nowMs: number) {
  if (!value) {
    return 0;
  }

  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) {
    return 0;
  }

  return Math.max(0, Math.floor((timestamp - nowMs) / 1000));
}

function getActiveTransferNotice(
  recommendation: Recommendation | null,
  selectedMethodId: number | null,
  nowMs: number
): ActiveTransferNotice | null {
  const notices =
    recommendation?.methods
      .map((method) => {
        const transfer = method.status.active_transfer;
        const secondsRemaining = getSecondsUntil(transfer.expires_at, nowMs);

        if (!transfer.available || !transfer.expires_at || secondsRemaining <= 0) {
          return null;
        }

        return {
          paymentMethodId: method.payment_method_id,
          paymentMethodLabel: method.label,
          sourceRideId: transfer.source_ride_id,
          sourceTransitMode: transfer.source_transit_mode,
          targetTransitMode: transfer.target_transit_mode,
          startedAt: transfer.started_at,
          expiresAt: transfer.expires_at,
          secondsRemaining,
          isSelectedMethod: method.payment_method_id === selectedMethodId
        };
      })
      .filter((notice): notice is ActiveTransferNotice => Boolean(notice)) ?? [];

  if (notices.length === 0) {
    return null;
  }

  const selectedNotice = notices.find((notice) => notice.isSelectedMethod);
  if (selectedNotice) {
    return selectedNotice;
  }

  return notices.reduce((soonest, notice) =>
    notice.secondsRemaining < soonest.secondsRemaining ? notice : soonest
  );
}

function buildTransferReminderMessage(notice: ActiveTransferNotice, reminderBucket: number) {
  const targetLabel = formatTransitLabel(notice.targetTransitMode);
  const countdown = formatCountdown(notice.secondsRemaining);

  if (!notice.isSelectedMethod) {
    return `Transfer is on ${notice.paymentMethodLabel}. Switch back for your next ${targetLabel} tap; ${countdown} left.`;
  }

  if (reminderBucket === 0) {
    return `Keep using ${notice.paymentMethodLabel} for your next ${targetLabel} tap. Switching cards will make it count as paid.`;
  }

  return `Reminder: free ${targetLabel} transfer on ${notice.paymentMethodLabel} expires in ${countdown}.`;
}

function hydrateSilencedTransferKeys() {
  const rawValue = localStorage.getItem(SILENCED_TRANSFER_NOTIFICATIONS_KEY);
  if (!rawValue) {
    return new Set<string>();
  }

  try {
    const parsed = JSON.parse(rawValue);
    if (!Array.isArray(parsed)) {
      return new Set<string>();
    }

    return new Set(parsed.filter((item): item is string => typeof item === "string"));
  } catch {
    return new Set<string>();
  }
}

function persistSilencedTransferKeys(keys: Set<string>) {
  localStorage.setItem(
    SILENCED_TRANSFER_NOTIFICATIONS_KEY,
    JSON.stringify(Array.from(keys))
  );
}

function getStoredTheme(): ThemeMode {
  return localStorage.getItem(THEME_KEY) === "light" ? "light" : "dark";
}

function NycBackdrop() {
  return (
    <div className="nyc-backdrop" aria-hidden="true">
      <div className="route-line-map">
        <span className="route-line route-line-blue" />
        <span className="route-line route-line-orange" />
        <span className="route-line route-line-green" />
        <span className="route-line route-line-yellow" />
      </div>

      <svg className="liberty-visual" viewBox="0 0 160 260" role="img">
        <path className="liberty-glow" d="M71 31 88 31 93 61 119 76 97 84 112 109 88 99 82 130 70 130 64 99 40 109 55 84 33 76 59 61Z" />
        <path className="liberty-flame" d="M74 4c11 15 7 29-6 40 2-14-9-21 6-40Z" />
        <path className="liberty-torch" d="M66 36h14l-2 75H68Z" />
        <path className="liberty-arm" d="M72 98c-19 10-28 32-29 66h18c1-23 7-38 20-46Z" />
        <path className="liberty-body" d="M59 122h44l12 116H47Z" />
        <path className="liberty-face" d="M66 77h31l-4 31H70Z" />
        <path className="liberty-crown" d="M63 77 72 48 77 75 85 44 89 75 104 50 96 81Z" />
        <path className="liberty-base" d="M35 238h92l11 19H24Z" />
      </svg>

      <svg className="bridge-visual" viewBox="0 0 640 260" role="img">
        <path className="bridge-deck" d="M18 192h604" />
        <path className="bridge-cable" d="M22 186C133 58 238 58 320 186C402 58 507 58 618 186" />
        <path className="bridge-cable secondary" d="M20 207C136 110 240 110 320 207C400 110 504 110 620 207" />
        <path className="bridge-tower" d="M146 190V72h58v118M436 190V72h58v118" />
        <path className="bridge-arch" d="M156 129h38M446 129h38" />
        <path className="bridge-arch" d="M156 94h38M446 94h38" />
        {Array.from({ length: 19 }, (_, index) => (
          <path
            key={index}
            className="bridge-suspender"
            d={`M${48 + index * 30} ${192}V${134 + Math.abs(9 - index) * 6}`}
          />
        ))}
      </svg>

      <div className="skyline-strip">
        {Array.from({ length: 18 }, (_, index) => (
          <span key={index} style={{ "--height": `${42 + (index % 6) * 16}px` } as CSSProperties} />
        ))}
      </div>
    </div>
  );
}

function ThemeToggle({
  theme,
  onThemeChange
}: {
  theme: ThemeMode;
  onThemeChange: (theme: ThemeMode) => void;
}) {
  return (
    <div className="theme-toggle" role="group" aria-label="Color theme">
      <button
        type="button"
        className={theme === "dark" ? "active" : ""}
        onClick={() => onThemeChange("dark")}
      >
        Night
      </button>
      <button
        type="button"
        className={theme === "light" ? "active" : ""}
        onClick={() => onThemeChange("light")}
      >
        Day
      </button>
    </div>
  );
}

function deriveUsernameFromEmail(email: string) {
  return email.split("@", 1)[0] || "there";
}

function hydrateStoredUser(rawValue: string | null): User | null {
  if (!rawValue) {
    return null;
  }

  const parsed = JSON.parse(rawValue) as Partial<User>;
  if (!parsed.id || !parsed.email) {
    return null;
  }

  return {
    id: parsed.id,
    email: parsed.email,
    username: parsed.username || deriveUsernameFromEmail(parsed.email)
  };
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
  const [theme, setTheme] = useState<ThemeMode>(() => getStoredTheme());
  const [mode, setMode] = useState<AuthMode>("register");
  const [username, setUsername] = useState("tapwise_rider");
  const [email, setEmail] = useState("demo@tapwise.app");
  const [password, setPassword] = useState("password123");
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState<User | null>(() => hydrateStoredUser(localStorage.getItem(USER_KEY)));
  const [hasAuthenticatedBefore, setHasAuthenticatedBefore] = useState(
    () => localStorage.getItem(HAS_AUTHENTICATED_BEFORE_KEY) === "true"
  );
  const [isFirstAuthenticatedSession, setIsFirstAuthenticatedSession] = useState(false);
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
  const [currentTimeMs, setCurrentTimeMs] = useState(() => Date.now());
  const [transferReminder, setTransferReminder] = useState("");
  const [silencedTransferKeys, setSilencedTransferKeys] = useState(() =>
    hydrateSilencedTransferKeys()
  );
  const lastTransferReminderKey = useRef<string | null>(null);
  const lastActiveTransferKey = useRef<string | null>(null);
  const activeTransferNotice = getActiveTransferNotice(
    recommendation,
    selectedMethodId,
    currentTimeMs
  );
  const activeTransferKey = activeTransferNotice
    ? getTransferNoticeKey(activeTransferNotice)
    : null;
  const transferNotificationsOff = activeTransferKey
    ? silencedTransferKeys.has(activeTransferKey)
    : false;

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

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

  useEffect(() => {
    if (!activeTransferNotice) {
      return;
    }

    const timerId = window.setInterval(() => {
      setCurrentTimeMs(Date.now());
    }, 1000);

    return () => window.clearInterval(timerId);
  }, [
    activeTransferNotice?.expiresAt,
    activeTransferNotice?.paymentMethodId,
    activeTransferNotice?.sourceRideId
  ]);

  useEffect(() => {
    const previousKey = lastActiveTransferKey.current;
    if (previousKey && previousKey !== activeTransferKey) {
      setSilencedTransferKeys((current) => {
        if (!current.has(previousKey)) {
          return current;
        }

        const next = new Set(current);
        next.delete(previousKey);
        persistSilencedTransferKeys(next);
        return next;
      });
    }

    lastActiveTransferKey.current = activeTransferKey;
  }, [activeTransferKey]);

  useEffect(() => {
    if (!activeTransferNotice || transferNotificationsOff) {
      lastTransferReminderKey.current = null;
      setTransferReminder("");
      return;
    }

    const elapsedSeconds = Math.max(
      0,
      TRANSFER_WINDOW_SECONDS - activeTransferNotice.secondsRemaining
    );
    const reminderBucket = Math.min(
      3,
      Math.floor(elapsedSeconds / TRANSFER_REMINDER_SECONDS)
    );
    const reminderKey = [
      activeTransferNotice.paymentMethodId,
      activeTransferNotice.sourceRideId ?? activeTransferNotice.startedAt,
      reminderBucket,
      activeTransferNotice.isSelectedMethod ? "selected" : "other"
    ].join(":");

    if (lastTransferReminderKey.current === reminderKey) {
      return;
    }

    lastTransferReminderKey.current = reminderKey;
    setTransferReminder(buildTransferReminderMessage(activeTransferNotice, reminderBucket));
  }, [
    activeTransferNotice?.isSelectedMethod,
    activeTransferNotice?.paymentMethodId,
    activeTransferNotice?.secondsRemaining,
    activeTransferNotice?.sourceRideId,
    activeTransferNotice?.startedAt,
    transferNotificationsOff
  ]);

  function handleTransferNotificationToggle() {
    if (!activeTransferKey) {
      return;
    }

    setSilencedTransferKeys((current) => {
      const next = new Set(current);
      if (next.has(activeTransferKey)) {
        next.delete(activeTransferKey);
        lastTransferReminderKey.current = null;
      } else {
        next.add(activeTransferKey);
        setTransferReminder("");
      }
      persistSilencedTransferKeys(next);
      return next;
    });
  }

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
          ? await api.register(username.trim().toLowerCase(), email, password)
          : await api.login(email, password);
      const firstAuthenticatedSession = !hasAuthenticatedBefore;

      localStorage.setItem(TOKEN_KEY, response.token);
      localStorage.setItem(USER_KEY, JSON.stringify(response.user));
      localStorage.setItem(HAS_AUTHENTICATED_BEFORE_KEY, "true");
      setToken(response.token);
      setUser(response.user);
      setIsFirstAuthenticatedSession(firstAuthenticatedSession);
      if (!hasAuthenticatedBefore) {
        setHasAuthenticatedBefore(true);
      }
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
      <main className="auth-page">
        <NycBackdrop />
        <section className="auth-copy" aria-labelledby="auth-title">
          <div className="brand-lockup">
            <span className="brand-mark">TW</span>
            <div>
              <p className="brand-name">TapWise</p>
              <p className="brand-caption">New York City transit</p>
            </div>
          </div>
          <h1 id="auth-title">TapWise</h1>
          <p className="auth-tagline">Know which tap gets you to free rides faster.</p>
          <p className="lede">
            Track subway and bus rides by card or device, compare active 7-day
            windows, and keep every payment method moving toward the weekly cap.
          </p>

          <div className="auth-stat-grid" aria-label="TapWise fare tracking summary">
            <div>
              <strong>12</strong>
              <span>cap-counting rides</span>
            </div>
            <div>
              <strong>7 days</strong>
              <span>per payment window</span>
            </div>
            <div>
              <strong>1 tap</strong>
              <span>recommended per ride</span>
            </div>
          </div>

          <div className="fare-preview" aria-label="Example fare cap progress">
            <div className="fare-preview-header">
              <span>Work Visa</span>
              <strong>8 / 12 cap rides</strong>
            </div>
            <div className="fare-preview-meter">
              <span />
            </div>
            <div className="fare-preview-footer">
              <span>4 rides left</span>
              <span>Window ends Friday</span>
            </div>
          </div>
        </section>

        <section className="auth-panel" aria-label="TapWise account access">
          <div className="auth-panel-top">
            <div className="auth-panel-heading">
              <p className="eyebrow">Account</p>
              <h2>{mode === "register" ? "Create your tracker" : "Welcome back"}</h2>
            </div>
            <ThemeToggle theme={theme} onThemeChange={setTheme} />
          </div>

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
            {mode === "register" ? (
              <label>
                Username
                <input
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  placeholder="tapwise_rider"
                  required
                />
              </label>
            ) : null}
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
  const ridesTaken = fareStatus?.rides_taken ?? 0;
  const ridesRemaining = fareStatus?.rides_remaining ?? FARE_CAP_RIDES;
  const progress = Math.min(100, fareStatus ? (ridesTaken / FARE_CAP_RIDES) * 100 : 0);
  const latestRide = rides[0] ?? null;

  return (
    <main className="shell dashboard-shell">
      <NycBackdrop />
      <header className="topbar">
        <div className="topbar-title">
          <div className="brand-lockup compact">
            <span className="brand-mark">TW</span>
            <div>
              <p className="brand-name">TapWise</p>
              <p className="brand-caption">New York City transit</p>
            </div>
          </div>
          <h1>
            {isFirstAuthenticatedSession ? "Welcome to TapWise!" : `Welcome back, ${user.username}`}
          </h1>
        </div>
        <div className="topbar-actions">
          <ThemeToggle theme={theme} onThemeChange={setTheme} />
          <span className="user-pill">{user.email}</span>
          <button onClick={handleLogout} className="secondary-button">
            Logout
          </button>
        </div>
      </header>

      {appError ? <div className="banner error">{appError}</div> : null}
      {activeTransferNotice ? (
        <div className="banner transfer" role="status" aria-live="polite">
          <div>
            <strong>
              {formatTransitLabel(activeTransferNotice.sourceTransitMode)} to{" "}
              {formatTransitLabel(activeTransferNotice.targetTransitMode)} transfer available
            </strong>
            <p>
              {transferNotificationsOff
                ? "Notifications are off for this transfer. The timer will keep running here."
                : transferReminder || buildTransferReminderMessage(activeTransferNotice, 0)}
            </p>
          </div>
          <div className="transfer-controls">
            <div className="transfer-timer" aria-label="Transfer time remaining">
              <span>{formatCountdown(activeTransferNotice.secondsRemaining)}</span>
              <small>remaining</small>
            </div>
            <button
              type="button"
              className="secondary-button transfer-toggle-button"
              onClick={handleTransferNotificationToggle}
            >
              {transferNotificationsOff ? "Turn notifications on" : "Turn notifications off"}
            </button>
          </div>
        </div>
      ) : null}

      <section className="status-strip" aria-label="TapWise account summary">
        <div className="stat-tile">
          <span>Payment methods</span>
          <strong>{paymentMethods.length}</strong>
        </div>
        <div className="stat-tile">
          <span>Current window</span>
          <strong>{ridesTaken} / {FARE_CAP_RIDES}</strong>
        </div>
        <div className="stat-tile">
          <span>Rides left</span>
          <strong>{fareStatus?.free_rides_active ? "0" : ridesRemaining}</strong>
        </div>
        <div className="stat-tile">
          <span>Latest ride</span>
          <strong>{formatShortDate(latestRide?.timestamp ?? null)}</strong>
        </div>
      </section>

      <section className="grid">
        <article className="panel recommendation-panel">
          <div>
            <p className="panel-label">Best next tap</p>
            <h2>{recommendation?.message ?? "Loading recommendation..."}</h2>
            <p className="muted">
              {recommendation?.warning ?? "TapWise recalculates this after every ride."}
            </p>
          </div>
          <div className="recommendation-badge">
            <span>{recommendation?.estimated_rides_until_free ?? ridesRemaining}</span>
            <small>rides until free</small>
          </div>
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

          <div className="method-list">
            {paymentMethods.map((method) => (
              <button
                key={method.id}
                className={
                  method.id === selectedMethodId
                    ? "selector active selector-card"
                    : "selector selector-card"
                }
                onClick={() => setSelectedMethodId(method.id)}
              >
                <span className="method-type">{getPaymentTypeLabel(method.payment_type)}</span>
                <strong>{method.label}</strong>
                <span className="method-details">{method.masked_details}</span>
              </button>
            ))}
            {paymentMethods.length === 0 ? (
              <p className="empty-state">Add your first card or device to start tracking rides.</p>
            ) : null}
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
          <div className="progress-heading">
            <div>
              <p className="panel-label">Fare cap status</p>
              <h2>
                {fareStatus?.free_rides_active
                  ? "Free rides active"
                  : `${ridesRemaining} rides left`}
              </h2>
            </div>
            <strong>{Math.round(progress)}%</strong>
          </div>
          <p className="muted">
            {selectedMethod
              ? `Tracking ${selectedMethod.label} (${selectedMethod.masked_details})`
              : "Select a payment method to see status."}
          </p>
          <div
            className="progress-track"
            aria-label={`${ridesTaken} of ${FARE_CAP_RIDES} cap-counting rides completed`}
          >
            <div className="progress-fill" style={{ width: `${progress}%` }} />
          </div>
          <div className="progress-meta">
            <span>{ridesTaken} / {FARE_CAP_RIDES} cap-counting rides</span>
            <span>Window ends {formatDate(fareStatus?.window_end ?? null)}</span>
          </div>
          {selectedMethod ? (
            <div className="detail-chip-row">
              <span className="detail-chip">{formatPaymentType(selectedMethod.payment_type)}</span>
              <span className="detail-chip">Code: {selectedMethod.identifier_code}</span>
              {fareStatus?.transfer_rides_taken ? (
                <span className="detail-chip">
                  {fareStatus.transfer_rides_taken} free{" "}
                  {fareStatus.transfer_rides_taken === 1 ? "transfer" : "transfers"}
                </span>
              ) : null}
            </div>
          ) : null}
        </article>

        <article className="panel ride-logging-panel">
          <div className="panel-header-row">
            <div>
              <p className="panel-label">Ride logging</p>
              <h2>Add a trip</h2>
            </div>
            <span className="selected-method-pill">
              {selectedMethod ? selectedMethod.label : "No payment selected"}
            </span>
          </div>
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
          <div className="panel-header-row">
            <div>
              <p className="panel-label">Ride history</p>
              <h2>{rides.length} logged rides</h2>
            </div>
          </div>
          {loading ? <p className="muted">Loading rides...</p> : null}
          <div className="ride-list">
            {rides.map((ride) => (
              <div className="ride-row" key={ride.id}>
                <div>
                  <div className="ride-row-title">
                    <strong>{ride.payment_method_label}</strong>
                    <span>{formatShortDate(ride.timestamp)}</span>
                  </div>
                  <p>
                    {ride.entry_stop} to {ride.exit_stop}
                  </p>
                </div>
                <div className="ride-chip-row">
                  <span className="route-chip">
                    {ride.transit_mode.toUpperCase()} {ride.transit_line}
                  </span>
                  <span className={ride.is_transfer ? "fare-chip transfer-chip" : "fare-chip"}>
                    {ride.is_transfer ? "Free transfer" : "Cap ride"}
                  </span>
                </div>
              </div>
            ))}
            {rides.length === 0 ? (
              <p className="empty-state">No rides logged yet. Add a trip to see history here.</p>
            ) : null}
          </div>
        </article>
      </section>
    </main>
  );
}

export default App;
