# ConstructAI System

An AI-powered construction management platform that combines computer vision, machine learning, and intelligent automation to streamline site analysis, compliance workflows, risk assessment, and project scheduling.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
  - [Backend Setup](#backend-setup)
  - [Frontend Setup](#frontend-setup)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [User Roles](#user-roles)
- [License](#license)

---

## Overview

ConstructAI is a full-stack web application built for construction professionals. It uses a YOLOv8 computer vision model to analyze site images, automates permit and compliance tracking, predicts project risks with ML, and computes CPM-based project schedules — all behind a role-based authentication system.

---

## Features

| Feature | Description |
|---|---|
| **Site Image Analysis** | Upload construction site images for YOLOv8 object detection with bounding-box results |
| **AI Risk Assessment** | Gemini-powered narrative risk analysis combined with an ML classifier for risk level prediction |
| **Compliance & Permit Tracking** | State-machine driven permit workflow (initiation → approval → rejection) per project |
| **Clash Detection** | Identify and track structural/MEP clashes in uploaded building plans |
| **Cost & Scheduling** | CPM (Critical Path Method) scheduler with Gantt chart output and Bill-of-Quantities aggregation |
| **Lifecycle Prediction** | Asset lifecycle forecasting based on project parameters |
| **Role-Based Dashboard** | Tailored views for Admin, Professional, and Client roles |
| **User Management** | Admin panel for managing platform users |

---

## Tech Stack

### Backend
- **Runtime**: Python 3.11+
- **Framework**: FastAPI
- **AI / ML**: YOLOv8 (Ultralytics), scikit-learn, Google Gemini (`google-genai`)
- **Scheduling**: NetworkX (CPM), pandas (BoQ)
- **Auth**: JWT (PyJWT), bcrypt (passlib)
- **Databases**: SQLite (users), MongoDB via Motor (compliance & project data)
- **Server**: Uvicorn

### Frontend
- **Framework**: Next.js 16 (App Router)
- **Language**: TypeScript
- **Auth**: NextAuth v4 with Prisma adapter
- **Database ORM**: Prisma v7 (MongoDB)
- **Styling**: Tailwind CSS v4
- **Animation**: Framer Motion
- **PDF Export**: jsPDF + jsPDF-AutoTable
- **Icons**: Lucide React

---

## Project Structure

```
ConstructAI-System/
├── backend/
│   ├── main.py                   # FastAPI entry point (auth, YOLO inference)
│   ├── requirements.txt
│   ├── weights/
│   │   └── best.pt               # YOLOv8 model weights
│   ├── tmp/uploads/              # Temporary image upload storage
│   └── app/
│       ├── core/database.py      # MongoDB async connection
│       ├── dependencies/auth.py  # JWT Bearer guard
│       ├── models/               # Pydantic schemas
│       ├── routers/
│       │   ├── analyze.py        # POST /api/analyze-site
│       │   ├── compliance.py     # /api/v1/compliance
│       │   └── cost_scheduling.py# /api/v1/project/schedule & /boq
│       └── services/
│           ├── yolo_service.py
│           ├── risk_analyzer.py
│           ├── ml_risk_service.py
│           ├── compliance_service.py
│           └── lifecycle_service.py
└── frontend/
    ├── prisma/schema.prisma      # MongoDB schema (User, Account, Session)
    └── src/
        ├── app/                  # Next.js App Router pages
        │   ├── (auth)/           # Login & Register
        │   └── (dashboard)/      # Protected dashboard routes
        ├── components/           # Shared UI components
        ├── lib/                  # API client, auth config, Prisma client
        └── types/
```

---

## Prerequisites

- **Python** 3.11+
- **Node.js** 18+ and **npm** (or pnpm / yarn)
- **MongoDB** instance (local or Atlas) — used by both the backend (Motor) and frontend (Prisma)
- **Google Gemini API key** — for AI-powered risk narratives
- YOLOv8 weights file at `backend/weights/best.pt`

---

## Getting Started

### Backend Setup

```bash
# 1. Navigate to the backend directory
cd backend

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create the .env file (see Environment Variables section)
copy .env.example .env        # Windows
# cp .env.example .env        # macOS / Linux

# 5. Start the development server
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

The API will be available at `http://127.0.0.1:8000`.  
Interactive docs: `http://127.0.0.1:8000/docs`

### Frontend Setup

```bash
# 1. Navigate to the frontend directory
cd frontend

# 2. Install dependencies
npm install

# 3. Create the .env.local file (see Environment Variables section)
copy .env.local.example .env.local   # Windows
# cp .env.local.example .env.local   # macOS / Linux

# 4. Push the Prisma schema to MongoDB
npx prisma db push

# 5. Start the development server
npm run dev
```

The frontend will be available at `http://localhost:3000`.

---

## Environment Variables

### Backend — `backend/.env`

| Variable | Description | Default |
|---|---|---|
| `GEMINI_API_KEY` | Google Gemini API key | *(required)* |
| `MONGODB_URL` | MongoDB connection string | *(required)* |
| `JWT_SECRET_KEY` | Secret key for signing JWTs | `constructai-dev-secret-CHANGE-in-production` |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` |

> **Warning**: Change `JWT_SECRET_KEY` to a strong random value before deploying to production.

### Frontend — `frontend/.env.local`

| Variable | Description |
|---|---|
| `DATABASE_URL` | MongoDB connection string for Prisma |
| `NEXTAUTH_SECRET` | Secret for NextAuth session encryption |
| `NEXTAUTH_URL` | Base URL of the Next.js app (e.g. `http://localhost:3000`) |
| `NEXT_PUBLIC_API_URL` | Backend API base URL (e.g. `http://127.0.0.1:8000`) |

---

## API Reference

All protected endpoints require an `Authorization: Bearer <token>` header.

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/register` | Register a new user |
| `POST` | `/auth/login` | Obtain a JWT access token |

### Site Analysis

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/analyze-site` | Upload an image for YOLOv8 object detection |

### Compliance & Permits

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/compliance/{project_id}/init` | Bootstrap compliance record for a project |
| `GET` | `/api/v1/compliance/{project_id}/status` | Get full permit workflow status |
| `PATCH` | `/api/v1/compliance/{project_id}/update-step` | Advance or revert a permit step |

### Risk Analysis

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/compliance/{project_id}/analyze-risk` | AI + ML risk analysis |

### Cost & Scheduling

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/project/schedule` | CPM schedule with Gantt chart output |
| `POST` | `/api/v1/project/boq` | Bill-of-Quantities cost aggregation |

---

## User Roles

| Role | Access |
|---|---|
| **ADMIN** | Full access including user management |
| **PROFESSIONAL** | Site analysis, compliance, scheduling, risk tools |
| **CLIENT** | Read-only dashboard and project status views |

Roles are assigned at registration and enforced via JWT claims on the backend and session data on the frontend.

---

## License

This project is private and proprietary. All rights reserved.
