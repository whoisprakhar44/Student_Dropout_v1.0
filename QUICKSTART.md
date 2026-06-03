# Quick Start Guide - Student Dropout Prediction System

## System Overview

This is a full-stack application for predicting student dropout risks with:
- **Backend**: FastAPI + SQLite database + 1000 synthetic students
- **Frontend**: Interactive web dashboard with HTML/CSS/JS
- **Database**: Auto-generated with schema from YAML specification

## What's Been Set Up

### ✅ Database Layer
- SQLite database with 8 interconnected tables:
  - `academic_years`: Academic year lookups (2021-22, 2022-23, 2023-24)
  - `schools`: 50 synthetic schools with infrastructure data
  - `students`: 1000 synthetic student records with demographics
  - `social_economic`: Socio-economic characteristics per student
  - `family_background`: Family and parental information
  - `attendance`: Daily attendance tracking (fact table)
  - `academic_scores`: Exam marks per student per year (fact table)
  - `dropout_records`: Dropout status and reasons (target table)

### ✅ Backend APIs
All endpoints auto-generate with proper database connections:

**Authentication**
- `POST /api/login` - User login
- `GET /api/me` - Get current user
- `POST /api/register` - User registration
- `POST /api/logout` - User logout

**Dashboard & Statistics**
- `GET /api/stats` - Dashboard statistics (total students, risk breakdown, attendance %)

**Student Management**
- `GET /api/students` - List students with risk scoring (pagination)
- `GET /api/students/{student_id}` - Detailed student information

**Chat & Query**
- `POST /api/chat/start` - Start a query session
- `POST /api/chat/feedback` - Provide feedback on queries
- `POST /api/chat/approve` - Execute approved queries
- `GET /api/chat/history` - Get chat session history

### ✅ Frontend Connectivity
- Updated `/static/app.js` to use `API_BASE` for backend URL routing
- All API calls now properly connect to backend
- Removed unsupported API calls
- Modal interactions and data binding ready

## How to Run

### 1. **Start the Backend**
```bash
cd c:\Users\2835949\Downloads\level_1_integration\level_1_integration
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

The backend will:
- Auto-initialize the database on first run
- Generate 1000 synthetic students
- Create all tables with proper relationships
- Start serving APIs at `http://localhost:8000`

### 2. **Access the Frontend**
Open your browser:
```
http://localhost:8000
```

The frontend is served directly from the FastAPI app (static files mounted at `/static`).

### 3. **Login**
- Enter any username/password to login (credentials don't matter in demo mode)
- Dashboard will load with real data from the database

### 4. **Explore**
- **Dashboard Tab**: View statistics and risk distribution
- **Students Tab**: Browse all 1000 students with risk scores
- **Chat Tab**: Query the database (placeholder functionality)
- **Modal**: Click any student to see detailed profile

## Key Features

### Risk Scoring Algorithm
Students are assessed on:
- **Attendance**: Low attendance (< 60%) increases risk
- **Academic Performance**: Marks < 200 increases risk
- **Socio-Economic Factors**: BPL status, family structure
- **Chronic Absence**: 30+ days of absence flagged

Risk levels: `critical` (> 60%), `high` (40-60%), `medium` (20-40%), `low` (< 20%)

### Data Distribution
- 1000 students across 50 schools (urban and rural)
- 3 academic years of historical data
- ~10% expected dropout rate (realistic for India)
- Varied attendance patterns and academic performance

### Database Relationships
```
schools (50) 
  ↓ 1-to-many
students (1000)
  ↓ 1-to-many
├── attendance (fact table, 3000 rows)
├── academic_scores (fact table, 3000 rows)
└── dropout_records (fact table, 3000 rows)

students (1-to-1)
├── social_economic (1000 rows)
└── family_background (1000 rows)
```

## API Response Examples

### `GET /api/stats`
```json
{
  "total_students": 1000,
  "critical_risk": 100,
  "high_risk": 150,
  "dropped_out": 95,
  "avg_gpa": 5.2,
  "avg_attendance": 78.5,
  "risk_distribution": [
    {"risk_level": "critical", "count": 100},
    ...
  ],
  "status_distribution": [
    {"current_status": "active", "count": 905},
    {"current_status": "dropped_out", "count": 95}
  ]
}
```

### `GET /api/students?skip=0&limit=50`
```json
[
  {
    "student_adhaar": "123456789012",
    "name": "Aarav Sharma",
    "gender": "M",
    "age": 16,
    "school_name": "BOYS",
    "school_id": 5,
    "risk_level": "high",
    "risk_score": 0.55,
    "current_status": "active",
    "contributing_factors": "Low marks, High absence",
    "recommended_intervention": "Academic support, Attendance tracking"
  },
  ...
]
```

## Troubleshooting

### Backend won't start
- Ensure Python 3.9+ is installed
- Install requirements: `pip install fastapi uvicorn langchain-core`
- Check if port 8000 is available

### Database not initializing
- Delete `database/schema.db` if it exists
- Backend will auto-create on next startup
- Check permissions in the `database/` folder

### Frontend can't connect to backend
- Verify backend is running at `http://localhost:8000`
- Check browser console for CORS errors (should be open)
- Ensure you're accessing the app through the backend URL, not file:// protocol

### No data showing in dashboard
- Wait 10-15 seconds for data generation
- Check `/api/stats` directly in browser to verify data
- Refresh the page

## Next Steps

You can now:
1. ✅ Run the full application end-to-end
2. ✅ Generate analytics reports
3. ✅ Identify at-risk students
4. ✅ Track intervention history
5. ✅ Query the database through the chat interface

All 1000 synthetic students are realistic and based on Indian education data patterns!
