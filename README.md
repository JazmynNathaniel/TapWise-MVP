# TapWise

TapWise is an MVP SaaS web app for tracking NYC subway and bus rides by payment method and modeling OMNY weekly fare capping. Each payment method has its own independent 7-day window, so the app computes ride progress and recommendations per card or device.

## Stack

- Backend: Flask, SQLAlchemy, JWT auth
- Frontend: React + TypeScript with Vite
- Database: PostgreSQL via `DATABASE_URL` env var

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

`CLIENT_ORIGIN` also accepts a comma-separated list if you need to allow both your production
Vercel domain and a preview or staging frontend.

This repo also includes [render.yaml](/abs/path/C:/Users/Jonathan/Fare_TrackerMVP/render.yaml:1) as a Render Blueprint starter for provisioning the backend service and a PostgreSQL database together.

### Database

- Use PostgreSQL in production.
- If you use Render Postgres, set the backend `DATABASE_URL` to the connection string Render
  provides for that database.

## VS Code

The repo includes [.vscode/settings.json](/abs/path/C:/Users/Jonathan/Fare_TrackerMVP/.vscode/settings.json:1) to point the Python extension at `backend/.venv`, load `backend/.env`, and make backend imports easier for analysis.

If your editor still shows missing Flask package imports, re-select the interpreter manually and choose the Python environment inside `backend/.venv`.

## API Endpoints

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/payment-methods`
- `POST /api/payment-methods`
- `GET /api/rides`
- `POST /api/rides`
- `GET /api/fare-status/:payment_method_id`
- `GET /api/recommendation`

Compatibility aliases were added for the typo variants from the spec (`payment_mthods`, `recomendation`).

## Fare Logic

- A payment method starts a 7-day fare-cap window on its first ride.
- All rides inside that 7-day block count toward the cap for that payment method only.
- After 12 rides in that active window, `cap_reached` becomes true and the method is treated as having free rides until the window expires.
- If the current time is past the window end, the next ride starts a fresh 7-day window.
