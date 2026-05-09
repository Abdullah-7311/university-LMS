"""
University LMS Backend
Flask REST API with SQLite (or MySQL) database
Run: python lms_backend.py
"""

from flask import Flask, request, jsonify, session
from flask_cors import CORS
import hashlib
import datetime
import sqlite3

app = Flask(__name__)
app.secret_key = "university_lms_secret_2024"
CORS(app, supports_credentials=True, origins="*")

# ─────────────────────────────────────────────
# DATABASE CONFIGURATION
# Set USE_MYSQL = True and fill MYSQL_CONFIG
# to switch from SQLite to MySQL.
# ─────────────────────────────────────────────
USE_MYSQL = False

MYSQL_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "your_password",
    "database": "university_lms"
}

DB_FILE = "lms_database.db"


def get_connection():
    if USE_MYSQL:
        import mysql.connector
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        return conn, conn.cursor(dictionary=True)
    else:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn, conn.cursor()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def row_to_dict(row):
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(row)


def rows_to_list(rows):
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# DATABASE INITIALISATION
# ─────────────────────────────────────────────
def init_db():
    conn, cur = get_connection()

    if USE_MYSQL:
        cur.execute("CREATE DATABASE IF NOT EXISTS university_lms")
        cur.execute("USE university_lms")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            full_name TEXT NOT NULL,
            email TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            roll_number TEXT UNIQUE NOT NULL,
            department TEXT,
            semester INTEGER DEFAULT 1,
            batch_year INTEGER,
            phone TEXT,
            address TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_code TEXT UNIQUE NOT NULL,
            course_name TEXT NOT NULL,
            department TEXT,
            credits INTEGER DEFAULT 3,
            semester INTEGER,
            instructor TEXT,
            description TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS student_courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            course_id INTEGER,
            enrolled_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(student_id) REFERENCES students(id),
            FOREIGN KEY(course_id) REFERENCES courses(id),
            UNIQUE(student_id, course_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS marks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            course_id INTEGER,
            exam_type TEXT NOT NULL,
            marks_obtained REAL DEFAULT 0,
            total_marks REAL DEFAULT 100,
            grade TEXT,
            remarks TEXT,
            exam_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(student_id) REFERENCES students(id),
            FOREIGN KEY(course_id) REFERENCES courses(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            course_id INTEGER,
            date TEXT NOT NULL,
            status TEXT DEFAULT 'present',
            remarks TEXT,
            FOREIGN KEY(student_id) REFERENCES students(id),
            FOREIGN KEY(course_id) REFERENCES courses(id),
            UNIQUE(student_id, course_id, date)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            target_audience TEXT DEFAULT 'all',
            department TEXT,
            posted_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(posted_by) REFERENCES users(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER,
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT,
            total_marks REAL DEFAULT 100,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(course_id) REFERENCES courses(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS timetable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER,
            day_of_week TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            room TEXT,
            department TEXT,
            semester INTEGER,
            FOREIGN KEY(course_id) REFERENCES courses(id)
        )
    """)

    # Seed default admin
    cur.execute("SELECT id FROM users WHERE username='admin'")
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (username, password, role, full_name, email) VALUES (?,?,?,?,?)",
            ('admin', hash_password('admin123'), 'admin', 'System Administrator', 'admin@university.edu')
        )

    conn.commit()
    conn.close()
    print("✅ Database initialised successfully.")


# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    role     = data.get('role', '').strip()

    if not username or not password:
        return jsonify({"success": False, "message": "Username and password required"}), 400

    conn, cur = get_connection()
    cur.execute("SELECT * FROM users WHERE username=? AND role=?", (username, role))
    user = row_to_dict(cur.fetchone())

    if not user or user['password'] != hash_password(password):
        conn.close()
        return jsonify({"success": False, "message": "Invalid credentials"}), 401

    resp = {
        "success": True,
        "user": {
            "id":        user['id'],
            "username":  user['username'],
            "role":      user['role'],
            "full_name": user['full_name'],
            "email":     user['email']
        }
    }

    if role == 'student':
        cur.execute("SELECT * FROM students WHERE user_id=?", (user['id'],))
        student = row_to_dict(cur.fetchone())
        if student:
            resp['user']['student_id']  = student['id']
            resp['user']['roll_number'] = student['roll_number']
            resp['user']['department']  = student['department']
            resp['user']['semester']    = student['semester']

    conn.close()
    return jsonify(resp)


# ─────────────────────────────────────────────
# CHANGE OWN PASSWORD (user changes their own)
# ─────────────────────────────────────────────
@app.route('/api/change-password', methods=['POST'])
def change_password():
    data       = request.json
    user_id    = data.get('user_id')
    current_pw = data.get('current_password', '').strip()
    new_pw     = data.get('new_password', '').strip()
    confirm_pw = data.get('confirm_password', '').strip()

    if not all([user_id, current_pw, new_pw, confirm_pw]):
        return jsonify({"success": False, "message": "All fields are required"}), 400
    if new_pw != confirm_pw:
        return jsonify({"success": False, "message": "New passwords do not match"}), 400
    if len(new_pw) < 6:
        return jsonify({"success": False, "message": "New password must be at least 6 characters"}), 400

    conn, cur = get_connection()
    cur.execute("SELECT password FROM users WHERE id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "message": "User not found"}), 404

    if dict(row)['password'] != hash_password(current_pw):
        conn.close()
        return jsonify({"success": False, "message": "Current password is incorrect"}), 401

    cur.execute("UPDATE users SET password=? WHERE id=?", (hash_password(new_pw), user_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Password changed successfully"})


# ─────────────────────────────────────────────
# ADMIN RESET STUDENT PASSWORD
# Admin authenticates with their own password,
# then sets any student's password directly.
# ─────────────────────────────────────────────
@app.route('/api/admin-reset-password', methods=['POST'])
def admin_reset_password():
    data          = request.json
    admin_user_id = data.get('admin_user_id')
    admin_pw      = data.get('admin_password', '').strip()
    target_id     = data.get('target_user_id')   # student's users.id (we'll accept student_id too)
    new_pw        = data.get('new_password', '').strip()

    if not all([admin_user_id, admin_pw, target_id, new_pw]):
        return jsonify({"success": False, "message": "All fields are required"}), 400
    if len(new_pw) < 6:
        return jsonify({"success": False, "message": "Password must be at least 6 characters"}), 400

    conn, cur = get_connection()

    # 1. Verify admin credentials
    cur.execute("SELECT password, role FROM users WHERE id=?", (admin_user_id,))
    admin = row_to_dict(cur.fetchone())
    if not admin or admin['role'] != 'admin':
        conn.close()
        return jsonify({"success": False, "message": "Unauthorised: not an admin account"}), 403
    if admin['password'] != hash_password(admin_pw):
        conn.close()
        return jsonify({"success": False, "message": "Admin password is incorrect"}), 401

    # 2. Resolve target — target_id may be student.id, so look up the user_id
    cur.execute("SELECT user_id FROM students WHERE id=?", (target_id,))
    student_row = cur.fetchone()
    if student_row:
        real_user_id = dict(student_row)['user_id']
    else:
        # Maybe they passed users.id directly
        cur.execute("SELECT id, role FROM users WHERE id=?", (target_id,))
        u = cur.fetchone()
        if not u:
            conn.close()
            return jsonify({"success": False, "message": "Target student not found"}), 404
        real_user_id = dict(u)['id']

    # 3. Ensure we're not resetting another admin
    cur.execute("SELECT role FROM users WHERE id=?", (real_user_id,))
    target_user = row_to_dict(cur.fetchone())
    if target_user and target_user['role'] == 'admin' and real_user_id != admin_user_id:
        conn.close()
        return jsonify({"success": False, "message": "Cannot reset another admin's password"}), 403

    # 4. Set new password
    cur.execute("UPDATE users SET password=? WHERE id=?", (hash_password(new_pw), real_user_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Student password reset successfully"})


# ─────────────────────────────────────────────
# STUDENTS
# ─────────────────────────────────────────────
@app.route('/api/students', methods=['GET'])
def get_students():
    conn, cur = get_connection()
    cur.execute("""
        SELECT u.id as user_id, u.username, u.full_name, u.email, u.created_at,
               s.id as student_id, s.roll_number, s.department, s.semester,
               s.batch_year, s.phone, s.address
        FROM users u
        LEFT JOIN students s ON u.id = s.user_id
        WHERE u.role = 'student'
        ORDER BY s.roll_number
    """)
    students = rows_to_list(cur.fetchall())
    conn.close()
    return jsonify({"success": True, "students": students})


@app.route('/api/students', methods=['POST'])
def add_student():
    data = request.json
    for field in ['username', 'password', 'full_name', 'roll_number']:
        if not data.get(field):
            return jsonify({"success": False, "message": f"{field} is required"}), 400

    conn, cur = get_connection()
    try:
        cur.execute(
            "INSERT INTO users (username, password, role, full_name, email) VALUES (?,?,'student',?,?)",
            (data['username'], hash_password(data['password']), data['full_name'], data.get('email', ''))
        )
        user_id = cur.lastrowid
        cur.execute(
            "INSERT INTO students (user_id, roll_number, department, semester, batch_year, phone, address) VALUES (?,?,?,?,?,?,?)",
            (user_id, data['roll_number'], data.get('department', ''),
             data.get('semester', 1), data.get('batch_year', datetime.datetime.now().year),
             data.get('phone', ''), data.get('address', ''))
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Student added successfully"})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/students/<int:student_id>', methods=['PUT'])
def update_student(student_id):
    data = request.json
    conn, cur = get_connection()
    try:
        cur.execute(
            "UPDATE students SET department=?, semester=?, batch_year=?, phone=?, address=? WHERE id=?",
            (data.get('department'), data.get('semester'), data.get('batch_year'),
             data.get('phone'), data.get('address'), student_id)
        )
        if data.get('full_name') or data.get('email'):
            cur.execute(
                "UPDATE users SET full_name=COALESCE(?,full_name), email=COALESCE(?,email) WHERE id=(SELECT user_id FROM students WHERE id=?)",
                (data.get('full_name'), data.get('email'), student_id)
            )
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Student updated"})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/students/<int:student_id>', methods=['DELETE'])
def delete_student(student_id):
    conn, cur = get_connection()
    try:
        cur.execute("SELECT user_id FROM students WHERE id=?", (student_id,))
        row = cur.fetchone()
        if row:
            user_id = dict(row)['user_id']
            cur.execute("DELETE FROM marks WHERE student_id=?", (student_id,))
            cur.execute("DELETE FROM attendance WHERE student_id=?", (student_id,))
            cur.execute("DELETE FROM student_courses WHERE student_id=?", (student_id,))
            cur.execute("DELETE FROM students WHERE id=?", (student_id,))
            cur.execute("DELETE FROM users WHERE id=?", (user_id,))
            conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Student deleted"})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "message": str(e)}), 500


# ─────────────────────────────────────────────
# COURSES
# ─────────────────────────────────────────────
@app.route('/api/courses', methods=['GET'])
def get_courses():
    conn, cur = get_connection()
    cur.execute("SELECT * FROM courses ORDER BY course_code")
    courses = rows_to_list(cur.fetchall())
    conn.close()
    return jsonify({"success": True, "courses": courses})


@app.route('/api/courses', methods=['POST'])
def add_course():
    data = request.json
    conn, cur = get_connection()
    try:
        cur.execute(
            "INSERT INTO courses (course_code, course_name, department, credits, semester, instructor, description) VALUES (?,?,?,?,?,?,?)",
            (data['course_code'], data['course_name'], data.get('department', ''),
             data.get('credits', 3), data.get('semester', 1),
             data.get('instructor', ''), data.get('description', ''))
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Course added"})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/courses/<int:course_id>', methods=['DELETE'])
def delete_course(course_id):
    conn, cur = get_connection()
    try:
        for tbl in ['marks', 'attendance', 'student_courses', 'timetable', 'assignments']:
            cur.execute(f"DELETE FROM {tbl} WHERE course_id=?", (course_id,))
        cur.execute("DELETE FROM courses WHERE id=?", (course_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Course deleted"})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/enroll', methods=['POST'])
def enroll_student():
    data = request.json
    conn, cur = get_connection()
    try:
        cur.execute(
            "INSERT OR IGNORE INTO student_courses (student_id, course_id) VALUES (?,?)",
            (data['student_id'], data['course_id'])
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Student enrolled"})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/student/<int:student_id>/courses', methods=['GET'])
def get_student_courses(student_id):
    conn, cur = get_connection()
    cur.execute(
        "SELECT c.* FROM courses c JOIN student_courses sc ON c.id=sc.course_id WHERE sc.student_id=? ORDER BY c.course_code",
        (student_id,)
    )
    courses = rows_to_list(cur.fetchall())
    conn.close()
    return jsonify({"success": True, "courses": courses})


# ─────────────────────────────────────────────
# MARKS
# ─────────────────────────────────────────────
@app.route('/api/marks', methods=['GET'])
def get_marks():
    student_id = request.args.get('student_id')
    course_id  = request.args.get('course_id')
    conn, cur  = get_connection()
    query = """
        SELECT m.*, u.full_name, s.roll_number, c.course_name, c.course_code
        FROM marks m
        JOIN students s ON m.student_id=s.id
        JOIN users u ON s.user_id=u.id
        JOIN courses c ON m.course_id=c.id
        WHERE 1=1
    """
    params = []
    if student_id:
        query += " AND m.student_id=?"; params.append(student_id)
    if course_id:
        query += " AND m.course_id=?";  params.append(course_id)
    query += " ORDER BY m.created_at DESC"
    cur.execute(query, params)
    marks = rows_to_list(cur.fetchall())
    conn.close()
    return jsonify({"success": True, "marks": marks})


@app.route('/api/marks', methods=['POST'])
def add_marks():
    data = request.json
    conn, cur = get_connection()
    try:
        pct = (float(data.get('marks_obtained', 0)) / float(data.get('total_marks', 100))) * 100
        if   pct >= 85: grade = 'A+'
        elif pct >= 75: grade = 'A'
        elif pct >= 65: grade = 'B'
        elif pct >= 55: grade = 'C'
        elif pct >= 45: grade = 'D'
        else:           grade = 'F'

        cur.execute(
            "INSERT INTO marks (student_id, course_id, exam_type, marks_obtained, total_marks, grade, remarks, exam_date) VALUES (?,?,?,?,?,?,?,?)",
            (data['student_id'], data['course_id'], data['exam_type'],
             data.get('marks_obtained', 0), data.get('total_marks', 100),
             grade, data.get('remarks', ''), data.get('exam_date', str(datetime.date.today())))
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Marks added", "grade": grade})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/marks/<int:mark_id>', methods=['DELETE'])
def delete_mark(mark_id):
    conn, cur = get_connection()
    cur.execute("DELETE FROM marks WHERE id=?", (mark_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Mark deleted"})


# ─────────────────────────────────────────────
# ATTENDANCE
# ─────────────────────────────────────────────
@app.route('/api/attendance', methods=['GET'])
def get_attendance():
    student_id = request.args.get('student_id')
    course_id  = request.args.get('course_id')
    conn, cur  = get_connection()
    query = """
        SELECT a.*, u.full_name, s.roll_number, c.course_name, c.course_code
        FROM attendance a
        JOIN students s ON a.student_id=s.id
        JOIN users u ON s.user_id=u.id
        JOIN courses c ON a.course_id=c.id
        WHERE 1=1
    """
    params = []
    if student_id:
        query += " AND a.student_id=?"; params.append(student_id)
    if course_id:
        query += " AND a.course_id=?";  params.append(course_id)
    query += " ORDER BY a.date DESC"
    cur.execute(query, params)
    records = rows_to_list(cur.fetchall())
    conn.close()
    return jsonify({"success": True, "attendance": records})


@app.route('/api/attendance', methods=['POST'])
def mark_attendance():
    data = request.json
    conn, cur = get_connection()
    try:
        records = data.get('records', [])
        for rec in records:
            cur.execute(
                "INSERT OR REPLACE INTO attendance (student_id, course_id, date, status, remarks) VALUES (?,?,?,?,?)",
                (rec['student_id'], rec['course_id'], rec['date'],
                 rec.get('status', 'present'), rec.get('remarks', ''))
            )
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": f"{len(records)} attendance record(s) saved"})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/attendance/summary/<int:student_id>', methods=['GET'])
def attendance_summary(student_id):
    conn, cur = get_connection()
    cur.execute("""
        SELECT c.id as course_id, c.course_name, c.course_code,
               COUNT(*) as total_classes,
               SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END) as present,
               SUM(CASE WHEN a.status='absent'  THEN 1 ELSE 0 END) as absent,
               ROUND(SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END)*100.0/COUNT(*),1) as percentage
        FROM attendance a
        JOIN courses c ON a.course_id=c.id
        WHERE a.student_id=?
        GROUP BY a.course_id
    """, (student_id,))
    summary = rows_to_list(cur.fetchall())
    conn.close()
    return jsonify({"success": True, "summary": summary})


# ─────────────────────────────────────────────
# ANNOUNCEMENTS
# ─────────────────────────────────────────────
@app.route('/api/announcements', methods=['GET'])
def get_announcements():
    conn, cur = get_connection()
    cur.execute("""
        SELECT a.*, u.full_name as posted_by_name
        FROM announcements a
        JOIN users u ON a.posted_by=u.id
        ORDER BY a.created_at DESC
    """)
    items = rows_to_list(cur.fetchall())
    conn.close()
    return jsonify({"success": True, "announcements": items})


@app.route('/api/announcements', methods=['POST'])
def add_announcement():
    data = request.json
    conn, cur = get_connection()
    try:
        cur.execute(
            "INSERT INTO announcements (title, content, target_audience, department, posted_by) VALUES (?,?,?,?,?)",
            (data['title'], data['content'], data.get('target_audience', 'all'),
             data.get('department', ''), data.get('posted_by', 1))
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Announcement posted"})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/announcements/<int:ann_id>', methods=['DELETE'])
def delete_announcement(ann_id):
    conn, cur = get_connection()
    cur.execute("DELETE FROM announcements WHERE id=?", (ann_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Announcement deleted"})


# ─────────────────────────────────────────────
# ASSIGNMENTS
# ─────────────────────────────────────────────
@app.route('/api/assignments', methods=['GET'])
def get_assignments():
    course_id = request.args.get('course_id')
    conn, cur = get_connection()
    query = "SELECT a.*, c.course_name, c.course_code FROM assignments a JOIN courses c ON a.course_id=c.id"
    params = []
    if course_id:
        query += " WHERE a.course_id=?"; params.append(course_id)
    query += " ORDER BY a.due_date ASC"
    cur.execute(query, params)
    items = rows_to_list(cur.fetchall())
    conn.close()
    return jsonify({"success": True, "assignments": items})


@app.route('/api/assignments', methods=['POST'])
def add_assignment():
    data = request.json
    conn, cur = get_connection()
    try:
        cur.execute(
            "INSERT INTO assignments (course_id, title, description, due_date, total_marks) VALUES (?,?,?,?,?)",
            (data['course_id'], data['title'], data.get('description', ''),
             data.get('due_date', ''), data.get('total_marks', 100))
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Assignment added"})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/assignments/<int:assign_id>', methods=['DELETE'])
def delete_assignment(assign_id):
    conn, cur = get_connection()
    cur.execute("DELETE FROM assignments WHERE id=?", (assign_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Assignment deleted"})


# ─────────────────────────────────────────────
# TIMETABLE
# ─────────────────────────────────────────────
@app.route('/api/timetable', methods=['GET'])
def get_timetable():
    dept     = request.args.get('department')
    semester = request.args.get('semester')
    conn, cur = get_connection()
    query = """
        SELECT t.*, c.course_name, c.course_code, c.instructor
        FROM timetable t
        JOIN courses c ON t.course_id=c.id
        WHERE 1=1
    """
    params = []
    if dept:
        query += " AND t.department=?";  params.append(dept)
    if semester:
        query += " AND t.semester=?";    params.append(semester)
    query += """
        ORDER BY CASE t.day_of_week
            WHEN 'Monday'    THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3
            WHEN 'Thursday'  THEN 4 WHEN 'Friday'  THEN 5 WHEN 'Saturday'  THEN 6
        END, t.start_time
    """
    cur.execute(query, params)
    items = rows_to_list(cur.fetchall())
    conn.close()
    return jsonify({"success": True, "timetable": items})


@app.route('/api/timetable', methods=['POST'])
def add_timetable():
    data = request.json
    conn, cur = get_connection()
    try:
        cur.execute(
            "INSERT INTO timetable (course_id, day_of_week, start_time, end_time, room, department, semester) VALUES (?,?,?,?,?,?,?)",
            (data['course_id'], data['day_of_week'], data['start_time'],
             data['end_time'], data.get('room', ''), data.get('department', ''), data.get('semester', 1))
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Timetable entry added"})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/timetable/<int:tt_id>', methods=['DELETE'])
def delete_timetable(tt_id):
    conn, cur = get_connection()
    cur.execute("DELETE FROM timetable WHERE id=?", (tt_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Entry deleted"})


# ─────────────────────────────────────────────
# DASHBOARD STATS
# ─────────────────────────────────────────────
@app.route('/api/dashboard/admin', methods=['GET'])
def admin_dashboard():
    conn, cur = get_connection()

    cur.execute("SELECT COUNT(*) as cnt FROM users WHERE role='student'")
    total_students = dict(cur.fetchone())['cnt']

    cur.execute("SELECT COUNT(*) as cnt FROM courses")
    total_courses = dict(cur.fetchone())['cnt']

    cur.execute("SELECT COUNT(*) as cnt FROM announcements")
    total_announcements = dict(cur.fetchone())['cnt']

    cur.execute("SELECT COUNT(*) as cnt FROM assignments")
    total_assignments = dict(cur.fetchone())['cnt']

    cur.execute("SELECT s.department, COUNT(*) as cnt FROM students s GROUP BY s.department")
    dept_stats = rows_to_list(cur.fetchall())

    cur.execute("""
        SELECT u.full_name, s.roll_number, s.department,
               ROUND(AVG(m.marks_obtained/m.total_marks*100),1) as avg_marks
        FROM marks m
        JOIN students s ON m.student_id=s.id
        JOIN users u ON s.user_id=u.id
        GROUP BY m.student_id
        ORDER BY avg_marks DESC LIMIT 5
    """)
    top_students = rows_to_list(cur.fetchall())

    conn.close()
    return jsonify({
        "success": True,
        "stats": {
            "total_students":      total_students,
            "total_courses":       total_courses,
            "total_announcements": total_announcements,
            "total_assignments":   total_assignments,
            "dept_stats":          dept_stats,
            "top_students":        top_students
        }
    })


@app.route('/api/dashboard/student/<int:student_id>', methods=['GET'])
def student_dashboard(student_id):
    conn, cur = get_connection()

    cur.execute("SELECT COUNT(*) as cnt FROM student_courses WHERE student_id=?", (student_id,))
    enrolled = dict(cur.fetchone())['cnt']

    cur.execute(
        "SELECT ROUND(AVG(marks_obtained/total_marks*100),1) as avg FROM marks WHERE student_id=?",
        (student_id,)
    )
    avg_marks = dict(cur.fetchone())['avg'] or 0

    cur.execute(
        "SELECT ROUND(SUM(CASE WHEN status='present' THEN 1 ELSE 0 END)*100.0/COUNT(*),1) as pct FROM attendance WHERE student_id=?",
        (student_id,)
    )
    att_pct = dict(cur.fetchone())['pct'] or 0

    cur.execute("SELECT COUNT(*) as cnt FROM announcements WHERE target_audience IN ('all','student')")
    ann_cnt = dict(cur.fetchone())['cnt']

    conn.close()
    return jsonify({
        "success": True,
        "stats": {
            "enrolled_courses":      enrolled,
            "average_marks":         avg_marks,
            "attendance_percentage": att_pct,
            "announcements":         ann_cnt
        }
    })


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    print("\n🎓 University LMS Backend")
    print("=" * 42)
    print("🔗 API running at : http://localhost:5000")
    print("👤 Default Admin  : admin / admin123")
    print("🎒 Students       : username & password set by admin")
    print("=" * 42)

    import threading, webbrowser, pathlib, time

    def open_browser():
        time.sleep(1.2)
        html_path = pathlib.Path(__file__).parent / "lms_frontend.html"
        if html_path.exists():
            webbrowser.open(html_path.as_uri())
            print(f"✅ Opened: {html_path}")
        else:
            print(f"⚠️  lms_frontend.html not found at {html_path}")

    threading.Thread(target=open_browser, daemon=True).start()
    app.run(debug=True, port=5000, host='0.0.0.0', use_reloader=False)
