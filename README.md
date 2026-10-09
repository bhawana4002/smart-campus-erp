# Smart Campus ERP

A role-based College ERP web app with separate portals for **Admin**, **Faculty** and **Student**.
Built with plain HTML/CSS/JavaScript on the frontend and Python Flask + SQLite on the backend.

## Features

**Admin**
- Manage students and faculty (a login account is created automatically)
- Manage courses and assign subjects to faculty
- Timetable builder with clash checks (same course or same faculty cannot be in two classes at once)
- View subject-wise attendance for every student
- Set fees and record payments
- Publish notices for everyone, only students, or only faculty
- Reports: summary cards, course-wise report, student-wise report with filters and CSV export
- Dashboard with live counts

**Faculty**
- See assigned subjects with student counts and average attendance
- Mark attendance (one entry per subject per day)
- Enter marks for students of own subjects
- Weekly and daily timetable
- Read notices meant for faculty

**Student**
- Dashboard with attendance, pending fees, CGPA, today's classes and notices
- Subject-wise attendance (below 75% is highlighted)
- Fees summary (total, paid, pending)
- Results with grades and CGPA (10-point scale)
- Weekly timetable

**Everyone**
- Login with role selection and change password

## Tech Stack

- Frontend: HTML, CSS, vanilla JavaScript (`fetch` API)
- Backend: Python, Flask, Flask-CORS, python-dotenv
- Database: SQLite
- Auth: signed, expiring tokens (itsdangerous) and password hashing (Werkzeug)

## Security

- Passwords are stored as hashes, never as plain text
- Tokens are signed and expire after 8 hours
- Role checks happen on the server for every protected route
- Teachers can only touch their own subjects; students only see their own data
- All SQL queries use parameter placeholders (no SQL injection)
- User text is escaped before it is shown in the browser (XSS protection)
- CSV export guards against formula injection
- Secret key is read from a `.env` file, not stored in code

## Project Structure

```
erp_project/
├── index.html                  # login page
├── style.css, login.js         # login page styling and logic
├── dashboard.css               # styling for all portal pages
├── layout.js                   # sidebar, auth guard, logout
├── admin-*.html, students.html, faculty.html, courses.html, subjects.html,
│   timetable.html, fees.html, notices.html, reports.html     # admin pages
├── faculty-*.html, my-subjects.html, mark-attendance.html,
│   enter-marks.html                                          # faculty pages
├── student-*.html, notices-view.html                         # student pages
├── change-password.html
└── backend/
    ├── app.py                  # Flask API
    ├── db.py                   # database tables and demo data
    └── requirements.txt
```

## Setup

1. Create the backend environment and install packages

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Create `backend/.env` with a secret key

```bash
echo "SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')" > .env
```

3. Start the backend (runs on http://127.0.0.1:5001). The database and demo data are created on the first run.

```bash
python app.py
```

4. Open `index.html` with a local server (for example the VS Code Live Server extension).

## Demo Accounts

| Role    | Email               | Password   |
|---------|---------------------|------------|
| Admin   | admin@campus.edu    | admin123   |
| Faculty | faculty@campus.edu  | faculty123 |
| Student | student@campus.edu  | student123 |

These are demo accounts only. Change the passwords before using the app for anything real.

## Known Limitations and Future Work

- Login has no rate limiting
- The token is kept in `localStorage` (an httpOnly cookie would be safer)
- CGPA treats every subject with equal weight (no credits)
- API address is hardcoded to `127.0.0.1:5001` in the frontend
- SQLite is used for development; PostgreSQL or MySQL is better for production
- No automated tests yet and no deployment setup (gunicorn, HTTPS)