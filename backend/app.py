import os
import sqlite3
from datetime import date, datetime
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, g, jsonify, request
from flask_cors import CORS
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db, init_db

# backend/.env se settings padho (secret key code me nahi rakhte)
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

app = Flask(__name__)
CORS(app)  # frontend (alag port) ko backend se baat karne deta hai

init_db()  # server start hote hi tables ban jaate hain (pehle se hon to kuch nahi hota)

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY nahi mili. backend/.env me SECRET_KEY=... likho.")
serializer = URLSafeTimedSerializer(SECRET_KEY)
TOKEN_MAX_AGE = 8 * 60 * 60  # 8 ghante baad token expire
MIN_PASSWORD = 6
LOW_ATTENDANCE = 75  # isse kam attendance "kam" maani jaati hai

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAYS = WEEKDAYS[:6]  # timetable Monday se Saturday tak
DAY_ORDER = "CASE t.day " + " ".join(
    "WHEN '%s' THEN %d" % (d, i) for i, d in enumerate(DAYS)
) + " ELSE 9 END"


def login_required(*allowed_roles):
    """Route ke upar lagao. Valid token chahiye, aur role allowed_roles me hona chahiye.
    Koi role na do to har logged-in user chalega.
    Login hue user ki details g.user me milti hain."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return jsonify({"ok": False, "message": "Pehle login karo."}), 401
            try:
                payload = serializer.loads(header[7:], max_age=TOKEN_MAX_AGE)
            except SignatureExpired:
                return jsonify({"ok": False, "message": "Session khatam ho gaya, dubara login karo."}), 401
            except BadSignature:
                return jsonify({"ok": False, "message": "Token galat hai, dubara login karo."}), 401

            if allowed_roles and payload.get("role") not in allowed_roles:
                return jsonify({"ok": False, "message": "Is kaam ki permission nahi hai."}), 403

            g.user = payload
            return func(*args, **kwargs)
        return wrapper
    return decorator


def current_faculty(conn):
    """Login hue faculty ka record (email se)."""
    return conn.execute(
        "SELECT emp_id, name FROM faculty WHERE email = ?", (g.user["email"],)
    ).fetchone()


def to_amount(value):
    """Rupaye ko positive integer me badalta hai. Galat ho to None."""
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return None
    return amount if amount > 0 else None


def grade_for(marks):
    """Marks (100 me se) ko grade aur 10-point scale ke grade point me badalta hai."""
    if marks >= 90:
        return "O", 10
    if marks >= 80:
        return "A+", 9
    if marks >= 70:
        return "A", 8
    if marks >= 60:
        return "B+", 7
    if marks >= 50:
        return "B", 6
    if marks >= 40:
        return "C", 5
    return "F", 0


def cgpa_from(rows):
    """Marks ki rows se CGPA (saare subject barabar weight ke). Koi result na ho to None."""
    if not rows:
        return None
    points = [grade_for(r["marks"])[1] for r in rows]
    return round(sum(points) / len(points), 2)


def timetable_rows(conn, where="", params=()):
    """Timetable ki entries (subject, course, faculty ke saath), din aur time ke order me.
    'where' sirf code ke andar ke fixed text se aata hai, user ke input se kabhi nahi."""
    sql = (
        "SELECT t.id, t.day, t.start_time, t.end_time, t.room, "
        "sub.subject, sub.course, sub.emp_id, f.name AS faculty_name "
        "FROM timetable t JOIN subjects sub ON sub.id = t.subject_id "
        "LEFT JOIN faculty f ON f.emp_id = sub.emp_id " + where +
        " ORDER BY " + DAY_ORDER + ", t.start_time"
    )
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def today_name():
    return WEEKDAYS[date.today().weekday()]


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "message": "ERP backend chal raha hai"})


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    role = data.get("role", "")
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE email = ? AND role = ?", (email, role)
    ).fetchone()
    conn.close()

    # user na mile ya password galat ho, dono me ek hi message
    if user is None or not check_password_hash(user["password_hash"], password):
        return jsonify({"ok": False, "message": "Email, password ya role galat hai."}), 401

    token = serializer.dumps({"email": user["email"], "role": user["role"]})

    return jsonify({
        "ok": True,
        "token": token,
        "user": {"name": user["name"], "email": user["email"], "role": user["role"]},
    })


# ---------------- Password change (har role) ----------------

@app.route("/api/change-password", methods=["POST"])
@login_required()
def change_password():
    data = request.get_json() or {}
    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")

    if len(new_password) < MIN_PASSWORD:
        return jsonify({"ok": False, "message": "Naya password kam se kam " + str(MIN_PASSWORD) + " akshar ka hona chahiye."}), 400

    conn = get_db()
    user = conn.execute(
        "SELECT id, password_hash FROM users WHERE email = ? AND role = ?",
        (g.user["email"], g.user["role"]),
    ).fetchone()

    # 401 nahi, kyunki frontend 401 pe logout kar deta hai
    if user is None or not check_password_hash(user["password_hash"], old_password):
        conn.close()
        return jsonify({"ok": False, "message": "Purana password galat hai."}), 400

    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(new_password), user["id"]),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ---------------- Dashboard stats (admin) ----------------

@app.route("/api/stats", methods=["GET"])
@login_required("admin")
def get_stats():
    conn = get_db()
    students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    faculty = conn.execute("SELECT COUNT(*) FROM faculty").fetchone()[0]
    courses = conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
    pending_fees = conn.execute("SELECT COUNT(*) FROM fees WHERE total > paid").fetchone()[0]
    conn.close()
    return jsonify({
        "students": students,
        "faculty": faculty,
        "courses": courses,
        "pending_fees": pending_fees,
    })


# ---------------- Reports (admin) ----------------

@app.route("/api/reports", methods=["GET"])
@login_required("admin")
def get_reports():
    conn = get_db()
    students = conn.execute("SELECT roll, name, course FROM students ORDER BY roll").fetchall()
    att_rows = conn.execute(
        "SELECT roll, SUM(total) AS total, SUM(attended) AS attended FROM attendance GROUP BY roll"
    ).fetchall()
    fee_rows = conn.execute("SELECT roll, total, paid FROM fees").fetchall()
    result_rows = conn.execute("SELECT roll, marks FROM results").fetchall()
    conn.close()

    att = {r["roll"]: r for r in att_rows}
    fees = {r["roll"]: r for r in fee_rows}
    marks_by_roll = {}
    for r in result_rows:
        marks_by_roll.setdefault(r["roll"], []).append(r)

    # Har student ki ek row: attendance, fees aur CGPA
    people = []
    for s in students:
        a = att.get(s["roll"])
        percent = round(a["attended"] * 100 / a["total"]) if a and a["total"] else None
        f = fees.get(s["roll"])
        fee_total = f["total"] if f else 0
        fee_paid = f["paid"] if f else 0
        people.append({
            "roll": s["roll"],
            "name": s["name"],
            "course": s["course"],
            "attendance": percent,
            "fees_total": fee_total,
            "fees_paid": fee_paid,
            "fees_pending": fee_total - fee_paid,
            "cgpa": cgpa_from(marks_by_roll.get(s["roll"], [])),
        })

    # Course-wise summary
    grouped = {}
    for p in people:
        c = grouped.setdefault(p["course"], {
            "course": p["course"], "students": 0, "att": [], "cgpa": [],
            "fees_total": 0, "fees_paid": 0,
        })
        c["students"] += 1
        if p["attendance"] is not None:
            c["att"].append(p["attendance"])
        if p["cgpa"] is not None:
            c["cgpa"].append(p["cgpa"])
        c["fees_total"] += p["fees_total"]
        c["fees_paid"] += p["fees_paid"]

    courses = []
    for c in grouped.values():
        courses.append({
            "course": c["course"],
            "students": c["students"],
            "avg_attendance": round(sum(c["att"]) / len(c["att"])) if c["att"] else None,
            "avg_cgpa": round(sum(c["cgpa"]) / len(c["cgpa"]), 2) if c["cgpa"] else None,
            "fees_total": c["fees_total"],
            "fees_paid": c["fees_paid"],
            "fees_pending": c["fees_total"] - c["fees_paid"],
        })

    fees_total = sum(p["fees_total"] for p in people)
    fees_paid = sum(p["fees_paid"] for p in people)
    summary = {
        "students": len(people),
        "low_attendance": sum(
            1 for p in people if p["attendance"] is not None and p["attendance"] < LOW_ATTENDANCE
        ),
        "fees_total": fees_total,
        "fees_paid": fees_paid,
        "fees_pending": fees_total - fees_paid,
        "collection_percent": round(fees_paid * 100 / fees_total) if fees_total else 0,
        "low_limit": LOW_ATTENDANCE,
    }

    return jsonify({"summary": summary, "courses": courses, "students": people})


# ---------------- Courses (admin) ----------------

@app.route("/api/courses", methods=["GET"])
@login_required("admin")
def get_courses():
    conn = get_db()
    rows = conn.execute("SELECT id, name FROM courses ORDER BY id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/courses", methods=["POST"])
@login_required("admin")
def add_course():
    data = request.get_json() or {}
    name = data.get("name", "").strip()

    if not name:
        return jsonify({"ok": False, "message": "Course ka naam likho."}), 400

    conn = get_db()
    try:
        conn.execute("INSERT INTO courses (name) VALUES (?)", (name,))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"ok": False, "message": "Ye course pehle se hai."}), 409
    conn.close()
    return jsonify({"ok": True}), 201


@app.route("/api/courses/<int:course_id>", methods=["DELETE"])
@login_required("admin")
def delete_course(course_id):
    conn = get_db()
    course = conn.execute("SELECT name FROM courses WHERE id = ?", (course_id,)).fetchone()
    if course is None:
        conn.close()
        return jsonify({"ok": False, "message": "Ye course nahi mila."}), 404

    # Agar is course me students ya subjects hain to delete nahi hoga
    students = conn.execute(
        "SELECT COUNT(*) FROM students WHERE course = ?", (course["name"],)
    ).fetchone()[0]
    subjects = conn.execute(
        "SELECT COUNT(*) FROM subjects WHERE course = ?", (course["name"],)
    ).fetchone()[0]
    if students or subjects:
        conn.close()
        return jsonify({
            "ok": False,
            "message": "Is course me " + str(students) + " student aur " + str(subjects) +
                       " subject hain. Pehle unhe hatao.",
        }), 409

    conn.execute("DELETE FROM courses WHERE id = ?", (course_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ---------------- Subjects (admin) ----------------

@app.route("/api/subjects", methods=["GET"])
@login_required("admin")
def get_subjects():
    conn = get_db()
    rows = conn.execute(
        "SELECT sub.id, sub.subject, sub.course, sub.emp_id, f.name AS faculty_name "
        "FROM subjects sub LEFT JOIN faculty f ON f.emp_id = sub.emp_id ORDER BY sub.id"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/subjects", methods=["POST"])
@login_required("admin")
def add_subject():
    data = request.get_json() or {}
    emp_id = data.get("emp_id", "").strip()
    subject = data.get("subject", "").strip()
    course = data.get("course", "").strip()

    if not (emp_id and subject and course):
        return jsonify({"ok": False, "message": "Saari details bharo."}), 400

    conn = get_db()
    if conn.execute("SELECT 1 FROM faculty WHERE emp_id = ?", (emp_id,)).fetchone() is None:
        conn.close()
        return jsonify({"ok": False, "message": "Ye faculty nahi mila."}), 404
    if conn.execute("SELECT 1 FROM courses WHERE name = ?", (course,)).fetchone() is None:
        conn.close()
        return jsonify({"ok": False, "message": "Ye course nahi mila."}), 404

    try:
        conn.execute(
            "INSERT INTO subjects (emp_id, subject, course) VALUES (?, ?, ?)",
            (emp_id, subject, course),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"ok": False, "message": "Ye subject is faculty ko pehle se assign hai."}), 409
    conn.close()
    return jsonify({"ok": True}), 201


@app.route("/api/subjects/<int:subject_id>", methods=["DELETE"])
@login_required("admin")
def delete_subject(subject_id):
    conn = get_db()
    conn.execute("DELETE FROM timetable WHERE subject_id = ?", (subject_id,))  # uski classes bhi hatao
    conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ---------------- Timetable (admin) ----------------

@app.route("/api/timetable", methods=["GET"])
@login_required("admin")
def get_timetable():
    conn = get_db()
    rows = timetable_rows(conn)
    conn.close()
    return jsonify(rows)


@app.route("/api/timetable", methods=["POST"])
@login_required("admin")
def add_timetable():
    data = request.get_json() or {}
    day = data.get("day", "").strip()
    room = data.get("room", "").strip()

    try:
        subject_id = int(data.get("subject_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "message": "Subject chuno."}), 400
    if day not in DAYS:
        return jsonify({"ok": False, "message": "Din galat hai."}), 400
    if not room or len(room) > 30:
        return jsonify({"ok": False, "message": "Room ka naam likho (30 akshar tak)."}), 400

    try:
        start = datetime.strptime(data.get("start_time", "").strip(), "%H:%M")
        end = datetime.strptime(data.get("end_time", "").strip(), "%H:%M")
    except ValueError:
        return jsonify({"ok": False, "message": "Time sahi format me daalo."}), 400
    if start >= end:
        return jsonify({"ok": False, "message": "End time start time ke baad ka hona chahiye."}), 400

    # HH:MM me save karte hain, taaki text se compare karne par bhi order sahi rahe
    start_text = start.strftime("%H:%M")
    end_text = end.strftime("%H:%M")

    conn = get_db()
    sub = conn.execute(
        "SELECT course, emp_id FROM subjects WHERE id = ?", (subject_id,)
    ).fetchone()
    if sub is None:
        conn.close()
        return jsonify({"ok": False, "message": "Ye subject nahi mila."}), 404

    # Us din us time se takrane wali classes
    clashes = conn.execute(
        "SELECT sub.course, sub.emp_id FROM timetable t "
        "JOIN subjects sub ON sub.id = t.subject_id "
        "WHERE t.day = ? AND t.start_time < ? AND t.end_time > ?",
        (day, end_text, start_text),
    ).fetchall()
    for c in clashes:
        if c["course"] == sub["course"]:
            conn.close()
            return jsonify({"ok": False, "message": "Is course ki us time pe pehle se class hai."}), 409
        if c["emp_id"] == sub["emp_id"]:
            conn.close()
            return jsonify({"ok": False, "message": "Ye faculty us time pe kisi aur class me hai."}), 409

    conn.execute(
        "INSERT INTO timetable (subject_id, day, start_time, end_time, room) VALUES (?, ?, ?, ?, ?)",
        (subject_id, day, start_text, end_text, room),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True}), 201


@app.route("/api/timetable/<int:entry_id>", methods=["DELETE"])
@login_required("admin")
def delete_timetable(entry_id):
    conn = get_db()
    conn.execute("DELETE FROM timetable WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ---------------- Timetable (student aur faculty apna dekhte hain) ----------------

@app.route("/api/my/timetable", methods=["GET"])
@login_required("student")
def my_timetable():
    conn = get_db()
    student = conn.execute(
        "SELECT course FROM students WHERE email = ?", (g.user["email"],)
    ).fetchone()

    if student is None:
        conn.close()
        return jsonify({"ok": False, "message": "Is email ka student record nahi mila."}), 404

    entries = timetable_rows(conn, "WHERE sub.course = ?", (student["course"],))
    conn.close()
    return jsonify({"ok": True, "today": today_name(), "entries": entries})


@app.route("/api/my/faculty-timetable", methods=["GET"])
@login_required("faculty")
def my_faculty_timetable():
    conn = get_db()
    fac = current_faculty(conn)

    if fac is None:
        conn.close()
        return jsonify({"ok": False, "message": "Is email ka faculty record nahi mila."}), 404

    entries = timetable_rows(conn, "WHERE sub.emp_id = ?", (fac["emp_id"],))
    conn.close()
    return jsonify({"ok": True, "today": today_name(), "entries": entries})


# ---------------- Notices ----------------

@app.route("/api/notices", methods=["GET"])
@login_required()
def get_notices():
    role = g.user["role"]
    conn = get_db()
    if role == "admin":
        rows = conn.execute(
            "SELECT id, title, message, audience, created_at FROM notices ORDER BY id DESC"
        ).fetchall()
    else:
        # Student ko 'all' aur 'student' wale, faculty ko 'all' aur 'faculty' wale
        rows = conn.execute(
            "SELECT id, title, message, audience, created_at FROM notices "
            "WHERE audience IN ('all', ?) ORDER BY id DESC",
            (role,),
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/notices", methods=["POST"])
@login_required("admin")
def add_notice():
    data = request.get_json() or {}
    title = data.get("title", "").strip()
    message = data.get("message", "").strip()
    audience = data.get("audience", "").strip()

    if not (title and message):
        return jsonify({"ok": False, "message": "Title aur message dono bharo."}), 400
    if audience not in ("all", "student", "faculty"):
        return jsonify({"ok": False, "message": "Audience galat hai."}), 400

    conn = get_db()
    conn.execute(
        "INSERT INTO notices (title, message, audience, created_at) VALUES (?, ?, ?, ?)",
        (title, message, audience, date.today().isoformat()),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True}), 201


@app.route("/api/notices/<int:notice_id>", methods=["DELETE"])
@login_required("admin")
def delete_notice(notice_id):
    conn = get_db()
    conn.execute("DELETE FROM notices WHERE id = ?", (notice_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ---------------- Student dashboard summary ----------------

@app.route("/api/my/summary", methods=["GET"])
@login_required("student")
def my_summary():
    conn = get_db()
    student = conn.execute(
        "SELECT roll, name FROM students WHERE email = ?", (g.user["email"],)
    ).fetchone()

    if student is None:
        conn.close()
        return jsonify({"ok": False, "message": "Is email ka student record nahi mila."}), 404

    roll = student["roll"]
    att = conn.execute(
        "SELECT total, attended FROM attendance WHERE roll = ?", (roll,)
    ).fetchall()
    fee = conn.execute("SELECT total, paid FROM fees WHERE roll = ?", (roll,)).fetchone()
    res = conn.execute("SELECT marks FROM results WHERE roll = ?", (roll,)).fetchall()
    conn.close()

    total_classes = sum(a["total"] for a in att)
    attended = sum(a["attended"] for a in att)
    percent = round(attended * 100 / total_classes) if total_classes else 0
    pending = (fee["total"] - fee["paid"]) if fee else 0

    return jsonify({
        "ok": True,
        "name": student["name"],
        "attendance": percent,
        "pending_fees": pending,
        "courses": len(att),
        "cgpa": cgpa_from(res),
    })


# ---------------- Student attendance (subject-wise) ----------------

@app.route("/api/my/attendance", methods=["GET"])
@login_required("student")
def my_attendance():
    conn = get_db()
    student = conn.execute(
        "SELECT roll, name FROM students WHERE email = ?", (g.user["email"],)
    ).fetchone()

    if student is None:
        conn.close()
        return jsonify({"ok": False, "message": "Is email ka student record nahi mila."}), 404

    rows = conn.execute(
        "SELECT subject, total, attended FROM attendance WHERE roll = ? ORDER BY subject",
        (student["roll"],),
    ).fetchall()
    conn.close()

    subjects = []
    for r in rows:
        percent = round(r["attended"] * 100 / r["total"]) if r["total"] else 0
        subjects.append({
            "subject": r["subject"],
            "total": r["total"],
            "attended": r["attended"],
            "percent": percent,
        })

    total = sum(r["total"] for r in rows)
    attended = sum(r["attended"] for r in rows)
    overall = round(attended * 100 / total) if total else 0

    return jsonify({"ok": True, "overall": overall, "subjects": subjects})


# ---------------- Student fees ----------------

@app.route("/api/my/fees", methods=["GET"])
@login_required("student")
def my_fees():
    conn = get_db()
    student = conn.execute(
        "SELECT roll FROM students WHERE email = ?", (g.user["email"],)
    ).fetchone()

    if student is None:
        conn.close()
        return jsonify({"ok": False, "message": "Is email ka student record nahi mila."}), 404

    fee = conn.execute(
        "SELECT total, paid FROM fees WHERE roll = ?", (student["roll"],)
    ).fetchone()
    conn.close()

    total = fee["total"] if fee else 0
    paid = fee["paid"] if fee else 0
    return jsonify({"ok": True, "total": total, "paid": paid, "pending": total - paid})


# ---------------- Student results ----------------

@app.route("/api/my/results", methods=["GET"])
@login_required("student")
def my_results():
    conn = get_db()
    student = conn.execute(
        "SELECT roll FROM students WHERE email = ?", (g.user["email"],)
    ).fetchone()

    if student is None:
        conn.close()
        return jsonify({"ok": False, "message": "Is email ka student record nahi mila."}), 404

    rows = conn.execute(
        "SELECT subject, marks FROM results WHERE roll = ? ORDER BY subject", (student["roll"],)
    ).fetchall()
    conn.close()

    subjects = []
    for r in rows:
        grade, point = grade_for(r["marks"])
        subjects.append({
            "subject": r["subject"],
            "marks": r["marks"],
            "grade": grade,
            "point": point,
        })

    return jsonify({"ok": True, "cgpa": cgpa_from(rows), "subjects": subjects})


# ---------------- Results (faculty marks daalta hai) ----------------

@app.route("/api/results/class", methods=["GET"])
@login_required("faculty")
def results_class():
    subject = request.args.get("subject", "").strip()

    conn = get_db()
    fac = current_faculty(conn)
    if fac is None:
        conn.close()
        return jsonify({"ok": False, "message": "Faculty record nahi mila."}), 404

    sub = conn.execute(
        "SELECT course FROM subjects WHERE emp_id = ? AND subject = ?", (fac["emp_id"], subject)
    ).fetchone()
    if sub is None:
        conn.close()
        return jsonify({"ok": False, "message": "Ye subject aapka nahi hai."}), 404

    students = conn.execute(
        "SELECT s.roll, s.name, r.marks FROM students s "
        "LEFT JOIN results r ON r.roll = s.roll AND r.subject = ? "
        "WHERE s.course = ? ORDER BY s.roll",
        (subject, sub["course"]),
    ).fetchall()
    conn.close()

    return jsonify({
        "ok": True,
        "course": sub["course"],
        "students": [dict(s) for s in students],
    })


@app.route("/api/results/save", methods=["POST"])
@login_required("faculty")
def results_save():
    data = request.get_json() or {}
    subject = data.get("subject", "").strip()
    marks = data.get("marks", {})

    if not isinstance(marks, dict):
        return jsonify({"ok": False, "message": "Marks sahi format me nahi hain."}), 400

    conn = get_db()
    fac = current_faculty(conn)
    if fac is None:
        conn.close()
        return jsonify({"ok": False, "message": "Faculty record nahi mila."}), 404

    sub = conn.execute(
        "SELECT course FROM subjects WHERE emp_id = ? AND subject = ?", (fac["emp_id"], subject)
    ).fetchone()
    if sub is None:
        conn.close()
        return jsonify({"ok": False, "message": "Ye subject aapka nahi hai."}), 404

    rolls = {
        r["roll"] for r in conn.execute(
            "SELECT roll FROM students WHERE course = ?", (sub["course"],)
        ).fetchall()
    }

    # Pehle sab validate karo, phir save. Ek bhi galat ho to kuch save nahi hoga.
    clean = {}
    for roll, value in marks.items():
        if roll not in rolls:
            conn.close()
            return jsonify({"ok": False, "message": "Roll " + str(roll) + " is subject ke course ka nahi hai."}), 400
        if str(value).strip() == "":
            continue  # khaali chhoda hai to skip
        try:
            number = int(value)
        except (TypeError, ValueError):
            conn.close()
            return jsonify({"ok": False, "message": "Roll " + str(roll) + " ke marks poore number me daalo."}), 400
        if number < 0 or number > 100:
            conn.close()
            return jsonify({"ok": False, "message": "Roll " + str(roll) + " ke marks 0 se 100 ke beech hone chahiye."}), 400
        clean[roll] = number

    for roll, number in clean.items():
        conn.execute(
            "INSERT INTO results (roll, subject, marks) VALUES (?, ?, ?) "
            "ON CONFLICT(roll, subject) DO UPDATE SET marks = excluded.marks",
            (roll, subject, number),
        )

    conn.commit()
    conn.close()
    return jsonify({"ok": True, "saved": len(clean)})


# ---------------- Faculty dashboard summary ----------------

@app.route("/api/my/faculty-summary", methods=["GET"])
@login_required("faculty")
def faculty_summary():
    conn = get_db()
    fac = current_faculty(conn)

    if fac is None:
        conn.close()
        return jsonify({"ok": False, "message": "Is email ka faculty record nahi mila."}), 404

    subjects = conn.execute(
        "SELECT subject, course FROM subjects WHERE emp_id = ? ORDER BY id", (fac["emp_id"],)
    ).fetchall()

    # Un courses ke students, jinhe ye faculty padhata hai (ek student ek hi baar gina jayega)
    students = conn.execute(
        "SELECT COUNT(DISTINCT s.roll) FROM students s "
        "JOIN subjects sub ON s.course = sub.course WHERE sub.emp_id = ?",
        (fac["emp_id"],),
    ).fetchone()[0]

    # Aaj kitne subjects ki attendance lag chuki hai
    done_today = conn.execute(
        "SELECT COUNT(*) FROM attendance_sessions WHERE emp_id = ? AND date = ?",
        (fac["emp_id"], date.today().isoformat()),
    ).fetchone()[0]
    conn.close()

    return jsonify({
        "ok": True,
        "name": fac["name"],
        "subjects_count": len(subjects),
        "students": students,
        "attendance_pending": max(len(subjects) - done_today, 0),
        "subjects": [dict(s) for s in subjects],
    })


# ---------------- Attendance (faculty) ----------------

@app.route("/api/attendance/class", methods=["GET"])
@login_required("faculty")
def attendance_class():
    subject = request.args.get("subject", "").strip()

    conn = get_db()
    fac = current_faculty(conn)
    if fac is None:
        conn.close()
        return jsonify({"ok": False, "message": "Faculty record nahi mila."}), 404

    sub = conn.execute(
        "SELECT course FROM subjects WHERE emp_id = ? AND subject = ?", (fac["emp_id"], subject)
    ).fetchone()
    if sub is None:
        conn.close()
        return jsonify({"ok": False, "message": "Ye subject aapka nahi hai."}), 404

    students = conn.execute(
        "SELECT roll, name FROM students WHERE course = ? ORDER BY roll", (sub["course"],)
    ).fetchall()
    done = conn.execute(
        "SELECT 1 FROM attendance_sessions WHERE emp_id = ? AND subject = ? AND date = ?",
        (fac["emp_id"], subject, date.today().isoformat()),
    ).fetchone()
    conn.close()

    return jsonify({
        "ok": True,
        "course": sub["course"],
        "already_marked": done is not None,
        "students": [dict(s) for s in students],
    })


@app.route("/api/attendance/mark", methods=["POST"])
@login_required("faculty")
def attendance_mark():
    data = request.get_json() or {}
    subject = data.get("subject", "").strip()
    present = set(data.get("present", []))

    conn = get_db()
    fac = current_faculty(conn)
    if fac is None:
        conn.close()
        return jsonify({"ok": False, "message": "Faculty record nahi mila."}), 404

    sub = conn.execute(
        "SELECT course FROM subjects WHERE emp_id = ? AND subject = ?", (fac["emp_id"], subject)
    ).fetchone()
    if sub is None:
        conn.close()
        return jsonify({"ok": False, "message": "Ye subject aapka nahi hai."}), 404

    # Aaj ki attendance ek hi baar lag sakti hai
    try:
        conn.execute(
            "INSERT INTO attendance_sessions (emp_id, subject, date) VALUES (?, ?, ?)",
            (fac["emp_id"], subject, date.today().isoformat()),
        )
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"ok": False, "message": "Aaj ki attendance pehle se lag chuki hai."}), 409

    students = conn.execute(
        "SELECT roll FROM students WHERE course = ?", (sub["course"],)
    ).fetchall()

    present_count = 0
    for s in students:
        roll = s["roll"]
        is_present = 1 if roll in present else 0
        present_count += is_present
        conn.execute(
            "INSERT OR IGNORE INTO attendance (roll, subject, total, attended) VALUES (?, ?, 0, 0)",
            (roll, subject),
        )
        conn.execute(
            "UPDATE attendance SET total = total + 1, attended = attended + ? "
            "WHERE roll = ? AND subject = ?",
            (is_present, roll, subject),
        )

    conn.commit()
    conn.close()
    return jsonify({"ok": True, "total": len(students), "present": present_count})


# ---------------- Fees (admin) ----------------

@app.route("/api/fees", methods=["GET"])
@login_required("admin")
def get_fees():
    conn = get_db()
    rows = conn.execute(
        "SELECT s.roll, s.name, s.course, COALESCE(f.total, 0) AS total, COALESCE(f.paid, 0) AS paid "
        "FROM students s LEFT JOIN fees f ON f.roll = s.roll ORDER BY s.id"
    ).fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append({
            "roll": r["roll"],
            "name": r["name"],
            "course": r["course"],
            "total": r["total"],
            "paid": r["paid"],
            "pending": r["total"] - r["paid"],
        })
    return jsonify(result)


@app.route("/api/fees/set-total", methods=["POST"])
@login_required("admin")
def set_total_fees():
    data = request.get_json() or {}
    roll = data.get("roll", "").strip()
    total = to_amount(data.get("total"))

    if not roll or total is None:
        return jsonify({"ok": False, "message": "Student chuno aur sahi amount daalo."}), 400

    conn = get_db()
    student = conn.execute("SELECT 1 FROM students WHERE roll = ?", (roll,)).fetchone()
    if student is None:
        conn.close()
        return jsonify({"ok": False, "message": "Ye student nahi mila."}), 404

    fee = conn.execute("SELECT paid FROM fees WHERE roll = ?", (roll,)).fetchone()
    if fee is None:
        conn.execute("INSERT INTO fees (roll, total, paid) VALUES (?, ?, 0)", (roll, total))
    else:
        if total < fee["paid"]:
            conn.close()
            return jsonify({"ok": False, "message": "Total fees jama ho chuki fees se kam nahi ho sakti."}), 400
        conn.execute("UPDATE fees SET total = ? WHERE roll = ?", (total, roll))

    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/fees/payment", methods=["POST"])
@login_required("admin")
def record_payment():
    data = request.get_json() or {}
    roll = data.get("roll", "").strip()
    amount = to_amount(data.get("amount"))

    if not roll or amount is None:
        return jsonify({"ok": False, "message": "Student chuno aur sahi amount daalo."}), 400

    conn = get_db()
    fee = conn.execute("SELECT total, paid FROM fees WHERE roll = ?", (roll,)).fetchone()
    if fee is None:
        conn.close()
        return jsonify({"ok": False, "message": "Is student ki total fees set nahi hai. Pehle total fees set karo."}), 404

    pending = fee["total"] - fee["paid"]
    if amount > pending:
        conn.close()
        return jsonify({"ok": False, "message": "Amount baaki fees (₹" + str(pending) + ") se zyada hai."}), 400

    conn.execute("UPDATE fees SET paid = paid + ? WHERE roll = ?", (amount, roll))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "pending": pending - amount})


# ---------------- Students ----------------

@app.route("/api/students", methods=["GET"])
@login_required("admin")
def get_students():
    conn = get_db()
    rows = conn.execute("SELECT roll, name, course, email FROM students ORDER BY id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/students", methods=["POST"])
@login_required("admin")
def add_student():
    data = request.get_json() or {}
    roll = data.get("roll", "").strip()
    name = data.get("name", "").strip()
    course = data.get("course", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not (roll and name and course and email and password):
        return jsonify({"ok": False, "message": "Saari details bharo (password bhi)."}), 400
    if len(password) < MIN_PASSWORD:
        return jsonify({"ok": False, "message": "Password kam se kam " + str(MIN_PASSWORD) + " akshar ka hona chahiye."}), 400

    conn = get_db()
    if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        conn.close()
        return jsonify({"ok": False, "message": "Is email ka login pehle se hai."}), 409

    # Student aur uska login ek saath banta hai. Ek bhi fail ho to dono wapas.
    try:
        conn.execute(
            "INSERT INTO students (roll, name, course, email) VALUES (?, ?, ?, ?)",
            (roll, name, course, email),
        )
        conn.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'student')",
            (name, email, generate_password_hash(password)),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()
        return jsonify({"ok": False, "message": "Ye roll number pehle se hai."}), 409
    conn.close()
    return jsonify({"ok": True}), 201


@app.route("/api/students/<roll>", methods=["DELETE"])
@login_required("admin")
def delete_student(roll):
    conn = get_db()
    student = conn.execute("SELECT email FROM students WHERE roll = ?", (roll,)).fetchone()
    if student is not None:
        conn.execute("DELETE FROM users WHERE email = ? AND role = 'student'", (student["email"],))
        conn.execute("DELETE FROM attendance WHERE roll = ?", (roll,))
        conn.execute("DELETE FROM fees WHERE roll = ?", (roll,))
        conn.execute("DELETE FROM results WHERE roll = ?", (roll,))
        conn.execute("DELETE FROM students WHERE roll = ?", (roll,))
        conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ---------------- Faculty ----------------

@app.route("/api/faculty", methods=["GET"])
@login_required("admin")
def get_faculty():
    conn = get_db()
    rows = conn.execute("SELECT emp_id, name, department, email FROM faculty ORDER BY id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/faculty", methods=["POST"])
@login_required("admin")
def add_faculty():
    data = request.get_json() or {}
    emp_id = data.get("emp_id", "").strip()
    name = data.get("name", "").strip()
    department = data.get("department", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not (emp_id and name and department and email and password):
        return jsonify({"ok": False, "message": "Saari details bharo (password bhi)."}), 400
    if len(password) < MIN_PASSWORD:
        return jsonify({"ok": False, "message": "Password kam se kam " + str(MIN_PASSWORD) + " akshar ka hona chahiye."}), 400

    conn = get_db()
    if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        conn.close()
        return jsonify({"ok": False, "message": "Is email ka login pehle se hai."}), 409

    # Faculty aur uska login ek saath banta hai. Ek bhi fail ho to dono wapas.
    try:
        conn.execute(
            "INSERT INTO faculty (emp_id, name, department, email) VALUES (?, ?, ?, ?)",
            (emp_id, name, department, email),
        )
        conn.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'faculty')",
            (name, email, generate_password_hash(password)),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()
        return jsonify({"ok": False, "message": "Ye employee ID pehle se hai."}), 409
    conn.close()
    return jsonify({"ok": True}), 201


@app.route("/api/faculty/<emp_id>", methods=["DELETE"])
@login_required("admin")
def delete_faculty(emp_id):
    conn = get_db()
    fac = conn.execute("SELECT email FROM faculty WHERE emp_id = ?", (emp_id,)).fetchone()
    if fac is not None:
        conn.execute("DELETE FROM users WHERE email = ? AND role = 'faculty'", (fac["email"],))
        # uske subjects ki timetable classes, phir subject assignments bhi hatao
        conn.execute(
            "DELETE FROM timetable WHERE subject_id IN (SELECT id FROM subjects WHERE emp_id = ?)",
            (emp_id,),
        )
        conn.execute("DELETE FROM subjects WHERE emp_id = ?", (emp_id,))
        conn.execute("DELETE FROM faculty WHERE emp_id = ?", (emp_id,))
        conn.commit()
    conn.close()
    return jsonify({"ok": True})

# ---------------- Subject-wise attendance ka hisaab (helper) ----------------

def subject_stats(conn, sub, emp_id):
    """Ek subject ke students, classes aur average attendance."""
    students = conn.execute(
        "SELECT COUNT(*) FROM students WHERE course = ?", (sub["course"],)
    ).fetchone()[0]
    classes_held = conn.execute(
        "SELECT COUNT(*) FROM attendance_sessions WHERE emp_id = ? AND subject = ?",
        (emp_id, sub["subject"]),
    ).fetchone()[0]
    weekly = conn.execute(
        "SELECT COUNT(*) FROM timetable WHERE subject_id = ?", (sub["id"],)
    ).fetchone()[0]
    totals = conn.execute(
        "SELECT SUM(a.total) AS total, SUM(a.attended) AS attended "
        "FROM attendance a JOIN students s ON s.roll = a.roll "
        "WHERE a.subject = ? AND s.course = ?",
        (sub["subject"], sub["course"]),
    ).fetchone()
    avg = None
    if totals["total"]:
        avg = round(totals["attended"] * 100 / totals["total"])
    return {
        "subject": sub["subject"],
        "course": sub["course"],
        "students": students,
        "classes_held": classes_held,
        "weekly_classes": weekly,
        "avg_attendance": avg,
    }


# ---------------- Faculty: My Subjects ----------------

@app.route("/api/my/subjects-detail", methods=["GET"])
@login_required("faculty")
def my_subjects_detail():
    conn = get_db()
    fac = current_faculty(conn)
    if fac is None:
        conn.close()
        return jsonify({"ok": False, "message": "Is email ka faculty record nahi mila."}), 404

    subs = conn.execute(
        "SELECT id, subject, course FROM subjects WHERE emp_id = ? ORDER BY id", (fac["emp_id"],)
    ).fetchall()
    result = [subject_stats(conn, s, fac["emp_id"]) for s in subs]
    conn.close()
    return jsonify({"ok": True, "low_limit": LOW_ATTENDANCE, "subjects": result})


# ---------------- Admin: Attendance ----------------

@app.route("/api/attendance/overview", methods=["GET"])
@login_required("admin")
def attendance_overview():
    conn = get_db()
    subs = conn.execute(
        "SELECT sub.id, sub.subject, sub.course, sub.emp_id, f.name AS faculty_name "
        "FROM subjects sub LEFT JOIN faculty f ON f.emp_id = sub.emp_id ORDER BY sub.id"
    ).fetchall()

    result = []
    for s in subs:
        row = subject_stats(conn, s, s["emp_id"])
        row["id"] = s["id"]
        row["faculty_name"] = s["faculty_name"] or s["emp_id"]
        result.append(row)
    conn.close()
    return jsonify({"ok": True, "low_limit": LOW_ATTENDANCE, "subjects": result})


@app.route("/api/attendance/subject/<int:subject_id>", methods=["GET"])
@login_required("admin")
def attendance_subject(subject_id):
    conn = get_db()
    sub = conn.execute(
        "SELECT subject, course FROM subjects WHERE id = ?", (subject_id,)
    ).fetchone()
    if sub is None:
        conn.close()
        return jsonify({"ok": False, "message": "Ye subject nahi mila."}), 404

    rows = conn.execute(
        "SELECT s.roll, s.name, COALESCE(a.total, 0) AS total, COALESCE(a.attended, 0) AS attended "
        "FROM students s LEFT JOIN attendance a ON a.roll = s.roll AND a.subject = ? "
        "WHERE s.course = ? ORDER BY s.roll",
        (sub["subject"], sub["course"]),
    ).fetchall()
    conn.close()

    students = []
    for r in rows:
        percent = round(r["attended"] * 100 / r["total"]) if r["total"] else None
        students.append({
            "roll": r["roll"],
            "name": r["name"],
            "total": r["total"],
            "attended": r["attended"],
            "percent": percent,
        })
    return jsonify({
        "ok": True,
        "subject": sub["subject"],
        "course": sub["course"],
        "low_limit": LOW_ATTENDANCE,
        "students": students,
    })


if __name__ == "__main__":
    app.run(debug=True, port=5001)