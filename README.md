# RouteSync 2.0

RouteSync is a full-stack delivery operations and route management platform.

## Core workflows

- JWT authentication with admin, driver, and customer roles
- Delivery creation and management
- Driver management and availability
- Driver-to-delivery assignment
- Assignment accept/reject/reassign
- Delivery lifecycle: pending → assigned → accepted → pickup_started → picked_up → in_transit → delivered
- Driver location updates
- Customer tracking view
- Dispatch recommendations based on distance and workload
- Route optimization for multiple stops
- Operations dashboard with live API-backed KPIs
- Search, filters, details, and activity timelines

## Stack

Frontend: React, Vite, React Router, Lucide React

Backend: Python, FastAPI, SQLAlchemy, Pydantic, PyJWT

Database: PostgreSQL

Deployment: Render backend/database, Vercel frontend

## Local setup

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`.

If `DATABASE_URL` is not set, the app uses a local SQLite database at `backend/routesync.db`, which makes the project easy to run locally. For PostgreSQL, set `DATABASE_URL`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on the Vite port shown in the terminal, normally `http://localhost:5173`.

Set `VITE_API_URL` when the backend is not local:

```bash
VITE_API_URL=https://your-backend.onrender.com
```

## Demo accounts

The seed script creates:

- Admin: `admin@routesync.com` / `Admin@123`
- Driver: `driver@routesync.com` / `Driver@123`
- Customer: `customer@routesync.com` / `Customer@123`

To reseed:

```bash
cd backend
python -m app.seed
```

## Testing

Backend API tests cover health checks, JWT authentication, role protection, driver recommendation, route optimization, and the delivery lifecycle.

```bash
cd backend
pip install -r requirements-dev.txt
pytest -q
```

## API

Swagger: `/docs`

Important endpoints:

- `POST /auth/login`
- `GET /auth/me`
- `GET /dashboard/summary`
- `GET /users`
- `GET /drivers`
- `GET /deliveries`
- `POST /deliveries`
- `GET /deliveries/{id}`
- `PATCH /deliveries/{id}/status`
- `GET /assignments`
- `POST /assignments`
- `PATCH /assignments/{id}/action`
- `PATCH /drivers/{id}/location`
- `GET /dispatch/recommend/{delivery_id}`
- `POST /routes/optimize`

## Production notes

For the Render backend, set the service Root Directory to `backend`, Build Command to `pip install -r requirements.txt`, Start Command to `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, and Pre-Deploy Command to `python -m app.seed`.

Set these environment variables on Render:

- `DATABASE_URL`
- `JWT_SECRET`
- `FRONTEND_URL`

Do not commit secrets. The application creates database tables on startup for this portfolio project. For a larger production system, add Alembic migrations, managed secret storage, rate limiting, background jobs, and a dedicated production observability stack.
