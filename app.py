
"""
StudyHub – Student Helper Web Application
==========================================
Full-stack Flask app with Auth, Notes, Quiz, Updates, Leaderboard, Admin Panel.
Works locally, on Render, AND on Vercel (handles read-only filesystem using /tmp).

Run locally : python app.py
Run on Render: gunicorn app:app
Run on Vercel: zero-config — Vercel detects the `app` Flask instance below.

NOTE: on both Render's free tier and Vercel's serverless functions, /tmp is
NOT permanent storage. Data (signups, uploaded notes, quiz scores) can reset
whenever the instance restarts or a new serverless invocation spins up. This
is fine for a class demo but not for real user data — swap in a real database
(e.g. Postgres/Supabase) if you need data to persist reliably.
"""

from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, send_from_directory)
from functools import wraps
from datetime import datetime
from werkzeug.utils import secure_filename
import json, os, hashlib, uuid

# ─────────────────────────────────────────────────────────────
#  App Setup
# ─────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = "studyhub_2024_render_secret_xK9pL2"

# ─────────────────────────────────────────────────────────────
#  Config  –  /tmp on Render, local folders otherwise
# ─────────────────────────────────────────────────────────────
IS_RENDER      = bool(os.environ.get("RENDER"))          # Render sets this automatically
IS_VERCEL      = bool(os.environ.get("VERCEL"))           # Vercel sets this automatically
IS_SERVERLESS  = IS_RENDER or IS_VERCEL
DATA_DIR      = "/tmp/studyhub/data"    if IS_SERVERLESS else "data"
UPLOAD_FOLDER = "/tmp/studyhub/uploads" if IS_SERVERLESS else os.path.join("static", "notes")

ALLOWED_EXTENSIONS              = {"pdf"}
app.config["UPLOAD_FOLDER"]     = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024   # 16 MB

# Create required directories at startup (safe on all platforms)
os.makedirs(DATA_DIR,      exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.route("/notes/file/<filename>")
def note_file(filename):
    notes_folder = os.path.join(app.root_path, "static", "notes")
    return send_from_directory(notes_folder, filename)
# ─────────────────────────────────────────────────────────────
#  Helper Functions
# ─────────────────────────────────────────────────────────────
def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def load_json(filename: str):
    """Load a JSON file from DATA_DIR. Returns [] if missing."""
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_json(filename: str, data) -> bool:
    """Save data as JSON to DATA_DIR. Returns True on success."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(os.path.join(DATA_DIR, filename), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[ERROR] save_json({filename}): {e}")
        return False

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def favorite_key_for(note_id: str, filename: str = "", note_name: str = "", chapter_name: str = "") -> str:
    if filename:
        return f"{str(note_id)}|{str(filename)}"
    if note_name:
        return f"{str(note_id)}|{str(note_name)}"
    return f"{str(note_id)}|{str(chapter_name or 'note')}"


def current_user_record():
    user_id = session.get("user_id")
    if not user_id:
        return None
    for user in load_json("users.json"):
        if str(user.get("id")) == str(user_id):
            user.setdefault("favorites", [])
            return user
    return None


def favorite_keys_for_user():
    user = current_user_record()
    favorites = user.get("favorites", []) if user else []
    return {str(item.get("key", "")) for item in favorites if isinstance(item, dict)}


def save_current_user_favorites(favorites):
    user_id = session.get("user_id")
    if not user_id:
        return False
    users = load_json("users.json")
    changed = False
    for user in users:
        if str(user.get("id")) == str(user_id):
            user["favorites"] = favorites
            changed = True
            break
    if changed:
        return save_json("users.json", users)
    return False


def note_matches_search(note: dict, query: str) -> bool:
    """Case-insensitive match against subject, title, description and file metadata."""
    if not query:
        return True
    query = query.lower().strip()
    if not query:
        return True

    haystacks = [
        note.get("subject", ""),
        note.get("title", ""),
        note.get("description", ""),
        note.get("filename", ""),
    ]
    for file_data in note.get("files", []) or []:
        haystacks.extend([
            file_data.get("label", ""),
            file_data.get("filename", ""),
        ])

    return any(query in str(value).lower() for value in haystacks if value is not None)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Admin access required.", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────────────────────
#  Seed Default Data  (called at every startup)
# ─────────────────────────────────────────────────────────────
def seed_data():
    """Write default data files if they don't exist yet."""

    # ── Users ──────────────────────────────────────────────
    if not os.path.exists(os.path.join(DATA_DIR, "users.json")):
        save_json("users.json", [
            {"id": str(uuid.uuid4()), "name": "Admin User",
             "email": "admin@school.com",
             "password": hash_password("admin123"),
             "is_admin": True,  "score": 0},
            {"id": str(uuid.uuid4()), "name": "John Student",
             "email": "john@school.com",
             "password": hash_password("student123"),
             "is_admin": False, "score": 85},
            {"id": str(uuid.uuid4()), "name": "Alice Smith",
             "email": "alice@school.com",
             "password": hash_password("alice123"),
             "is_admin": False, "score": 92},
        ])

    # ── Notes ───────────────────────────────────────────────
    if not os.path.exists(os.path.join(DATA_DIR, "notes.json")):
        save_json("notes.json", [
            {"id": "1", "subject": "Mathematics",
             "title": "Calculus – Differentiation & Integration",
             "description": "Limits, derivatives, integrals and their applications.",
             "filename": None, "icon": "📐", "color": "#4361ee"},
            {"id": "2", "subject": "Physics",
             "title": "Mechanics – Newton's Laws",
             "description": "Motion, forces, energy and momentum.",
             "filename": None, "icon": "⚛️", "color": "#7209b7"},
            {"id": "3", "subject": "Chemistry",
             "title": "Organic Chemistry Basics",
             "description": "Hydrocarbons, functional groups and reactions.",
             "filename": None, "icon": "🧪", "color": "#f72585"},
            {"id": "4", "subject": "Computer Science",
             "title": "Data Structures & Algorithms",
             "description": "Arrays, linked lists, trees, sorting and searching.",
             "filename": None, "icon": "💻", "color": "#4cc9f0"},
            {"id": "5", "subject": "Biology",
             "title": "Cell Biology & Genetics",
             "description": "Cell structure, DNA replication, genetics.",
             "filename": None, "icon": "🧬", "color": "#06d6a0"},
            {"id": "6", "subject": "Information Security",
             "title": "Cyber Security – Unit 5",
             "description": "Cyber threats, attacks, vulnerabilities and cybercrime.",
             "filename": None, "icon": "🔐", "color": "#fb8500"},
        ])

    # ── Quiz ────────────────────────────────────────────────
    if not os.path.exists(os.path.join(DATA_DIR, "quiz.json")):
        save_json("quiz.json", [
            {"id": 1,  "subject": "Mathematics",
             "question": "What is the derivative of sin(x)?",
             "options": ["cos(x)", "-cos(x)", "tan(x)", "-sin(x)"], "answer": 0},
            {"id": 2,  "subject": "Science",
             "question": "Which planet is known as the Red Planet?",
             "options": ["Venus", "Mars", "Jupiter", "Saturn"],      "answer": 1},
            {"id": 3,  "subject": "Computer Science",
             "question": "What does CPU stand for?",
             "options": ["Central Process Unit", "Central Processing Unit",
                         "Computer Personal Unit", "Control Processing Unit"], "answer": 1},
            {"id": 4,  "subject": "Chemistry",
             "question": "What is the chemical symbol for Gold?",
             "options": ["Go", "Gd", "Au", "Ag"],                   "answer": 2},
            {"id": 5,  "subject": "Biology",
             "question": "What is the powerhouse of the cell?",
             "options": ["Nucleus", "Ribosome", "Mitochondria", "Golgi Apparatus"], "answer": 2},
            {"id": 6,  "subject": "English",
             "question": "Who wrote 'Romeo and Juliet'?",
             "options": ["Charles Dickens", "Mark Twain",
                         "William Shakespeare", "Jane Austen"], "answer": 2},
            {"id": 7,  "subject": "Physics",
             "question": "What is Newton's Second Law of Motion?",
             "options": ["F = mv", "F = ma", "F = m/a", "F = a/m"], "answer": 1},
            {"id": 8,  "subject": "Mathematics",
             "question": "What is the value of π to 2 decimal places?",
             "options": ["3.12", "3.41", "3.14", "3.16"],           "answer": 2},
            {"id": 9,  "subject": "Computer Science",
             "question": "Which data structure uses LIFO order?",
             "options": ["Queue", "Array", "Stack", "Linked List"],  "answer": 2},
            {"id": 10, "subject": "Cyber Security",
             "question": "Which attack sends fake emails to steal credentials?",
             "options": ["Ransomware", "Phishing", "DoS", "Worm"],  "answer": 1},
        ])

    # ── Updates ─────────────────────────────────────────────
    if not os.path.exists(os.path.join(DATA_DIR, "updates.json")):
        save_json("updates.json", [
            {"id": "1", "title": "🎉 Mid-Term Exams Schedule Released",
             "content": "Mid-term examinations will be held from November 18–25.",
             "date": "2024-11-01", "tag": "Exam",        "tag_color": "#f72585"},
            {"id": "2", "title": "📚 New Study Materials Added",
             "content": "Updated notes for Mathematics and Physics uploaded. Check Notes section.",
             "date": "2024-10-28", "tag": "Resources",   "tag_color": "#4361ee"},
            {"id": "3", "title": "🏆 Quiz Competition Results",
             "content": "Congratulations! Top scorers will receive certificates next Monday.",
             "date": "2024-10-25", "tag": "Achievement", "tag_color": "#06d6a0"},
            {"id": "4", "title": "🎓 Guest Lecture on AI & Careers",
             "content": "Special session on AI and career opportunities – Nov 10.",
             "date": "2024-10-22", "tag": "Event",       "tag_color": "#fb8500"},
            {"id": "5", "title": "📝 Assignment Submission Reminder",
             "content": "All pending assignments must be submitted by November 5.",
             "date": "2024-10-20", "tag": "Reminder",    "tag_color": "#7209b7"},
        ])

    # Assignments
    if not os.path.exists(os.path.join(DATA_DIR, "assignments.json")):
        save_json("assignments.json", [
            {"id": "1", "subject": "Mathematics", "title": "Calculus Practice Set",
             "description": "Complete questions 1–15 from the differentiation worksheet.",
             "due_date": "2026-08-20", "color": "#4361ee"},
            {"id": "2", "subject": "Information Security", "title": "Cryptography Report",
             "description": "Write a short report on symmetric encryption techniques.",
             "due_date": "2026-08-23", "color": "#fb8500"},
        ])

# Run seed at module load (works with gunicorn workers too)
seed_data()


# ─────────────────────────────────────────────────────────────
#  Auth Routes
# ─────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return redirect(url_for("dashboard") if "user" in session else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        users    = load_json("users.json")
        user     = next((u for u in users
                         if u["email"] == email
                         and u["password"] == hash_password(password)), None)
        if user:
            session["user"]     = user["name"]
            session["user_id"]  = user["id"]
            session["is_admin"] = user.get("is_admin", False)
            flash(f"Welcome back, {user['name']}! 👋", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid email or password. Please try again.", "danger")
    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name    = request.form.get("name", "").strip()
        email   = request.form.get("email", "").strip().lower()
        pwd     = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not all([name, email, pwd]):
            flash("All fields are required.", "danger")
            return render_template("signup.html")
        if pwd != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("signup.html")
        if len(pwd) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return render_template("signup.html")

        users = load_json("users.json")
        if any(u["email"] == email for u in users):
            flash("Email already registered. Please log in.", "warning")
            return redirect(url_for("login"))

        new_user = {"id": str(uuid.uuid4()), "name": name, "email": email,
                    "password": hash_password(pwd), "is_admin": False, "score": 0}
        users.append(new_user)
        save_json("users.json", users)

        session["user"]     = name
        session["user_id"]  = new_user["id"]
        session["is_admin"] = False
        flash(f"Account created! Welcome, {name}! 🎉", "success")
        return redirect(url_for("dashboard"))
    return render_template("signup.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully. See you soon! 👋", "info")
    return redirect(url_for("login"))


# ─────────────────────────────────────────────────────────────
#  Main Pages
# ─────────────────────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    updates     = load_json("updates.json")[:3]
    notes_count = len(load_json("notes.json"))
    quiz_count  = len(load_json("quiz.json"))
    assignments_count = len(load_json("assignments.json"))
    return render_template("dashboard.html",
                           updates=updates,
                           notes_count=notes_count,
                           quiz_count=quiz_count,
                           assignments_count=assignments_count)


@app.route("/notes")
@login_required
def notes():
    all_notes      = load_json("notes.json")
    search         = request.args.get("search", "").strip()
    subject_filter = request.args.get("subject", "").strip()

    if search:
        all_notes = [n for n in all_notes if note_matches_search(n, search)]
    if subject_filter:
        all_notes = [n for n in all_notes if n["subject"] == subject_filter]

    subjects = sorted({n["subject"] for n in load_json("notes.json")})
    return render_template("notes.html",
                           notes=all_notes,
                           subjects=subjects,
                           search=search,
                           subject_filter=subject_filter,
                           favorite_keys=favorite_keys_for_user())


@app.route("/notes/subject/<subject_name>")
@login_required
def subject_page(subject_name):
    all_notes = load_json("notes.json")
    # Match subject case-insensitively
    matched = [n for n in all_notes if n.get("subject", "").lower() == subject_name.lower()]
    if not matched:
        flash(f"No notes found for subject: {subject_name}", "warning")
        return redirect(url_for("notes"))
    # Pass the matched entries (may contain multiple note groups/files)
    return render_template("subject.html", subject=subject_name, notes=matched,
                           favorite_keys=favorite_keys_for_user())


@app.route("/favorites", methods=["GET"])
@login_required
def favorites_page():
    user = current_user_record()
    favorites = user.get("favorites", []) if user else []
    return render_template("favorites.html", favorites=favorites)


@app.route("/favorites/toggle", methods=["POST"])
@login_required
def toggle_favorite():
    user = current_user_record()
    if not user:
        flash("Please log in to manage favorites.", "warning")
        return redirect(url_for("login"))

    favorite_key = (request.form.get("favorite_key") or request.form.get("item_key") or "").strip()
    if not favorite_key:
        note_id = request.form.get("note_id", "")
        subject = request.form.get("subject", "")
        chapter_name = request.form.get("chapter_name", "")
        note_name = request.form.get("note_name", "")
        filename = request.form.get("filename", "")
        favorite_key = favorite_key_for(note_id, filename=filename, note_name=note_name, chapter_name=chapter_name)

    favorites = user.get("favorites", [])
    existing_index = next((idx for idx, item in enumerate(favorites) if item.get("key") == favorite_key), None)

    if existing_index is not None:
        del favorites[existing_index]
        save_current_user_favorites(favorites)
        flash("Removed from favorites.", "info")
    else:
        favorite_item = {
            "key": favorite_key,
            "note_id": request.form.get("note_id", ""),
            "subject": request.form.get("subject", ""),
            "chapter_name": request.form.get("chapter_name", ""),
            "note_name": request.form.get("note_name", ""),
            "filename": request.form.get("filename", ""),
            "file_label": request.form.get("file_label", ""),
            "preview_url": request.form.get("preview_url", ""),
            "download_url": request.form.get("download_url", ""),
            "view_url": request.form.get("view_url", "")
        }
        favorites.append(favorite_item)
        save_current_user_favorites(favorites)
        flash("Added to favorites.", "success")

    next_url = request.form.get("next") or request.referrer or url_for("notes")
    return redirect(next_url)


# Fallback alias for CHASM subject to avoid 404 if dynamic route has issues
@app.route("/notes/subject/CHASM")
@login_required
def subject_chasm():
    return subject_page('CHASM')


# Debug helper: list all registered routes (safe for local testing)
@app.route('/_routes')
def _routes():
    lines = []
    for r in sorted(app.url_map.iter_rules(), key=lambda x: x.rule):
        lines.append(f"{r.rule} -> {r.endpoint}")
    return '<pre>' + '\n'.join(lines) + '</pre>'


@app.route("/notes/download/<note_id>")
@login_required
def download_note(note_id):
    all_notes = load_json("notes.json")
    note = next((n for n in all_notes if n["id"] == note_id), None)
    if note and note.get("filename"):
        return send_from_directory(
            app.config["UPLOAD_FOLDER"],
            note["filename"],
            as_attachment=True
        )
    flash("File not available for download yet.", "warning")
    return redirect(url_for("notes"))


@app.route("/notes/download/<note_id>/<int:file_index>")
@login_required
def download_note_file(note_id, file_index):
    note = next((n for n in load_json("notes.json") if n["id"] == note_id), None)
    files = note.get("files", []) if note else []
    if 0 <= file_index < len(files):
        return send_from_directory(app.config["UPLOAD_FOLDER"],
                                   files[file_index]["filename"],
                                   as_attachment=True)
    flash("File not available for download yet.", "warning")
    return redirect(url_for("notes"))


@app.route("/quiz", methods=["GET", "POST"])
@login_required
def quiz():
    questions = load_json("quiz.json")
    if request.method == "POST":
        score, results = 0, []
        for q in questions:
            raw = request.form.get(f"q{q['id']}")
            if raw is None:
                continue
            selected = int(raw)
            correct  = (q["answer"] == selected)
            if correct:
                score += 1
            results.append({
                "question":      q["question"],
                "options":       q["options"],
                "selected":      selected,
                "correct_index": q["answer"],
                "is_correct":    correct,
                "subject":       q["subject"],
            })

        total      = len(questions)
        percentage = round(score / total * 100) if total else 0

        # Save best score
        users = load_json("users.json")
        for u in users:
            if u["id"] == session.get("user_id"):
                if score > u.get("score", 0):
                    u["score"] = score
        save_json("users.json", users)

        return render_template("quiz_result.html",
                               score=score, total=total,
                               percentage=percentage, results=results)
    return render_template("quiz.html", questions=questions)


@app.route("/updates")
@login_required
def updates():
    return render_template("updates.html", updates=load_json("updates.json"))


@app.route("/assignments")
@login_required
def assignments():
    all_assignments = load_json("assignments.json")
    subject_filter = request.args.get("subject", "").strip()
    if subject_filter:
        all_assignments = [a for a in all_assignments if a["subject"] == subject_filter]
    subjects = sorted({a["subject"] for a in load_json("assignments.json")})
    return render_template("assignments.html", assignments=all_assignments,
                           subjects=subjects, subject_filter=subject_filter)


@app.route("/leaderboard")
@login_required
def leaderboard():
    ranked = sorted(load_json("users.json"),
                    key=lambda u: u.get("score", 0), reverse=True)
    return render_template("leaderboard.html",
                           users=ranked,
                           current_user_id=session.get("user_id"))


# ─────────────────────────────────────────────────────────────
#  Admin Panel
# ─────────────────────────────────────────────────────────────
@app.route("/admin")
@login_required
@admin_required
def admin():
    return render_template("admin.html",
                           users=load_json("users.json"),
                           notes=load_json("notes.json"),
                           updates=load_json("updates.json"),
                           assignments=load_json("assignments.json"))


@app.route("/admin/upload_note", methods=["POST"])
@login_required
@admin_required
def upload_note():
    subject     = request.form.get("subject", "").strip()
    title       = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    icon        = request.form.get("icon", "📄").strip()
    color       = request.form.get("color", "#4361ee").strip()
    file        = request.files.get("file")

    if not subject or not title:
        flash("Subject and title are required.", "danger")
        return redirect(url_for("admin"))

    filename = None
    if file and file.filename and allowed_file(file.filename):
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    notes_list = load_json("notes.json")
    notes_list.append({
        "id": str(uuid.uuid4()), "subject": subject, "title": title,
        "description": description, "filename": filename,
        "icon": icon, "color": color,
    })
    save_json("notes.json", notes_list)
    flash("Note uploaded successfully! ✅", "success")
    return redirect(url_for("admin"))


@app.route("/admin/delete_note/<note_id>", methods=["POST"])
@login_required
@admin_required
def delete_note(note_id):
    notes_list = load_json("notes.json")
    note = next((n for n in notes_list if n["id"] == note_id), None)
    if note and note.get("filename"):
        fp = os.path.join(app.config["UPLOAD_FOLDER"], note["filename"])
        if os.path.exists(fp):
            os.remove(fp)
    save_json("notes.json", [n for n in notes_list if n["id"] != note_id])
    flash("Note deleted.", "info")
    return redirect(url_for("admin"))


@app.route("/admin/add_update", methods=["POST"])
@login_required
@admin_required
def add_update():
    title     = request.form.get("title", "").strip()
    content   = request.form.get("content", "").strip()
    tag       = request.form.get("tag", "General").strip()
    tag_color = request.form.get("tag_color", "#4361ee").strip()

    if not title or not content:
        flash("Title and content are required.", "danger")
        return redirect(url_for("admin"))

    updates_list = load_json("updates.json")
    updates_list.insert(0, {
        "id": str(uuid.uuid4()), "title": title, "content": content,
        "tag": tag, "tag_color": tag_color,
        "date": datetime.now().strftime("%Y-%m-%d"),
    })
    save_json("updates.json", updates_list)
    flash("Announcement posted! 📢", "success")
    return redirect(url_for("admin"))


@app.route("/admin/delete_update/<update_id>", methods=["POST"])
@login_required
@admin_required
def delete_update(update_id):
    save_json("updates.json",
              [u for u in load_json("updates.json") if u["id"] != update_id])
    flash("Announcement deleted.", "info")
    return redirect(url_for("admin"))


@app.route("/admin/add_assignment", methods=["POST"])
@login_required
@admin_required
def add_assignment():
    subject = request.form.get("subject", "").strip()
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    due_date = request.form.get("due_date", "").strip()
    color = request.form.get("color", "#4361ee").strip()
    if not all([subject, title, description, due_date]):
        flash("Subject, title, description and due date are required.", "danger")
        return redirect(url_for("admin"))
    assignment_list = load_json("assignments.json")
    assignment_list.insert(0, {"id": str(uuid.uuid4()), "subject": subject,
                                "title": title, "description": description,
                                "due_date": due_date, "color": color})
    save_json("assignments.json", assignment_list)
    flash("Assignment posted successfully!", "success")
    return redirect(url_for("admin"))


@app.route("/admin/delete_assignment/<assignment_id>", methods=["POST"])
@login_required
@admin_required
def delete_assignment(assignment_id):
    save_json("assignments.json", [a for a in load_json("assignments.json")
                                   if a["id"] != assignment_id])
    flash("Assignment deleted.", "info")
    return redirect(url_for("admin"))


# ─────────────────────────────────────────────────────────────
#  Run
# ─────────────────────────────────────────────────────────────
@app.route("/notes/view/<note_id>")
@login_required
def view_note(note_id):
    all_notes = load_json("notes.json")
    note = next((n for n in all_notes if n["id"] == note_id), None)

    if note and note.get("filename"):
        return send_from_directory(
            app.config["UPLOAD_FOLDER"],
            note["filename"],
            as_attachment=False
        )

    flash("File not available for viewing yet.", "warning")
    return redirect(url_for("notes"))


@app.route("/notes/view/<note_id>/<int:file_index>")
@login_required
def view_note_file(note_id, file_index):
    note = next((n for n in load_json("notes.json") if n["id"] == note_id), None)
    files = note.get("files", []) if note else []
    if 0 <= file_index < len(files):
        return send_from_directory(app.config["UPLOAD_FOLDER"],
                                   files[file_index]["filename"],
                                   as_attachment=False)
    flash("File not available for viewing yet.", "warning")
    return redirect(url_for("notes"))


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
