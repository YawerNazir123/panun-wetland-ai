import os
import sys
import base64
import sqlite3
from io import BytesIO
from unittest import result
from PIL import Image
from flask import session
from werkzeug.utils import secure_filename


from flask import Flask, render_template, request, redirect, url_for
from functools import wraps
from flask import session, redirect, url_for




# --------------------------------------------------
# PATH SETUP
# --------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
sys.path.append(ROOT_DIR)

UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DB_PATH = os.path.join(BASE_DIR, "data", "species.db")

# --------------------------------------------------
# AI MODEL IMPORT
# --------------------------------------------------
from ai.ai_utils import predict_image

def normalize_name(name: str):
    return name.lower().replace("_", " ").strip()


# --------------------------------------------------
# FLASK APP
# --------------------------------------------------
app = Flask(__name__)
app.config["ENV"] = "production"
app.config["DEBUG"] = False
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

app.secret_key = "panun_wetland_secret_key_v1"

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper


# --------------------------------------------------
# DATABASE HELPERS
# --------------------------------------------------
def get_species(query=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    if query:
        c.execute("""
            SELECT * FROM species
            WHERE lower(common_name) LIKE ?
               OR lower(scientific_name) LIKE ?
        """, (f"%{query.lower()}%", f"%{query.lower()}%"))
    else:
        c.execute("SELECT * FROM species")

    rows = c.fetchall()
    conn.close()
    return rows


def save_pending_observation(species, confidence, image_path):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        INSERT INTO pending_observations
        (predicted_name, confidence, image_path)
        VALUES (?, ?, ?)
    """, (species, confidence, image_path))

    conn.commit()
    conn.close()


# --------------------------------------------------
# ROUTES
# --------------------------------------------------
@app.route("/")
def home():
    return render_template("home.html")

def species_exists(scientific_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT 1 FROM species
        WHERE LOWER(REPLACE(scientific_name, '_', ' ')) = ?
    """, (scientific_name.lower().strip(),))

    exists = c.fetchone() is not None
    conn.close()
    return exists



@app.route("/identify", methods=["GET", "POST"])
def identify():
    if request.method == "POST":

        # -------- SAVE IMAGE --------
        file = request.files.get("image")
        if not file or file.filename == "":
            return redirect(url_for("identify"))

        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        image_url = "uploads/" + filename

        # -------- AI PREDICTION --------
        result = predict_image(filepath)

        confidence = result["confidence"]
        predicted_scientific = normalize_name(result["scientific"])

        # -------- DATABASE CHECK --------
        in_database = species_exists(predicted_scientific)

        # -------- USER-FACING MESSAGE (NO % SHOWN) --------
        if confidence >= 32:
            user_message = (
                "Confirmed identification – this species has been previously documented as a migratory bird of the Chatlam Wetland."
            )

        elif confidence >= 22:
            user_message = (
              "Probable identification – this bird closely resembles a known migratory species and is currently under expert verification."
            )

        else:
            user_message = (
               "Based on our analysis, this observation may represent a new or rare migratory bird not included among the 103 species currently recorded from the Chatlam Wetland."
            )

        # -------- FINAL DECISION (YOUR ORIGINAL STATUS LOGIC) --------
        if in_database and confidence >= 32:
            status = "Confirmed Migratory Bird"

        elif confidence >= 22:
            status = "Likely Migratory Species (Under Expert Verification)"

        else:
            status = "Potential New / Rare Visitor"
            save_pending_observation(
                result["species"],
                confidence,
                image_url
            )

        return render_template(
            "result.html",
            result={
                "species": result["species"],
                "status": status,
                "message": user_message
            },
            image_path=image_url
        )

    return render_template("identify.html")

@app.route("/about")
def about():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # total species recorded
    c.execute("SELECT COUNT(*) FROM species")
    total_species = c.fetchone()[0]

    conn.close()

    return render_template(
        "about.html",
        total_species=total_species,
        trained_species=50  # change if needed
    )



@app.route("/species")
def species():
    status = request.args.get("status")
    season = request.args.get("season")
    search = request.args.get("q")


    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    query = "SELECT * FROM species WHERE 1=1"
    params = []

    if status:
        query += " AND status LIKE ?"
        params.append(f"%{status}%")

    if season:
        query += " AND season = ?"
        params.append(season)
    if search:
        query += " AND (common_name LIKE ? OR scientific_name LIKE ?)"
        params.append(f"%{search}%")
        params.append(f"%{search}%")


    c.execute(query, params)
    species_list = c.fetchall()
    conn.close()

    return render_template(
    "species.html",
    species=species_list,
    status=status,
    season=season,
    query=search
)




@app.route("/species/<int:species_id>")
def species_detail(species_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM species WHERE id = ?", (species_id,))
    bird = c.fetchone()
    conn.close()

    if not bird:
        return "Species not found", 404

    return render_template("species_detail.html", bird=bird)

@app.route("/admin/login", methods=["GET", "POST"])

def admin_login():
    error = None

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT * FROM admins
            WHERE username=? AND password=?
        """, (username, password))
        admin = c.fetchone()
        conn.close()

        if admin:
            session.clear()
            session["admin_logged_in"] = True
            return redirect("/admin/review")
        else:
            error = "Invalid credentials"

    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
@admin_required
def admin_logout():
    session.clear()   # IMPORTANT: clears everything
    return redirect("/")

@app.route("/admin/species")
@admin_required
def admin_species():
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM species ORDER BY common_name")
    species = c.fetchall()
    conn.close()

    return render_template("admin_species.html", species=species)


@app.route("/admin/species/edit/<int:species_id>", methods=["GET", "POST"])
@admin_required
def edit_species(species_id):
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    if request.method == "POST":
        c.execute("""
            UPDATE species
            SET common_name = ?, scientific_name = ?, status = ?, season = ?, image = ?
            WHERE id = ?
        """, (
            request.form["common_name"],
            request.form["scientific_name"],
            request.form["status"],
            request.form["season"],
            request.form["image"],
            species_id
        ))
        conn.commit()
        conn.close()
        return redirect("/admin/species")

    c.execute("SELECT * FROM species WHERE id = ?", (species_id,))
    bird = c.fetchone()
    conn.close()

    return render_template("admin_edit_species.html", bird=bird)

@app.route("/admin/review")
@admin_required
def admin_review():
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM pending_observations ORDER BY id DESC")

    pending = c.fetchall()

    conn.close()

    return render_template("admin_review.html", pending=pending)



@app.route("/admin/approve/<int:pid>", methods=["POST"])
@admin_required
def approve_species(pid):

    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    common = request.form["common_name"]
    scientific = request.form["scientific_name"]
    status = request.form["status"]
    season = request.form["season"]

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Get pending record
    c.execute("SELECT image_path FROM pending_observations WHERE id=?", (pid,))
    image_path = c.fetchone()[0]

    # Insert into species
    c.execute("""
        INSERT INTO species (common_name, scientific_name, status, season, image)
        VALUES (?, ?, ?, ?, ?)
    """, (common, scientific, status, season, image_path))

    # Remove from pending
    c.execute("DELETE FROM pending_observations WHERE id=?", (pid,))

    conn.commit()
    conn.close()

    return redirect("/admin/review")


@app.route("/admin/reject/<int:obs_id>", methods=["POST"])
def reject_observation(obs_id):
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM pending_observations WHERE id = ?", (obs_id,))
    conn.commit()
    conn.close()

    return redirect("/admin/review")

@app.route("/admin/species/delete/<int:species_id>", methods=["POST"])
def delete_species(species_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("DELETE FROM species WHERE id = ?", (species_id,))
    conn.commit()
    conn.close()

    return redirect(url_for("admin_species"))





# --------------------------------------------------
# RUN SERVER
# --------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
