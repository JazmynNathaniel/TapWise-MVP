# TapWise

TapWise is an MVP web app for NYC transit riders. It helps users track OMNY-style fare progress by payment method, choose the best card or device for the next tap, check upcoming subway, bus, LIRR, and Metro-North arrivals, and stay aware of service changes on routes they use often.

## Current Features

- Fare tracking by card, OMNY card, mobile wallet, or custom payment method label
- 7-day OMNY fare-cap windows per payment method
- Best-next-tap recommendations based on fare-cap progress and active transfers
- Free bus-to-train and train-to-bus transfer tracking
- Manual and current-time ride logging
- Separate dashboard tabs for fares, travel, payments, rides, and settings
- Route board for subway, bus, LIRR, and Metro-North lines
- Planned travel checks by route, origin, destination, and travel time
- Route suggestions that consider service state, fare-cap progress, and rail ticket prices
- Live arrivals grouped into adjacent terminal-direction cards
- Service alerts and delay/service-change display for the selected route and travel time
- Peak and off-peak ticket estimates for LIRR and Metro-North trips
- Personalized route notifications for frequently used routes
- User-friendly frontend error messages that avoid exposing server details
- Light and dark themes

## Stack

- Backend: Flask, SQLAlchemy, JWT auth
- Frontend: React + TypeScript with Vite
- Database: PostgreSQL in production via `DATABASE_URL`
- Realtime transit: MTA GTFS-RT feeds and MTA Bus Time

## Project Structure

```text
backend/
  app/
    routes/
    services/
  run.py
frontend/
  src/
```

## Environment Variables

### Backend

- `SECRET_KEY`
- `JWT_SECRET_KEY`
- `DATABASE_URL`
- `CLIENT_ORIGIN`
- `APP_ENV=production` for deployed backend services
- `MTA_API_KEY` optional for MTA feeds that require a key
- `MTA_BUS_TIME_API_KEY` required for live bus arrivals and bus service alerts

### Frontend

- `VITE_API_BASE_URL`

## Backend Setup

1. Create a virtual environment and install dependencies:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and update `DATABASE_URL` for PostgreSQL.

3. Start the API:

```powershell
python run.py
```

The API creates tables automatically on startup.

Production schema changes also live in `backend/migrations/`. Apply the numbered SQL files
against PostgreSQL when you want an explicit migration step instead of relying on startup table
creation.

## Frontend Setup

1. Install dependencies:

```powershell
cd frontend
npm install
```

2. Copy `.env.example` to `.env`.

3. Start the app:

```powershell
npm run dev
```

## Deployment

### Frontend on Vercel

- Root directory: `frontend`
- Build command: `npm run build`
- Output directory: `dist`
- Environment variable:
  - `VITE_API_BASE_URL=https://<your-render-service>.onrender.com/api`

This frontend does not currently use client-side routed URLs beyond the main app entry, so a
custom `vercel.json` rewrite is not required right now.

### Backend on Render

- Service type: Web Service
- Root directory: `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn run:app --bind 0.0.0.0:$PORT`
- Environment variables:
  - `SECRET_KEY`
  - `JWT_SECRET_KEY`
  - `DATABASE_URL`
  - `CLIENT_ORIGIN=https://<your-vercel-domain>`
  - `APP_ENV=production`
  - `MTA_BUS_TIME_API_KEY`
  - `MTA_API_KEY` if needed for your MTA account/feed access

`CLIENT_ORIGIN` also accepts a comma-separated list if you need to allow both your production
Vercel domain and a preview or staging frontend.

When `APP_ENV=production`, the backend refuses to start with development fallback secrets.
Set both `SECRET_KEY` and `JWT_SECRET_KEY` to generated values in Render.

This repo also includes [render.yaml](render.yaml) as a Render Blueprint starter for provisioning the backend service and a PostgreSQL database together.

### Database

- Use PostgreSQL in production.
- If you use Render Postgres, set the backend `DATABASE_URL` to the connection string Render
  provides for that database.

## VS Code

The repo includes [.vscode/settings.json](.vscode/settings.json) to point the Python extension at `backend/.venv/Scripts/python.exe`, load `backend/.env`, and make backend imports easier for analysis.

If your editor still shows missing Flask package imports, re-select the interpreter manually and choose the Python environment inside `backend/.venv`.

## API Endpoints

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `DELETE /api/auth/profile`
- `GET /api/payment-methods`
- `POST /api/payment-methods`
- `GET /api/rides`
- `POST /api/rides`
- `GET /api/fare-status/:payment_method_id`
- `GET /api/recommendation`
- `GET /api/transit-options`
- `GET /api/routes`
- `GET /api/arrivals`
- `GET /api/service-alerts`
- `GET /api/travel-status`
- `GET /api/route-suggestions`
- `GET /api/rail-fare-estimate`
- `GET /api/personalized-alerts`
- `POST /api/notification-preferences`

Compatibility aliases were added for the typo variants from the spec (`payment_mthods`, `recomendation`).

## Fare Logic

- A payment method starts a 7-day fare-cap window on its first OMNY-eligible subway or bus ride.
- Only subway, bus, and Select Bus Service rides count toward the OMNY 12-ride weekly fare cap.
- LIRR and Metro-North rides can be logged for route information, arrivals, and service alerts, but they use separate ticketing systems and do not count toward OMNY fare-cap progress.
- Only cap-counting rides inside that 7-day block count toward the cap for that payment method.
- A bus-to-train or train-to-bus transfer on the same payment method is free for two hours.
- Free transfer rides do not count toward the 12-ride fare cap.
- After 12 rides in that active window, `cap_reached` becomes true and the method is treated as having free rides until the window expires.
- If the current time is past the window end, the next ride starts a fresh 7-day window.

## Transit Logic

- Subway arrivals are pulled from MTA GTFS-RT feeds when available.
- Bus arrivals and bus service alerts use MTA Bus Time and require `MTA_BUS_TIME_API_KEY`.
- Arrival results are grouped by route terminal so users can see the exact direction instead of relying on vague northbound or southbound labels.
- Selected-route service alerts load automatically when the user chooses a train or bus line.
- Frequent-route notifications are based on the user's logged ride history and notification preferences.

## Security Notes

- Production deployments require real Flask and JWT secrets.
- CORS is restricted to `CLIENT_ORIGIN`; use a comma-separated list for multiple allowed frontend origins.
- Login, registration, selected write actions, and realtime transit calls are rate limited.
- Frontend actions use one in-flight request at a time, timeout slow responses, and briefly pause retry buttons after failed requests.
- Logout and profile deletion revoke the active JWT until it expires.
- Registration passwords require at least 8 characters, one capital letter, one number, one special character from `!@#$%^&*_-`, and no spaces.
