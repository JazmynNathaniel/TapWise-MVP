import { FormEvent, useEffect, useRef, useState, type CSSProperties } from "react";
import { api } from "./api";
import {
  Arrival,
  ArrivalResponse,
  FareStatus,
  FrequentRoute,
  PaymentMethod,
  PersonalizedAlerts,
  Recommendation,
  Ride,
  RouteSummary,
  ServiceAlertResponse,
  TransitMode,
  TransitOptions,
  User
} from "./types";

declare global {
  interface Window {
    webkitAudioContext?: typeof AudioContext;
  }
}

const TOKEN_KEY = "tapwise_token";
const USER_KEY = "tapwise_user";
const HAS_AUTHENTICATED_BEFORE_KEY = "tapwise_has_authenticated_before";
const THEME_KEY = "tapwise_theme";
const SETTINGS_KEY = "tapwise_settings";
const SILENCED_TRANSFER_NOTIFICATIONS_KEY = "tapwise_silenced_transfer_notifications";
const SESSION_ENDED_MESSAGE = "Your session has ended. Please sign in again.";
const PASSWORD_RULE_MESSAGE =
  "Password must be at least 8 characters and include one capital letter, one number, one special character (!@#$%^&*_-), and no spaces.";
const ACTION_RETRY_DELAY_MS = 3500;
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

const TRANSIT_MODE_OPTIONS: Array<{
  value: TransitMode;
  label: string;
  routeLabel: string;
  placeholder: string;
}> = [
  {
    value: "subway",
    label: "Subway",
    routeLabel: "Subway line",
    placeholder: "Select subway"
  },
  {
    value: "bus",
    label: "Bus",
    routeLabel: "Bus line",
    placeholder: "Select bus"
  },
  {
    value: "lirr",
    label: "LIRR",
    routeLabel: "LIRR branch",
    placeholder: "Select LIRR"
  },
  {
    value: "metro_north",
    label: "Metro-North",
    routeLabel: "Metro-North line",
    placeholder: "Select Metro-North"
  }
];

type AuthMode = "login" | "register";
type ThemeMode = "dark" | "light";
type DashboardTab = "fare" | "travel" | "payments" | "rides" | "settings";
type NotificationFrequency = "as_it_happens" | "daily" | "weekly";
type SoundOption = "service_change" | "travel_update" | "soft" | "bright" | "none";

type PaymentFormState = {
  label: string;
  paymentType: string;
  identifierCode: string;
};

type RideFormState = {
  transitMode: TransitMode;
  transitLine: string;
  entryStop: string;
  exitStop: string;
};

type RideTimingMode = "now" | "manual";

type AppSettings = {
  routeUpdatesEnabled: boolean;
  serviceAlertsEnabled: boolean;
  transferRemindersEnabled: boolean;
  notificationFrequency: NotificationFrequency;
  notificationVolume: number;
  soundOption: SoundOption;
};

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

function getFrequentRouteKey(route: Pick<FrequentRoute, "transit_mode" | "line" | "entry_stop">) {
  return [route.transit_mode, route.line, route.entry_stop].join(":");
}

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

const defaultSettings: AppSettings = {
  routeUpdatesEnabled: true,
  serviceAlertsEnabled: true,
  transferRemindersEnabled: true,
  notificationFrequency: "as_it_happens",
  notificationVolume: 90,
  soundOption: "service_change"
};

function safeStorageGetItem(key: string) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeStorageSetItem(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Some social app browsers block saved browser data.
  }
}

function safeStorageRemoveItem(key: string) {
  try {
    window.localStorage.removeItem(key);
  } catch {
    // Some social app browsers block saved browser data.
  }
}

function browserStorageAvailable() {
  const testKey = "tapwise_storage_check";
  try {
    window.localStorage.setItem(testKey, "1");
    window.localStorage.removeItem(testKey);
    return true;
  } catch {
    return false;
  }
}

function getBrowserSupportNotice() {
  const userAgent = navigator.userAgent.toLowerCase();
  const isEmbeddedBrowser = [
    "instagram",
    "fban",
    "fbav",
    "fb_iab",
    "threads",
    "barcelona",
    "twitter",
    "tiktok",
    "linkedinapp",
    "snapchat",
    "pinterest"
  ].some((marker) => userAgent.includes(marker));

  if (isEmbeddedBrowser) {
    return "TapWise works best in Safari, Chrome, Edge, or Firefox. Social app browsers can block route updates and make it harder to stay signed in, so open this link in your browser for the full app.";
  }

  if (!browserStorageAvailable()) {
    return "TapWise needs your browser to remember that you signed in while you use the app. Please open TapWise in Safari, Chrome, Edge, or Firefox.";
  }

  return "";
}

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

function formatArrivalTime(value: string) {
  return new Date(value).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit"
  });
}

function formatMinutesUntil(minutes: number) {
  if (minutes <= 0) {
    return "Due";
  }
  if (minutes === 1) {
    return "1 min";
  }
  return `${minutes} min`;
}

function playNotificationPreview(soundOption: SoundOption, volume: number) {
  if (soundOption === "none") {
    return;
  }

  const normalizedVolume = Math.min(1, Math.max(0, volume / 100));

  if (soundOption === "service_change" || soundOption === "travel_update") {
    const speech = "speechSynthesis" in window ? window.speechSynthesis : null;
    if (!speech) {
      return;
    }

    const utterance = new SpeechSynthesisUtterance(
      soundOption === "service_change"
        ? "Service Change"
        : "There has been an update to your travel plans"
    );
    utterance.volume = normalizedVolume;
    utterance.rate = soundOption === "service_change" ? 0.86 : 0.9;
    utterance.pitch = 0.92;
    utterance.voice =
      speech.getVoices().find((voice) => voice.lang.toLowerCase().startsWith("en-us")) ?? null;
    speech.cancel();
    speech.speak(utterance);
    return;
  }

  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) {
    return;
  }

  const audioContext = new AudioContextClass();
  const oscillator = audioContext.createOscillator();
  const gain = audioContext.createGain();
  const now = audioContext.currentTime;
  const frequency = soundOption === "bright" ? 880 : 520;

  oscillator.type = soundOption === "bright" ? "triangle" : "sine";
  oscillator.frequency.setValueAtTime(frequency, now);
  oscillator.frequency.exponentialRampToValueAtTime(frequency * 1.22, now + 0.12);
  gain.gain.setValueAtTime(0.0001, now);
  gain.gain.exponentialRampToValueAtTime(Math.max(0.0001, normalizedVolume * 0.32), now + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.28);

  oscillator.connect(gain);
  gain.connect(audioContext.destination);
  oscillator.start(now);
  oscillator.stop(now + 0.3);
  window.setTimeout(() => void audioContext.close(), 420);
}

function formatModeLabel(value: string) {
  return TRANSIT_MODE_OPTIONS.find((option) => option.value === value)?.label ?? value;
}

function getArrivalDirectionBucket(arrival: Arrival): "first" | "last" {
  const normalizedDirection = arrival.direction.toLowerCase();

  if (
    normalizedDirection.includes("north") ||
    normalizedDirection.includes("west")
  ) {
    return "first";
  }

  if (
    normalizedDirection.includes("south") ||
    normalizedDirection.includes("east")
  ) {
    return "last";
  }

  if (arrival.direction_id === 1) {
    return "last";
  }

  return "first";
}

function getDirectionCards(
  arrivals: Arrival[],
  firstStop: string,
  lastStop: string
) {
  const firstStopLabel = firstStop || "the first stop";
  const lastStopLabel = lastStop || "the last stop";

  return [
    {
      id: "first",
      className: "direction-card direction-card-first",
      title: `Toward ${firstStopLabel}`,
      detail: "First stop on this line",
      terminal: firstStopLabel,
      arrivals: arrivals.filter(
        (arrival) => getArrivalDirectionBucket(arrival) === "first"
      )
    },
    {
      id: "last",
      className: "direction-card direction-card-last",
      title: `Toward ${lastStopLabel}`,
      detail: "Last stop on this line",
      terminal: lastStopLabel,
      arrivals: arrivals.filter(
        (arrival) => getArrivalDirectionBucket(arrival) === "last"
      )
    }
  ];
}

function getPaymentTypeLabel(value: string) {
  return PAYMENT_TYPE_OPTIONS.find((option) => option.value === value)?.label ?? value;
}

function formatPaymentType(value: string) {
  return getPaymentTypeLabel(value).toUpperCase();
}

function formatTransitLabel(value: string | null) {
  if (value === "subway" || value === "lirr" || value === "metro_north") {
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
  const rawValue = safeStorageGetItem(SILENCED_TRANSFER_NOTIFICATIONS_KEY);
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
  safeStorageSetItem(
    SILENCED_TRANSFER_NOTIFICATIONS_KEY,
    JSON.stringify(Array.from(keys))
  );
}

function getStoredTheme(): ThemeMode {
  return safeStorageGetItem(THEME_KEY) === "light" ? "light" : "dark";
}

function hydrateStoredSettings(): AppSettings {
  const rawValue = safeStorageGetItem(SETTINGS_KEY);
  if (!rawValue) {
    return defaultSettings;
  }

  try {
    const parsed = JSON.parse(rawValue) as Partial<AppSettings>;
    const notificationFrequency: NotificationFrequency =
      parsed.notificationFrequency === "daily" || parsed.notificationFrequency === "weekly"
        ? parsed.notificationFrequency
        : "as_it_happens";
    const soundOption: SoundOption =
      parsed.soundOption === "travel_update" ||
      parsed.soundOption === "bright" ||
      parsed.soundOption === "soft" ||
      parsed.soundOption === "none"
        ? parsed.soundOption
        : "service_change";
    const notificationVolume =
      typeof parsed.notificationVolume === "number"
        ? Math.min(100, Math.max(0, parsed.notificationVolume))
        : defaultSettings.notificationVolume;

    return {
      routeUpdatesEnabled: parsed.routeUpdatesEnabled ?? defaultSettings.routeUpdatesEnabled,
      serviceAlertsEnabled: parsed.serviceAlertsEnabled ?? defaultSettings.serviceAlertsEnabled,
      transferRemindersEnabled:
        parsed.transferRemindersEnabled ?? defaultSettings.transferRemindersEnabled,
      notificationFrequency,
      notificationVolume,
      soundOption
    };
  } catch {
    return defaultSettings;
  }
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
    return "Select a transit line.";
  }
  if (!form.entryStop) {
    return "Select the stop where you entered.";
  }
  if (!form.exitStop) {
    return "Select the stop where you exited.";
  }
  return null;
}

function validatePassword(value: string) {
  if (
    value.length < 8 ||
    /\s/.test(value) ||
    !/[A-Z]/.test(value) ||
    !/[0-9]/.test(value) ||
    !/[!@#$%^&*_-]/.test(value)
  ) {
    return PASSWORD_RULE_MESSAGE;
  }

  return null;
}

function App() {
  const [theme, setTheme] = useState<ThemeMode>(() => getStoredTheme());
  const [settings, setSettings] = useState<AppSettings>(() => hydrateStoredSettings());
  const [dashboardTab, setDashboardTab] = useState<DashboardTab>("fare");
  const [mode, setMode] = useState<AuthMode>("register");
  const [username, setUsername] = useState("tapwise_rider");
  const [email, setEmail] = useState("demo@tapwise.app");
  const [password, setPassword] = useState("Password123!");
  const [token, setToken] = useState<string | null>(() => safeStorageGetItem(TOKEN_KEY));
  const [user, setUser] = useState<User | null>(() => hydrateStoredUser(safeStorageGetItem(USER_KEY)));
  const [hasAuthenticatedBefore, setHasAuthenticatedBefore] = useState(
    () => safeStorageGetItem(HAS_AUTHENTICATED_BEFORE_KEY) === "true"
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
  const [, setRouteSummaries] = useState<RouteSummary[]>([]);
  const [personalizedAlerts, setPersonalizedAlerts] = useState<PersonalizedAlerts | null>(null);
  const [selectedRouteMode, setSelectedRouteMode] = useState<TransitMode>("subway");
  const [selectedRouteLine, setSelectedRouteLine] = useState("");
  const [selectedRouteStop, setSelectedRouteStop] = useState("");
  const [arrivalBoard, setArrivalBoard] = useState<ArrivalResponse | null>(null);
  const [arrivalLoading, setArrivalLoading] = useState(false);
  const [selectedRouteAlerts, setSelectedRouteAlerts] = useState<ServiceAlertResponse | null>(null);
  const [selectedRouteAlertsLoading, setSelectedRouteAlertsLoading] = useState(false);
  const [notificationUpdatingKey, setNotificationUpdatingKey] = useState("");
  const [rideTimingMode, setRideTimingMode] = useState<RideTimingMode>("now");
  const [manualRideDate, setManualRideDate] = useState(() => createManualRideDateTime().date);
  const [manualRideTime, setManualRideTime] = useState(() => createManualRideDateTime().time);
  const [showPaymentDetails, setShowPaymentDetails] = useState(false);
  const [authError, setAuthError] = useState("");
  const [authNotice, setAuthNotice] = useState("");
  const [appError, setAppError] = useState("");
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [authRetryLocked, setAuthRetryLocked] = useState(false);
  const [paymentSubmitting, setPaymentSubmitting] = useState(false);
  const [paymentRetryLocked, setPaymentRetryLocked] = useState(false);
  const [rideSubmitting, setRideSubmitting] = useState(false);
  const [rideRetryLocked, setRideRetryLocked] = useState(false);
  const [profileDeleting, setProfileDeleting] = useState(false);
  const [profileRetryLocked, setProfileRetryLocked] = useState(false);
  const [notificationRetryKeys, setNotificationRetryKeys] = useState<Set<string>>(
    () => new Set()
  );
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
  const browserSupportNotice = getBrowserSupportNotice();

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    safeStorageSetItem(THEME_KEY, theme);
  }, [theme]);

  useEffect(() => {
    safeStorageSetItem(SETTINGS_KEY, JSON.stringify(settings));
  }, [settings]);

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
      const modeOptions = transitOptions[current.transitMode] ?? {};
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
    if (!transitOptions) {
      return;
    }

    const routeOptions = transitOptions[selectedRouteMode] ?? {};
    const lines = Object.keys(routeOptions);
    setSelectedRouteLine((current) => {
      if (current && routeOptions[current]) {
        return current;
      }
      return lines[0] ?? "";
    });
  }, [selectedRouteMode, transitOptions]);

  useEffect(() => {
    if (!transitOptions || !selectedRouteLine) {
      setSelectedRouteStop("");
      return;
    }

    const stops = transitOptions[selectedRouteMode]?.[selectedRouteLine] ?? [];
    setSelectedRouteStop((current) => {
      if (current && stops.includes(current)) {
        return current;
      }
      return stops[0] ?? "";
    });
  }, [selectedRouteLine, selectedRouteMode, transitOptions]);

  useEffect(() => {
    if (!token || !selectedRouteLine || !selectedRouteStop) {
      setArrivalBoard(null);
      return;
    }

    let cancelled = false;
    setArrivalLoading(true);
    void api
      .getArrivals(token, selectedRouteMode, selectedRouteLine, selectedRouteStop)
      .then((payload) => {
        if (!cancelled) {
          setArrivalBoard(payload);
        }
      })
      .catch((error: Error) => {
        if (!cancelled) {
          if (error.message === SESSION_ENDED_MESSAGE) {
            handleLogout();
            setAuthError(error.message);
            return;
          }

          setArrivalBoard({
            status: "unavailable",
            message: error.message,
            generated_at: new Date().toISOString(),
            arrivals: []
          });
        }
      })
      .finally(() => {
        if (!cancelled) {
          setArrivalLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedRouteLine, selectedRouteMode, selectedRouteStop, token]);

  useEffect(() => {
    if (!token || !selectedRouteLine) {
      setSelectedRouteAlerts(null);
      return;
    }

    let cancelled = false;
    setSelectedRouteAlertsLoading(true);
    void api
      .getServiceAlerts(token, selectedRouteMode, selectedRouteLine)
      .then((payload) => {
        if (!cancelled) {
          setSelectedRouteAlerts(payload);
        }
      })
      .catch((error: Error) => {
        if (cancelled) {
          return;
        }

        if (error.message === SESSION_ENDED_MESSAGE) {
          handleLogout();
          setAuthError(error.message);
          return;
        }

        setSelectedRouteAlerts({
          status: "unavailable",
          message: error.message,
          generated_at: new Date().toISOString(),
          alerts: []
        });
      })
      .finally(() => {
        if (!cancelled) {
          setSelectedRouteAlertsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedRouteLine, selectedRouteMode, token]);

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
      const [
        methods,
        rideItems,
        recommendationPayload,
        routePayload,
        personalizedPayload
      ] = await Promise.all([
        api.getPaymentMethods(activeToken),
        api.getRides(activeToken),
        api.getRecommendation(activeToken),
        api.getRoutes(activeToken),
        api.getPersonalizedAlerts(activeToken)
      ]);

      setPaymentMethods(methods);
      setRides(rideItems);
      setRecommendation(recommendationPayload);
      setRouteSummaries(routePayload.routes);
      setPersonalizedAlerts(personalizedPayload);

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
      const message = (error as Error).message;
      if (message === SESSION_ENDED_MESSAGE) {
        handleLogout();
        setAuthError(message);
        return;
      }
      setAppError(message);
    } finally {
      setLoading(false);
    }
  }

  async function handleAuthSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (authSubmitting || authRetryLocked) {
      return;
    }

    if (mode === "register") {
      const passwordError = validatePassword(password);
      if (passwordError) {
        setAuthNotice("");
        setAuthError(passwordError);
        return;
      }
    }

    setAuthSubmitting(true);
    try {
      setAuthError("");
      setAuthNotice("");
      const response =
        mode === "register"
          ? await api.register(username.trim().toLowerCase(), email, password)
          : await api.login(email, password);
      const firstAuthenticatedSession = !hasAuthenticatedBefore;

      safeStorageSetItem(TOKEN_KEY, response.token);
      safeStorageSetItem(USER_KEY, JSON.stringify(response.user));
      safeStorageSetItem(HAS_AUTHENTICATED_BEFORE_KEY, "true");
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
      lockActionTemporarily(setAuthRetryLocked);
    } finally {
      setAuthSubmitting(false);
    }
  }

  async function handleLogout(revokeToken = false) {
    const activeToken = token;
    if (revokeToken && activeToken) {
      try {
        await api.logout(activeToken);
      } catch {
        // Still clear local session state if the logout request cannot complete.
      }
    }

    safeStorageRemoveItem(TOKEN_KEY);
    safeStorageRemoveItem(USER_KEY);
    setToken(null);
    setUser(null);
    setPaymentMethods([]);
    setRides([]);
    setSelectedMethodId(null);
    setFareStatus(null);
    setRecommendation(null);
    setTransitOptions(null);
    setRouteSummaries([]);
    setPersonalizedAlerts(null);
    setArrivalBoard(null);
  }

  function updateSettings<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
    setSettings((current) => ({ ...current, [key]: value }));
  }

  function lockActionTemporarily(setLocked: (locked: boolean) => void) {
    setLocked(true);
    window.setTimeout(() => setLocked(false), ACTION_RETRY_DELAY_MS);
  }

  function lockNotificationTemporarily(routeKey: string) {
    setNotificationRetryKeys((current) => new Set(current).add(routeKey));
    window.setTimeout(() => {
      setNotificationRetryKeys((current) => {
        const next = new Set(current);
        next.delete(routeKey);
        return next;
      });
    }, ACTION_RETRY_DELAY_MS);
  }

  function handleSoundOptionChange(value: SoundOption) {
    updateSettings("soundOption", value);
    playNotificationPreview(value, settings.notificationVolume);
  }

  function handleNotificationVolumeChange(value: number) {
    updateSettings("notificationVolume", value);
  }

  function handleNotificationVolumePreview(value: number) {
    playNotificationPreview(settings.soundOption, value);
  }

  async function handleDeleteProfile() {
    if (!token || profileDeleting || profileRetryLocked) {
      return;
    }

    const confirmed = window.confirm(
      "Delete your TapWise profile, payment methods, and ride history? This cannot be undone."
    );
    if (!confirmed) {
      return;
    }

    setProfileDeleting(true);
    try {
      setAppError("");
      await api.deleteProfile(token);
      handleLogout();
      setMode("register");
      setAuthNotice("Your TapWise profile has been deleted.");
    } catch (error) {
      setAppError((error as Error).message);
      lockActionTemporarily(setProfileRetryLocked);
    } finally {
      setProfileDeleting(false);
    }
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

  function selectTravelRoute(mode: TransitMode, line: string) {
    if (!line) {
      return;
    }

    setSelectedRouteMode(mode);
    setSelectedRouteLine(line);
    const stops = transitOptions?.[mode]?.[line] ?? [];
    setSelectedRouteStop(stops[0] ?? "");
  }

  async function handleNotificationToggle(route: FrequentRoute) {
    if (!token) {
      return;
    }

    const routeKey = getFrequentRouteKey(route);
    if (notificationUpdatingKey === routeKey || notificationRetryKeys.has(routeKey)) {
      return;
    }

    setNotificationUpdatingKey(routeKey);
    try {
      setAppError("");
      await api.updateNotificationPreference(token, {
        transit_mode: route.transit_mode,
        transit_line: route.line,
        entry_stop: route.entry_stop,
        enabled: !route.notifications_enabled
      });
      const payload = await api.getPersonalizedAlerts(token);
      setPersonalizedAlerts(payload);
    } catch (error) {
      setAppError((error as Error).message);
      lockNotificationTemporarily(routeKey);
    } finally {
      setNotificationUpdatingKey("");
    }
  }

  async function handleCreatePaymentMethod(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || paymentSubmitting || paymentRetryLocked) {
      return;
    }

    const validationError = validatePaymentForm(paymentForm);
    if (validationError) {
      setAppError(validationError);
      return;
    }

    setPaymentSubmitting(true);
    try {
      setAppError("");
      const createdMethod = await api.createPaymentMethod(token, {
        label: paymentForm.label.trim(),
        payment_type: paymentForm.paymentType,
        identifier_code: paymentForm.identifierCode
      });

      setPaymentMethods((current) => [...current, createdMethod]);
      setSelectedMethodId(createdMethod.id);
      setPaymentForm(emptyPaymentForm);
      setShowPaymentDetails(false);
      await loadDashboard(token);
    } catch (error) {
      setAppError((error as Error).message);
      lockActionTemporarily(setPaymentRetryLocked);
    } finally {
      setPaymentSubmitting(false);
    }
  }

  async function handleAddRide() {
    if (!token || !selectedMethodId || rideSubmitting || rideRetryLocked) {
      return;
    }

    const validationError = validateRideForm(rideForm);
    if (validationError) {
      setAppError(validationError);
      return;
    }

    setRideSubmitting(true);
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
      lockActionTemporarily(setRideRetryLocked);
    } finally {
      setRideSubmitting(false);
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
          <p className="auth-tagline">Know your fare, your route, and what is coming next.</p>
          <p className="lede">
            TapWise helps you choose the right card, see upcoming subway, bus,
            LIRR, and Metro-North arrivals, and keep an eye on service changes
            for the routes you use most.
          </p>

          <div className="auth-stat-grid" aria-label="TapWise app features">
            <div>
              <strong>Fares</strong>
              <span>rides left toward free trips</span>
            </div>
            <div>
              <strong>Travel</strong>
              <span>next transit arrivals by route</span>
            </div>
            <div>
              <strong>Alerts</strong>
              <span>updates for familiar lines</span>
            </div>
          </div>

          <div className="fare-preview" aria-label="TapWise feature preview">
            <div className="fare-preview-header">
              <span>Today in TapWise</span>
              <strong>Fare + travel</strong>
            </div>
            <div className="fare-preview-meter">
              <span />
            </div>
            <div className="feature-preview-list">
              <div>
                <strong>4 rides left</strong>
                <span>Best card for your next tap</span>
              </div>
              <div>
                <strong>3 min</strong>
                <span>Next train toward South Ferry</span>
              </div>
              <div>
                <strong>All clear</strong>
                <span>No alerts for your usual route</span>
              </div>
            </div>
          </div>

          <div className="privacy-note" aria-label="TapWise privacy note">
            <strong>No location tracking needed.</strong>
            <p>
              TapWise does not need or want your current location to track your rides.
              Your frequent routes are based on the trips you choose to log, not where
              your phone is.
            </p>
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

          {browserSupportNotice ? (
            <div className="banner notice browser-notice">{browserSupportNotice}</div>
          ) : null}

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
                <span className="field-helper">
                  Your username does not need to be your real name. Usernames are
                  unique and can only belong to one TapWise account.
                </span>
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
              {mode === "register" ? (
                <span className="field-helper">
                  Use at least 8 characters with one capital letter, one number, and one special character
                  (!@#$%^&*_-). Spaces are not allowed.
                </span>
              ) : null}
            </label>
            {authNotice ? <p className="notice">{authNotice}</p> : null}
            {authError ? <p className="error">{authError}</p> : null}
            <button
              type="submit"
              className="primary-button"
              disabled={authSubmitting || authRetryLocked}
            >
              {authSubmitting
                ? mode === "register"
                  ? "Creating..."
                  : "Signing in..."
                : mode === "register"
                  ? "Create account"
                  : "Sign in"}
            </button>
          </form>
        </section>
      </main>
    );
  }

  const availableModeOptions = transitOptions?.[rideForm.transitMode] ?? {};
  const availableLines = Object.keys(availableModeOptions);
  const availableStops =
    rideForm.transitLine ? availableModeOptions[rideForm.transitLine] ?? [] : [];
  const routeModeOptions = transitOptions?.[selectedRouteMode] ?? {};
  const routeOptionGroups = TRANSIT_MODE_OPTIONS.map((option) => ({
    ...option,
    lines: Object.keys(transitOptions?.[option.value] ?? {})
  }));
  const routeStops = selectedRouteLine ? routeModeOptions[selectedRouteLine] ?? [] : [];
  const firstRouteStop = routeStops[0] ?? "";
  const lastRouteStop = routeStops[routeStops.length - 1] ?? "";
  const directionCards = getDirectionCards(
    arrivalBoard?.arrivals ?? [],
    firstRouteStop,
    lastRouteStop
  );
  const frequentRoutes = personalizedAlerts?.routes ?? [];
  const personalizedNotifications = personalizedAlerts?.notifications ?? [];

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
          <span className="user-pill">{user.email}</span>
        </div>
      </header>

      {browserSupportNotice ? (
        <div className="banner notice browser-notice">{browserSupportNotice}</div>
      ) : null}
      {appError ? <div className="banner error">{appError}</div> : null}
      {activeTransferNotice && settings.transferRemindersEnabled ? (
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

      <div className="dashboard-tabs" role="tablist" aria-label="Dashboard views">
        <button
          type="button"
          role="tab"
          aria-selected={dashboardTab === "fare"}
          className={dashboardTab === "fare" ? "active" : ""}
          onClick={() => setDashboardTab("fare")}
        >
          <span>Fares</span>
          <small>
            {fareStatus?.free_rides_active ? "Free rides active" : `${ridesRemaining} left`}
          </small>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={dashboardTab === "travel"}
          className={dashboardTab === "travel" ? "active" : ""}
          onClick={() => setDashboardTab("travel")}
        >
          <span>Travel</span>
          <small>
            {selectedRouteLine
              ? `${formatModeLabel(selectedRouteMode)} ${selectedRouteLine}`
              : "Routes"}
          </small>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={dashboardTab === "payments"}
          className={dashboardTab === "payments" ? "active" : ""}
          onClick={() => setDashboardTab("payments")}
        >
          <span>Pay</span>
          <small>{paymentMethods.length} saved</small>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={dashboardTab === "rides"}
          className={dashboardTab === "rides" ? "active" : ""}
          onClick={() => setDashboardTab("rides")}
        >
          <span>Rides</span>
          <small>{rides.length} logged</small>
        </button>
        <button
          type="button"
          role="tab"
          aria-label="Settings"
          aria-selected={dashboardTab === "settings"}
          className={dashboardTab === "settings" ? "active icon-tab" : "icon-tab"}
          data-tooltip="Settings"
          onClick={() => setDashboardTab("settings")}
        >
          <span aria-hidden="true" className="gear-icon">
            ⚙
          </span>
          <small>Preferences</small>
        </button>
      </div>

      <section
        className={dashboardTab === "fare" ? "status-strip" : "status-strip hidden-tab-content"}
        aria-label="TapWise account summary"
      >
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
        <article
          className={
            dashboardTab === "fare"
              ? "panel recommendation-panel"
              : "panel recommendation-panel hidden-tab-content"
          }
        >
          <div>
            <p className="panel-label">Best next tap</p>
            <h2>{recommendation?.message ?? "Finding your best next tap..."}</h2>
            <p className="muted">
              {recommendation?.warning ?? "TapWise recalculates this after every ride."}
            </p>
          </div>
          <div className="recommendation-badge">
            <span>{recommendation?.estimated_rides_until_free ?? ridesRemaining}</span>
            <small>rides until free</small>
          </div>
        </article>

        <article
          className={
            dashboardTab === "payments"
              ? "panel payment-panel"
              : "panel payment-panel hidden-tab-content"
          }
        >
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
            <button
              type="submit"
              className="primary-button"
              disabled={paymentSubmitting || paymentRetryLocked}
            >
              {paymentSubmitting ? "Saving..." : "Save payment method"}
            </button>
          </form>
        </article>

        <article
          className={
            dashboardTab === "fare"
              ? "panel progress-panel"
              : "panel progress-panel hidden-tab-content"
          }
        >
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

        <article
          className={
            dashboardTab === "travel"
              ? "panel route-board-panel"
              : "panel route-board-panel hidden-tab-content"
          }
        >
          <div className="panel-header-row">
            <div>
              <p className="panel-label">Route board</p>
              <h2>All routes and arrivals</h2>
            </div>
            <span className="selected-method-pill">
              {selectedRouteLine
                ? `${formatModeLabel(selectedRouteMode)} ${selectedRouteLine}`
                : "Choose a route"}
            </span>
          </div>

          <div className="route-board-grid">
            <div className="route-picker">
              <div className="route-dropdown-grid">
                {routeOptionGroups.map((option) => (
                  <label key={option.value}>
                    {option.routeLabel}
                    <select
                      value={selectedRouteMode === option.value ? selectedRouteLine : ""}
                      onChange={(event) => selectTravelRoute(option.value, event.target.value)}
                    >
                      <option value="">{option.placeholder}</option>
                      {option.lines.map((line) => (
                        <option key={line} value={line}>
                          {line}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
                <label className="route-stop-select">
                  Stop for selected route
                  <select
                    value={selectedRouteStop}
                    onChange={(event) => setSelectedRouteStop(event.target.value)}
                  >
                    {routeStops.map((stop) => (
                      <option key={stop} value={stop}>
                        {stop}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="selected-alert-board" aria-live="polite">
                <div className="arrival-board-heading">
                  <strong>Delays and service changes</strong>
                  <span>{selectedRouteLine || "Select a route"}</span>
                </div>
                {!settings.serviceAlertsEnabled ? (
                  <p className="empty-state">
                    Service updates are paused. You can turn them back on in Settings.
                  </p>
                ) : selectedRouteAlertsLoading ? (
                  <p className="muted">Checking for service updates...</p>
                ) : null}
                {settings.serviceAlertsEnabled && !selectedRouteAlertsLoading && selectedRouteAlerts ? (
                  selectedRouteAlerts.alerts.length > 0 ? (
                    <div className="selected-alert-list">
                      {selectedRouteAlerts.alerts.map((alert) => (
                        <div className="selected-alert-card" key={alert.id}>
                          <span className="route-chip">
                            {formatModeLabel(alert.transit_mode)} {alert.line ?? selectedRouteLine}
                          </span>
                          <strong>{alert.title}</strong>
                          <p>{alert.description || alert.effect || "Service change reported."}</p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="empty-state">
                      {selectedRouteAlerts.status === "ok"
                        ? "No alerts or service changes to report. You're all set. Safe travels!"
                        : selectedRouteAlerts.message}
                    </p>
                  )
                ) : null}
              </div>

              <div className="arrival-board" aria-live="polite">
                <div className="arrival-board-heading">
                  <strong>
                    {formatModeLabel(selectedRouteMode)} {selectedRouteLine}
                  </strong>
                  <span>{selectedRouteStop || "Select a stop"}</span>
                </div>
                {arrivalLoading ? <p className="muted">Checking live arrivals...</p> : null}
                {!arrivalLoading && arrivalBoard ? (
                  <>
                    {arrivalBoard.arrivals.length > 0 ? (
                      <div className="direction-card-grid">
                        {directionCards.map((card) => (
                          <section className={card.className} key={card.id}>
                            <div className="direction-card-heading">
                              <span>{card.detail}</span>
                              <strong>{card.title}</strong>
                            </div>
                            <div className="arrival-list">
                              {card.arrivals.slice(0, 4).map((arrival) => (
                                <div
                                  className="arrival-row"
                                  key={`${arrival.trip_id}:${arrival.stop_id}:${arrival.arrival_time}`}
                                >
                                  <div>
                                    <strong>{formatMinutesUntil(arrival.minutes_until)}</strong>
                                    <span>Arrival / departure</span>
                                  </div>
                                  <time dateTime={arrival.arrival_time}>
                                    {formatArrivalTime(arrival.arrival_time)}
                                  </time>
                                </div>
                              ))}
                              {card.arrivals.length === 0 ? (
                                <p className="empty-state">
                                  No upcoming trips toward {card.terminal} right now.
                                </p>
                              ) : null}
                            </div>
                          </section>
                        ))}
                      </div>
                    ) : (
                      <p className="empty-state">{arrivalBoard.message}</p>
                    )}
                    {arrivalBoard.arrivals.length > 0 ? (
                      <p className="muted helper-copy">{arrivalBoard.message}</p>
                    ) : null}
                  </>
                ) : null}
              </div>
            </div>
          </div>
        </article>

        <article
          className={
            dashboardTab === "travel"
              ? "panel alerts-panel"
              : "panel alerts-panel hidden-tab-content"
          }
        >
          <div className="panel-header-row">
            <div>
              <p className="panel-label">Service updates</p>
              <h2>Frequent routes</h2>
            </div>
          </div>

          <div className="notification-list">
            {settings.routeUpdatesEnabled
              ? personalizedNotifications.map((notification) => (
                  <div className="notification-card" key={notification.id}>
                    <span className="route-chip">
                      {formatModeLabel(notification.transit_mode)} {notification.line}
                    </span>
                    <strong>{notification.title}</strong>
                    <p>{notification.message}</p>
                  </div>
                ))
              : null}
            {!settings.routeUpdatesEnabled ? (
              <p className="empty-state">
                Route update notifications are paused. You can turn them back on in Settings.
              </p>
            ) : personalizedNotifications.length === 0 ? (
              <p className="empty-state">
                No frequent-route updates yet. Once you log a few rides, TapWise will keep an eye on those lines for you.
              </p>
            ) : null}
          </div>
        </article>

        <article
          className={
            dashboardTab === "settings"
              ? "panel settings-panel"
              : "panel settings-panel hidden-tab-content"
          }
        >
          <div className="panel-header-row">
            <div>
              <p className="panel-label">Settings</p>
              <h2>Notifications and display</h2>
            </div>
          </div>

          <div className="settings-control-grid">
            <label className="toggle-row">
              <span>
                <strong>Route update notifications</strong>
                <small>Updates for the lines you ride most.</small>
              </span>
              <input
                type="checkbox"
                checked={settings.routeUpdatesEnabled}
                onChange={(event) =>
                  updateSettings("routeUpdatesEnabled", event.target.checked)
                }
              />
            </label>
            <label className="toggle-row">
              <span>
                <strong>Service changes</strong>
                <small>Delay and service-change messages on the travel page.</small>
              </span>
              <input
                type="checkbox"
                checked={settings.serviceAlertsEnabled}
                onChange={(event) =>
                  updateSettings("serviceAlertsEnabled", event.target.checked)
                }
              />
            </label>
            <label className="toggle-row">
              <span>
                <strong>Transfer reminders</strong>
                <small>Helpful reminders while a free transfer is active.</small>
              </span>
              <input
                type="checkbox"
                checked={settings.transferRemindersEnabled}
                onChange={(event) =>
                  updateSettings("transferRemindersEnabled", event.target.checked)
                }
              />
            </label>
            <label>
              Notification frequency
              <select
                value={settings.notificationFrequency}
                onChange={(event) =>
                  updateSettings(
                    "notificationFrequency",
                    event.target.value as NotificationFrequency
                  )
                }
              >
                <option value="as_it_happens">As things happen</option>
                <option value="daily">Daily summary</option>
                <option value="weekly">Weekly summary</option>
              </select>
            </label>
            <label>
              Sound
              <select
                value={settings.soundOption}
                onChange={(event) =>
                  handleSoundOptionChange(event.target.value as SoundOption)
                }
              >
                <option value="service_change">Voice: Service Change</option>
                <option value="travel_update">Voice: travel update</option>
                <option value="soft">Soft chime</option>
                <option value="bright">Bright chime</option>
                <option value="none">No sound</option>
              </select>
            </label>
            <label>
              Volume
              <div className="volume-control">
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={settings.notificationVolume}
                  onChange={(event) =>
                    handleNotificationVolumeChange(Number(event.target.value))
                  }
                  onPointerUp={(event) =>
                    handleNotificationVolumePreview(Number(event.currentTarget.value))
                  }
                  onKeyUp={(event) =>
                    handleNotificationVolumePreview(Number(event.currentTarget.value))
                  }
                  disabled={settings.soundOption === "none"}
                />
                <span>{settings.notificationVolume}%</span>
              </div>
            </label>
            <div className="settings-theme-row">
              <div>
                <strong>Color theme</strong>
                <span>Choose the TapWise look that feels best.</span>
              </div>
              <ThemeToggle theme={theme} onThemeChange={setTheme} />
            </div>
          </div>
        </article>

        <article
          className={
            dashboardTab === "settings"
              ? "panel account-settings-panel"
              : "panel account-settings-panel hidden-tab-content"
          }
        >
          <div className="panel-header-row">
            <div>
              <p className="panel-label">Account</p>
              <h2>Your profile</h2>
            </div>
          </div>
          <div className="account-summary">
            <strong>{user.username}</strong>
            <span>{user.email}</span>
          </div>
          <div className="privacy-note compact-privacy-note">
            <strong>Your location stays yours.</strong>
            <p>
              TapWise uses logged rides to understand your familiar routes. It does not
              use your current location for tracking.
            </p>
          </div>
          <div className="account-action-list">
            <button
              type="button"
              className="secondary-button"
              onClick={() => void handleLogout(true)}
            >
              Log out
            </button>
            <button
              type="button"
              className="secondary-button danger-button"
              onClick={() => void handleDeleteProfile()}
              disabled={profileDeleting || profileRetryLocked}
            >
              {profileDeleting ? "Deleting..." : "Delete profile"}
            </button>
          </div>
        </article>

        <article
          className={
            dashboardTab === "settings"
              ? "panel route-settings-panel"
              : "panel route-settings-panel hidden-tab-content"
          }
        >
          <div className="panel-header-row">
            <div>
              <p className="panel-label">Route updates</p>
              <h2>Frequent route notifications</h2>
            </div>
          </div>
          {!settings.routeUpdatesEnabled ? (
            <p className="empty-state">
              Route update notifications are paused. Turn them back on above to use these route controls.
            </p>
          ) : null}
          <div className="frequent-route-list">
            {frequentRoutes.map((route) => {
              const routeKey = getFrequentRouteKey(route);
              return (
                <div className="frequent-route-row" key={routeKey}>
                  <div>
                    <strong>{formatModeLabel(route.transit_mode)} {route.line}</strong>
                    <span>
                      {route.entry_stop} to {route.exit_stop}
                    </span>
                    <small>{route.ride_count} logged rides</small>
                  </div>
                  <button
                    type="button"
                    className={
                      route.notifications_enabled
                        ? "secondary-button notification-toggle active"
                        : "secondary-button notification-toggle"
                    }
                    onClick={() => void handleNotificationToggle(route)}
                    disabled={
                      !settings.routeUpdatesEnabled ||
                      notificationUpdatingKey === routeKey ||
                      notificationRetryKeys.has(routeKey)
                    }
                  >
                    {route.notifications_enabled ? "Updates on" : "Updates off"}
                  </button>
                </div>
              );
            })}
            {frequentRoutes.length === 0 ? (
              <p className="empty-state">
                Log a few rides and TapWise will show your regular lines here.
              </p>
            ) : null}
          </div>
        </article>

        <article
          className={
            dashboardTab === "rides"
              ? "panel ride-logging-panel"
              : "panel ride-logging-panel hidden-tab-content"
          }
        >
          <div className="panel-header-row">
            <div>
              <p className="panel-label">Ride logging</p>
              <h2>Add a trip</h2>
            </div>
            <span className="selected-method-pill">
              {selectedMethod ? selectedMethod.label : "Choose a payment method"}
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
                  {TRANSIT_MODE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
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
                disabled={!selectedMethodId || rideSubmitting || rideRetryLocked}
              >
                {rideSubmitting
                  ? "Saving..."
                  : rideTimingMode === "now"
                    ? "Add ride now"
                    : "Save dated ride"}
              </button>
            </div>
          </div>
        </article>

        <article
          className={
            dashboardTab === "rides"
              ? "panel ride-history"
              : "panel ride-history hidden-tab-content"
          }
        >
          <div className="panel-header-row">
            <div>
              <p className="panel-label">Ride history</p>
              <h2>{rides.length} logged rides</h2>
            </div>
          </div>
          {loading ? <p className="muted">Getting your rides ready...</p> : null}
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
                    {formatModeLabel(ride.transit_mode)} {ride.transit_line}
                  </span>
                  <span className={ride.is_transfer ? "fare-chip transfer-chip" : "fare-chip"}>
                    {ride.is_transfer ? "Free transfer used" : "Cap ride"}
                  </span>
                </div>
              </div>
            ))}
            {rides.length === 0 ? (
              <p className="empty-state">No rides logged yet. Add your first trip when you're ready.</p>
            ) : null}
          </div>
        </article>
      </section>
    </main>
  );
}

export default App;
