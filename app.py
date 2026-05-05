import json
import os
from functools import wraps
from flask import Flask, render_template, request, session, redirect, url_for, jsonify, flash

app = Flask(__name__)
app.secret_key = "mathly_secret_2024_xK9p"

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_lectie(lectie_id):
    lectii = load_json("lectii.json")
    return next((l for l in lectii if l["id"] == lectie_id), None)


def get_progres_user(username):
    progres = load_json("progres.json")
    return progres.get(username, {})


def save_progres_user(username, user_progres):
    progres = load_json("progres.json")
    progres[username] = user_progres
    save_json("progres.json", progres)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        users = load_json("users.json")
        if users.get(session["username"], {}).get("rol") != "admin":
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated


def get_lectie_status(lectie, user_progres):
    lid = lectie["id"]
    if lid not in user_progres:
        return "neînceput"
    lp = user_progres[lid]
    if lp.get("testFinal", {}).get("completat"):
        return "complet"
    return "în progres"


# ─── LANDING ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if "username" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


# ─── AUTH ────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        parola = request.form.get("parola", "").strip()
        users = load_json("users.json")
        user = users.get(username)
        if user and user["parola"] == parola:
            session["username"] = username
            session["rol"] = user["rol"]
            session["nume"] = user["nume"]
            if user["rol"] == "admin":
                return redirect(url_for("admin_index"))
            return redirect(url_for("dashboard"))
        flash("Utilizator sau parolă incorectă.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ─── DASHBOARD ───────────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    lectii = load_json("lectii.json")
    user_progres = get_progres_user(session["username"])

    module = {}
    for l in lectii:
        modul = l["modul"]
        if modul not in module:
            module[modul] = []
        status = get_lectie_status(l, user_progres)
        lp = user_progres.get(l["id"], {})
        scor = lp.get("testFinal", {}).get("scor")
        module[modul].append({
            "id": l["id"],
            "titlu": l["titlu"],
            "descriere": l["descriere"],
            "status": status,
            "scor": scor,
            "num_pasi": len(l["pasi"]),
        })

    total = len(lectii)
    complete = sum(1 for l in lectii if get_lectie_status(l, user_progres) == "complet")
    in_progres = sum(1 for l in lectii if get_lectie_status(l, user_progres) == "în progres")

    return render_template("dashboard.html",
                           module=module,
                           total=total,
                           complete=complete,
                           in_progres=in_progres)


# ─── LECȚIE ──────────────────────────────────────────────────────────────────

@app.route("/lectie/<lectie_id>")
@login_required
def lectie(lectie_id):
    l = get_lectie(lectie_id)
    if not l:
        return redirect(url_for("dashboard"))

    user_progres = get_progres_user(session["username"])
    lp = user_progres.get(lectie_id, {})

    # Dacă testul e completat, redirectăm la rezultate
    if lp.get("testFinal", {}).get("completat"):
        return redirect(url_for("test_rezultat", lectie_id=lectie_id))

    # Găsim primul pas necomplet
    pasi = l["pasi"]
    pas_curent_idx = 0
    for i, pas in enumerate(pasi):
        if lp.get(pas["id"]):
            pas_curent_idx = i + 1
        else:
            pas_curent_idx = i
            break
    else:
        # Toate pasii completați
        pas_curent_idx = len(pasi)

    if pas_curent_idx >= len(pasi):
        # Toate pasii OK → test final
        return redirect(url_for("test_final", lectie_id=lectie_id))

    pas = pasi[pas_curent_idx]
    eroare = session.pop(f"eroare_{lectie_id}_{pas['id']}", None)

    return render_template("lectie.html",
                           lectie=l,
                           pas=pas,
                           pas_idx=pas_curent_idx,
                           total_pasi=len(pasi),
                           eroare=eroare)


@app.route("/lectie/<lectie_id>/pas/<pas_id>", methods=["POST"])
@login_required
def submit_pas(lectie_id, pas_id):
    l = get_lectie(lectie_id)
    if not l:
        return redirect(url_for("dashboard"))

    pas = next((p for p in l["pasi"] if p["id"] == pas_id), None)
    if not pas:
        return redirect(url_for("lectie", lectie_id=lectie_id))

    raspuns = request.form.get("raspuns", "").strip()

    if raspuns == pas["raspuns_corect"]:
        user_progres = get_progres_user(session["username"])
        if lectie_id not in user_progres:
            user_progres[lectie_id] = {}
        if "testFinal" not in user_progres[lectie_id]:
            user_progres[lectie_id]["testFinal"] = {"completat": False, "scor": None}
        user_progres[lectie_id][pas_id] = True
        save_progres_user(session["username"], user_progres)
    else:
        session[f"eroare_{lectie_id}_{pas_id}"] = pas.get("explicatie_gresit", "Răspuns incorect. Încearcă din nou.")

    return redirect(url_for("lectie", lectie_id=lectie_id))


# ─── TEST FINAL ──────────────────────────────────────────────────────────────

@app.route("/lectie/<lectie_id>/test")
@login_required
def test_final(lectie_id):
    l = get_lectie(lectie_id)
    if not l:
        return redirect(url_for("dashboard"))

    user_progres = get_progres_user(session["username"])
    lp = user_progres.get(lectie_id, {})

    # Verifică dacă toate pasii sunt completați
    pasi_ok = all(lp.get(p["id"]) for p in l["pasi"])
    if not pasi_ok:
        return redirect(url_for("lectie", lectie_id=lectie_id))

    # Dacă testul e deja completat
    if lp.get("testFinal", {}).get("completat"):
        return redirect(url_for("test_rezultat", lectie_id=lectie_id))

    return render_template("test.html", lectie=l)


@app.route("/lectie/<lectie_id>/test/submit", methods=["POST"])
@login_required
def submit_test(lectie_id):
    l = get_lectie(lectie_id)
    if not l:
        return redirect(url_for("dashboard"))

    user_progres = get_progres_user(session["username"])
    lp = user_progres.get(lectie_id, {})

    if lp.get("testFinal", {}).get("completat"):
        return redirect(url_for("test_rezultat", lectie_id=lectie_id))

    intrebari = l["test"]["intrebari"]
    raspunsuri_user = {}
    corecte = 0
    rezultate = []

    for q in intrebari:
        raspuns_dat = request.form.get(f"q_{q['id']}", "").strip()
        corect = raspuns_dat == q["raspuns_corect"]
        if corect:
            corecte += 1
        raspunsuri_user[q["id"]] = raspuns_dat
        rezultate.append({
            "intrebare": q["intrebare"],
            "raspuns_dat": raspuns_dat,
            "raspuns_corect": q["raspuns_corect"],
            "corect": corect,
            "explicatie": q["explicatie"],
        })

    scor = corecte * 10  # din 100

    if lectie_id not in user_progres:
        user_progres[lectie_id] = {}
    user_progres[lectie_id]["testFinal"] = {
        "completat": True,
        "scor": scor,
        "raspunsuri": raspunsuri_user,
        "rezultate": rezultate,
    }
    save_progres_user(session["username"], user_progres)

    return redirect(url_for("test_rezultat", lectie_id=lectie_id))


@app.route("/lectie/<lectie_id>/test/rezultat")
@login_required
def test_rezultat(lectie_id):
    l = get_lectie(lectie_id)
    if not l:
        return redirect(url_for("dashboard"))

    user_progres = get_progres_user(session["username"])
    lp = user_progres.get(lectie_id, {})
    test_data = lp.get("testFinal", {})

    if not test_data.get("completat"):
        return redirect(url_for("lectie", lectie_id=lectie_id))

    return render_template("test_rezultat.html",
                           lectie=l,
                           scor=test_data["scor"],
                           rezultate=test_data.get("rezultate", []))


# ─── ADMIN ───────────────────────────────────────────────────────────────────

@app.route("/admin")
@admin_required
def admin_index():
    users = load_json("users.json")
    progres = load_json("progres.json")
    lectii = load_json("lectii.json")

    elevi = {u: d for u, d in users.items() if d["rol"] == "elev"}

    stats = []
    for username, _ in elevi.items():
        up = progres.get(username, {})
        complete = sum(1 for l in lectii if up.get(l["id"], {}).get("testFinal", {}).get("completat"))
        stats.append({"username": username, "complete": complete, "total": len(lectii)})

    return render_template("admin/index.html", stats=stats, total_lectii=len(lectii))


@app.route("/admin/users")
@admin_required
def admin_users():
    users = load_json("users.json")
    return render_template("admin/users.html", users=users)


@app.route("/admin/users/add", methods=["POST"])
@admin_required
def admin_add_user():
    username = request.form.get("username", "").strip()
    parola = request.form.get("parola", "").strip()
    nume = request.form.get("nume", "").strip()
    rol = request.form.get("rol", "elev").strip()

    if not username or not parola or not nume:
        flash("Toate câmpurile sunt obligatorii.", "error")
        return redirect(url_for("admin_users"))

    users = load_json("users.json")
    if username in users:
        flash(f"Utilizatorul '{username}' există deja.", "error")
        return redirect(url_for("admin_users"))

    users[username] = {"parola": parola, "rol": rol, "nume": nume}
    save_json("users.json", users)
    flash(f"Utilizatorul '{username}' a fost adăugat.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/delete/<username>", methods=["POST"])
@admin_required
def admin_delete_user(username):
    if username == session["username"]:
        flash("Nu poți șterge propriul cont.", "error")
        return redirect(url_for("admin_users"))

    users = load_json("users.json")
    if username not in users:
        flash("Utilizatorul nu există.", "error")
        return redirect(url_for("admin_users"))

    del users[username]
    save_json("users.json", users)

    # Ștergem și progresul
    progres = load_json("progres.json")
    progres.pop(username, None)
    save_json("progres.json", progres)

    flash(f"Utilizatorul '{username}' a fost șters.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/progres")
@admin_required
def admin_progres():
    users = load_json("users.json")
    progres = load_json("progres.json")
    lectii = load_json("lectii.json")

    elevi_progres = []
    for username, udata in users.items():
        if udata["rol"] != "elev":
            continue
        up = progres.get(username, {})
        lectii_status = []
        for l in lectii:
            lp = up.get(l["id"], {})
            status = get_lectie_status(l, up)
            scor = lp.get("testFinal", {}).get("scor")
            lectii_status.append({
                "id": l["id"],
                "titlu": l["titlu"],
                "status": status,
                "scor": scor,
            })
        elevi_progres.append({
            "username": username,
            "nume": udata["nume"],
            "lectii": lectii_status,
        })

    return render_template("admin/progres.html", elevi_progres=elevi_progres)


@app.route("/admin/lectii")
@admin_required
def admin_lectii():
    lectii = load_json("lectii.json")
    return render_template("admin/lectii.html", lectii=lectii)


@app.route("/admin/lectii/<lectie_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_lectie(lectie_id):
    lectii = load_json("lectii.json")
    lectie = next((l for l in lectii if l["id"] == lectie_id), None)
    if not lectie:
        flash("Lecția nu există.", "error")
        return redirect(url_for("admin_lectii"))

    if request.method == "POST":
        try:
            new_data = json.loads(request.form.get("json_data", "{}"))
            for i, l in enumerate(lectii):
                if l["id"] == lectie_id:
                    lectii[i] = new_data
                    break
            save_json("lectii.json", lectii)
            flash("Lecția a fost salvată.", "success")
        except json.JSONDecodeError as e:
            flash(f"JSON invalid: {e}", "error")
        return redirect(url_for("admin_edit_lectie", lectie_id=lectie_id))

    lectie_json = json.dumps(lectie, ensure_ascii=False, indent=2)
    return render_template("admin/edit_lectie.html", lectie=lectie, lectie_json=lectie_json)


@app.route("/admin/reset_progres/<username>", methods=["POST"])
@admin_required
def admin_reset_progres(username):
    progres = load_json("progres.json")
    progres.pop(username, None)
    save_json("progres.json", progres)
    flash(f"Progresul lui '{username}' a fost resetat.", "success")
    return redirect(url_for("admin_progres"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
