import os
import sqlite3
from datetime import date
from werkzeug.security import generate_password_hash

# erp.db isi backend folder me banegi
DB_PATH = os.path.join(os.path.dirname(__file__), "erp.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # rows ko dictionary jaisa use kar sakte hain
    return conn


def init_db():
    conn = get_db()

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            course TEXT NOT NULL,
            email TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS faculty (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_id TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            department TEXT NOT NULL,
            email TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll TEXT NOT NULL,
            subject TEXT NOT NULL,
            total INTEGER NOT NULL,
            attended INTEGER NOT NULL,
            UNIQUE (roll, subject)
        );

        CREATE TABLE IF NOT EXISTS fees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll TEXT NOT NULL UNIQUE,
            total INTEGER NOT NULL,
            paid INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_id TEXT NOT NULL,
            subject TEXT NOT NULL,
            course TEXT NOT NULL,
            UNIQUE (emp_id, subject)
        );

        CREATE TABLE IF NOT EXISTS attendance_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_id TEXT NOT NULL,
            subject TEXT NOT NULL,
            date TEXT NOT NULL,
            UNIQUE (emp_id, subject, date)
        );

        CREATE TABLE IF NOT EXISTS notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            audience TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll TEXT NOT NULL,
            subject TEXT NOT NULL,
            marks INTEGER NOT NULL,
            UNIQUE (roll, subject)
        );

        CREATE TABLE IF NOT EXISTS timetable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            room TEXT NOT NULL
        );
    """)

    # Demo users (password hash karke save hota hai, seedha nahi)
    demo_users = [
        ("Admin", "admin@campus.edu", "admin123", "admin"),
        ("Faculty", "faculty@campus.edu", "faculty123", "faculty"),
        ("Student", "student@campus.edu", "student123", "student"),
    ]
    for name, email, password, role in demo_users:
        conn.execute(
            "INSERT OR IGNORE INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (name, email, generate_password_hash(password), role),
        )

    # Demo courses
    for course in ["B.Tech CSE", "B.Tech ECE", "BCA", "MBA"]:
        conn.execute("INSERT OR IGNORE INTO courses (name) VALUES (?)", (course,))

    # Demo students (CSE101 wala student@campus.edu se login karta hai)
    demo_students = [
        ("CSE001", "Aman Sharma", "B.Tech CSE", "aman@campus.edu"),
        ("ECE014", "Priya Verma", "B.Tech ECE", "priya@campus.edu"),
        ("CSE101", "Demo Student", "B.Tech CSE", "student@campus.edu"),
    ]
    for roll, name, course, email in demo_students:
        conn.execute(
            "INSERT OR IGNORE INTO students (roll, name, course, email) VALUES (?, ?, ?, ?)",
            (roll, name, course, email),
        )

    # Demo faculty (FAC003 wala faculty@campus.edu se login karta hai)
    demo_faculty = [
        ("FAC001", "Dr. Rakesh Gupta", "Computer Science", "rakesh@campus.edu"),
        ("FAC002", "Prof. Neha Singh", "Electronics", "neha@campus.edu"),
        ("FAC003", "Demo Faculty", "Computer Science", "faculty@campus.edu"),
    ]
    for emp_id, name, department, email in demo_faculty:
        conn.execute(
            "INSERT OR IGNORE INTO faculty (emp_id, name, department, email) VALUES (?, ?, ?, ?)",
            (emp_id, name, department, email),
        )

    # Demo subjects (faculty ka emp_id, subject, kis course ko padhata hai)
    demo_subjects = [
        ("FAC003", "Data Structures", "B.Tech CSE"),
        ("FAC003", "Algorithms", "B.Tech CSE"),
        ("FAC003", "Digital Electronics", "B.Tech ECE"),
    ]
    for emp_id, subject, course in demo_subjects:
        conn.execute(
            "INSERT OR IGNORE INTO subjects (emp_id, subject, course) VALUES (?, ?, ?)",
            (emp_id, subject, course),
        )

    # Demo attendance (roll, subject, total classes, attended classes)
    demo_attendance = [
        ("CSE101", "Data Structures", 40, 34),
        ("CSE101", "DBMS", 38, 30),
        ("CSE101", "Operating Systems", 36, 30),
    ]
    for roll, subject, total, attended in demo_attendance:
        conn.execute(
            "INSERT OR IGNORE INTO attendance (roll, subject, total, attended) VALUES (?, ?, ?, ?)",
            (roll, subject, total, attended),
        )

    # Demo fees (roll, total fees, paid)
    conn.execute(
        "INSERT OR IGNORE INTO fees (roll, total, paid) VALUES (?, ?, ?)",
        ("CSE101", 60000, 48000),
    )

    # Demo results (roll, subject, marks out of 100)
    demo_results = [
        ("CSE101", "Data Structures", 85),
        ("CSE101", "DBMS", 78),
        ("CSE101", "Operating Systems", 72),
    ]
    for roll, subject, marks in demo_results:
        conn.execute(
            "INSERT OR IGNORE INTO results (roll, subject, marks) VALUES (?, ?, ?)",
            (roll, subject, marks),
        )

    # Demo timetable (sirf tab jab table khaali ho)
    if conn.execute("SELECT COUNT(*) FROM timetable").fetchone()[0] == 0:
        demo_timetable = [
            ("FAC003", "Data Structures", "Monday", "09:00", "10:00", "Room 201"),
            ("FAC003", "Data Structures", "Wednesday", "09:00", "10:00", "Room 201"),
            ("FAC003", "Data Structures", "Friday", "09:00", "10:00", "Room 201"),
            ("FAC003", "Algorithms", "Tuesday", "10:00", "11:00", "Room 204"),
            ("FAC003", "Algorithms", "Thursday", "10:00", "11:00", "Room 204"),
            ("FAC003", "Algorithms", "Friday", "10:00", "11:00", "Room 204"),
            ("FAC003", "Digital Electronics", "Monday", "11:30", "12:30", "Lab 1"),
            ("FAC003", "Digital Electronics", "Thursday", "11:30", "12:30", "Lab 1"),
        ]
        for emp_id, subject, day, start, end, room in demo_timetable:
            sub = conn.execute(
                "SELECT id FROM subjects WHERE emp_id = ? AND subject = ?", (emp_id, subject)
            ).fetchone()
            if sub is not None:
                conn.execute(
                    "INSERT INTO timetable (subject_id, day, start_time, end_time, room) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (sub["id"], day, start, end, room),
                )

    # Demo notices (sirf tab jab table khaali ho)
    if conn.execute("SELECT COUNT(*) FROM notices").fetchone()[0] == 0:
        today = date.today().isoformat()
        demo_notices = [
            ("Mid-semester exams", "Exams 20 October se shuru honge.", "all"),
            ("Fee reminder", "Last date fees jama karne ki 15 October hai.", "student"),
            ("Department meeting", "Kal 3 baje seminar hall me meeting hai.", "faculty"),
        ]
        for title, message, audience in demo_notices:
            conn.execute(
                "INSERT INTO notices (title, message, audience, created_at) VALUES (?, ?, ?, ?)",
                (title, message, audience, today),
            )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database ban gaya: erp.db")