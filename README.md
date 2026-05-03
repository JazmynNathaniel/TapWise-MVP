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
