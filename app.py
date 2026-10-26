import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
)

from config import DATABASE_PATH, SECRET_KEY


# =========================================================
# APPLICATION CONFIGURATION
# =========================================================

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
app.config["DATABASE"] = str(DATABASE_PATH)


# =========================================================
# DATABASE CONNECTION AND INITIALIZATION
# =========================================================

def get_db_connection():
    """Create a connection to the project's SQLite database."""
    database_path = Path(app.config["DATABASE"])
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def initialize_database():
    """Create required tables and indexes if they do not exist."""
    with get_db_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_code TEXT UNIQUE,
                full_name TEXT NOT NULL,
                date_of_birth TEXT NOT NULL,
                gender TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT,
                address TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL,
                doctor_name TEXT NOT NULL,
                appointment_date TEXT NOT NULL,
                appointment_time TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Scheduled'
                    CHECK (
                        status IN (
                            'Scheduled',
                            'Completed',
                            'Cancelled'
                        )
                    ),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (patient_id) REFERENCES patients(id)
            )
        """)

        connection.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            unique_scheduled_doctor_slot
            ON appointments (
                doctor_name COLLATE NOCASE,
                appointment_date,
                appointment_time
            )
            WHERE status = 'Scheduled'
        """)


# =========================================================
# PATIENT VALIDATION
# =========================================================

def validate_patient(form):
    """Validate patient registration and editing form fields."""

    full_name = form.get("full_name", "").strip()
    dob = form.get("date_of_birth", "").strip()
    gender = form.get("gender", "").strip()
    phone = form.get("phone", "").strip()
    email = form.get("email", "").strip()
    address = form.get("address", "").strip()

    if not full_name or len(full_name) > 100:
        return None, "Enter a name of at most 100 characters."

    # Correct regex: * means zero or more valid characters.
    if not re.fullmatch(r"[A-Za-z][A-Za-z .'-]*", full_name):
        return None, "Name must contain valid letters and punctuation."

    try:
        birth_date = date.fromisoformat(dob)

        if birth_date > date.today():
            return None, "Date of birth cannot be in the future."

    except (ValueError, TypeError):
        return None, "Enter a valid date of birth."

    if gender not in {
        "Female",
        "Male",
        "Other",
        "Prefer not to say",
    }:
        return None, "Select a valid gender option."

    if not re.fullmatch(r"[0-9+() .-]{7,20}", phone):
        return None, "Enter a valid phone number."

    if email and (
        len(email) > 254
        or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
    ):
        return None, "Enter a valid email address."

    if len(address) > 300:
        return None, "Address must be 300 characters or fewer."

    return {
        "full_name": full_name,
        "date_of_birth": dob,
        "gender": gender,
        "phone": phone,
        "email": email or None,
        "address": address or None,
    }, None


# =========================================================
# APPOINTMENT VALIDATION
# =========================================================

def validate_appointment(form):
    """Validate appointment details before saving them."""

    try:
        patient_id = int(form.get("patient_id", ""))
    except (ValueError, TypeError):
        return None, "Select a valid registered patient."

    doctor_name = form.get("doctor_name", "").strip()
    appointment_date = form.get("appointment_date", "").strip()
    appointment_time = form.get("appointment_time", "").strip()
    reason = form.get("reason", "").strip()

    if patient_id <= 0:
        return None, "Select a valid registered patient."

    if (
        not doctor_name
        or len(doctor_name) > 100
        or not re.fullmatch(r"[A-Za-z][A-Za-z .'-]*", doctor_name)
    ):
        return None, "Enter a valid doctor's name."

    try:
        selected_date = date.fromisoformat(appointment_date)

        selected_time = datetime.strptime(
            appointment_time, "%H:%M"
        ).time()

    except (ValueError, TypeError):
        return None, "Enter a valid appointment date and time."

    selected_datetime = datetime.combine(
        selected_date, selected_time
    )

    if selected_datetime <= datetime.now():
        return None, "Appointment date and time must be in the future."

    if not reason or len(reason) > 500:
        return None, "Enter a reason of at most 500 characters."

    return {
        "patient_id": patient_id,
        "doctor_name": doctor_name,
        "appointment_date": appointment_date,
        "appointment_time": appointment_time,
        "reason": reason,
    }, None


# =========================================================
# HOME AND HEALTH CHECK
# =========================================================

@app.route("/")
def home():
    return redirect(url_for("patients"))


@app.route("/health")
def health_check():
    return {"status": "healthy"}


# =========================================================
# PATIENT LIST, REGISTRATION AND SEARCH
# =========================================================

@app.route("/patients", methods=["GET", "POST"])
def patients():

    if request.method == "POST":
        patient, error = validate_patient(request.form)

        if error:
            flash(error, "danger")

        else:
            try:
                with get_db_connection() as connection:
                    cursor = connection.execute("""
                        INSERT INTO patients (
                            full_name,
                            date_of_birth,
                            gender,
                            phone,
                            email,
                            address
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        patient["full_name"],
                        patient["date_of_birth"],
                        patient["gender"],
                        patient["phone"],
                        patient["email"],
                        patient["address"],
                    ))

                    patient_id = cursor.lastrowid
                    patient_code = f"P-{patient_id:05d}"

                    connection.execute("""
                        UPDATE patients
                        SET patient_code = ?
                        WHERE id = ?
                    """, (patient_code, patient_id))

                flash(
                    f"Patient registered successfully! ID: {patient_code}",
                    "success",
                )

                return redirect(url_for("patients"))

            except sqlite3.IntegrityError:
                app.logger.exception(
                    "Patient registration integrity error"
                )
                flash(
                    "Patient registration failed. Check the supplied details.",
                    "danger",
                )

            except sqlite3.Error:
                app.logger.exception(
                    "Patient registration database error"
                )
                flash(
                    "A database error prevented patient registration.",
                    "danger",
                )

    search_query = request.args.get("q", "").strip()

    with get_db_connection() as connection:
        if search_query:
            pattern = f"%{search_query}%"

            patient_rows = connection.execute("""
                SELECT *
                FROM patients
                WHERE patient_code LIKE ?
                   OR full_name LIKE ?
                   OR phone LIKE ?
                ORDER BY id DESC
            """, (pattern, pattern, pattern)).fetchall()

        else:
            patient_rows = connection.execute("""
                SELECT *
                FROM patients
                ORDER BY id DESC
            """).fetchall()

    return render_template(
        "patients/index.html",
        patients=patient_rows,
        search_query=search_query,
        today=date.today().isoformat(),
    )


# =========================================================
# VIEW PATIENT
# =========================================================

@app.route("/patients/<int:patient_id>")
def view_patient(patient_id):

    with get_db_connection() as connection:
        patient = connection.execute("""
            SELECT *
            FROM patients
            WHERE id = ?
        """, (patient_id,)).fetchone()

    if patient is None:
        flash("Patient record not found.", "danger")
        return redirect(url_for("patients"))

    return render_template(
        "patients/view.html",
        patient=patient,
    )


# =========================================================
# EDIT PATIENT
# =========================================================

@app.route(
    "/patients/<int:patient_id>/edit",
    methods=["GET", "POST"],
)
def edit_patient(patient_id):

    with get_db_connection() as connection:
        patient = connection.execute("""
            SELECT *
            FROM patients
            WHERE id = ?
        """, (patient_id,)).fetchone()

    if patient is None:
        flash("Patient record not found.", "danger")
        return redirect(url_for("patients"))

    if request.method == "POST":
        updated_patient, error = validate_patient(request.form)

        if error:
            flash(error, "danger")

        else:
            try:
                with get_db_connection() as connection:
                    connection.execute("""
                        UPDATE patients
                        SET full_name = ?,
                            date_of_birth = ?,
                            gender = ?,
                            phone = ?,
                            email = ?,
                            address = ?
                        WHERE id = ?
                    """, (
                        updated_patient["full_name"],
                        updated_patient["date_of_birth"],
                        updated_patient["gender"],
                        updated_patient["phone"],
                        updated_patient["email"],
                        updated_patient["address"],
                        patient_id,
                    ))

                flash(
                    "Patient details updated successfully.",
                    "success",
                )

                return redirect(
                    url_for("view_patient", patient_id=patient_id)
                )

            except sqlite3.Error:
                app.logger.exception("Patient update database error")
                flash(
                    "Could not update the patient record.",
                    "danger",
                )

    return render_template(
        "patients/edit.html",
        patient=patient,
        today=date.today().isoformat(),
    )


# =========================================================
# DELETE PATIENT
# =========================================================

@app.route(
    "/patients/<int:patient_id>/delete",
    methods=["POST"],
)
def delete_patient(patient_id):

    try:
        with get_db_connection() as connection:
            patient = connection.execute("""
                SELECT id
                FROM patients
                WHERE id = ?
            """, (patient_id,)).fetchone()

            if patient is None:
                flash("Patient record not found.", "danger")
                return redirect(url_for("patients"))

            connection.execute("""
                DELETE FROM patients
                WHERE id = ?
            """, (patient_id,))

        flash("Patient record deleted successfully.", "success")

    except sqlite3.IntegrityError:
        flash(
            "This patient has linked appointments and cannot be deleted.",
            "danger",
        )

    except sqlite3.Error:
        app.logger.exception("Patient deletion database error")
        flash(
            "Could not delete the patient record.",
            "danger",
        )

    return redirect(url_for("patients"))


# =========================================================
# APPOINTMENT LIST AND BOOKING
# =========================================================

@app.route("/appointments", methods=["GET", "POST"])
def appointments():

    if request.method == "POST":
        appointment, error = validate_appointment(request.form)

        if error:
            flash(error, "danger")

        else:
            try:
                with get_db_connection() as connection:
                    patient = connection.execute("""
                        SELECT id
                        FROM patients
                        WHERE id = ?
                    """, (appointment["patient_id"],)).fetchone()

                    if patient is None:
                        flash(
                            "Select an existing registered patient.",
                            "danger",
                        )
                        return redirect(url_for("appointments"))

                    connection.execute("""
                        INSERT INTO appointments (
                            patient_id,
                            doctor_name,
                            appointment_date,
                            appointment_time,
                            reason
                        )
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        appointment["patient_id"],
                        appointment["doctor_name"],
                        appointment["appointment_date"],
                        appointment["appointment_time"],
                        appointment["reason"],
                    ))

                flash("Appointment booked successfully.", "success")
                return redirect(url_for("appointments"))

            except sqlite3.IntegrityError:
                flash(
                    "That doctor already has a scheduled appointment "
                    "at this date and time. Choose another slot.",
                    "danger",
                )

            except sqlite3.Error:
                app.logger.exception(
                    "Appointment booking database error"
                )
                flash("Could not book the appointment.", "danger")

    # Normalize the selected status to handle capitalization differences.
    requested_status = request.args.get("status", "").strip()

    allowed_statuses = {
        "Scheduled",
        "Completed",
        "Cancelled",
    }

    status_lookup = {
        status.casefold(): status
        for status in allowed_statuses
    }

    status_filter = status_lookup.get(
        requested_status.casefold(), ""
    )

    with get_db_connection() as connection:

        patients_list = connection.execute("""
            SELECT id, patient_code, full_name
            FROM patients
            ORDER BY full_name COLLATE NOCASE
        """).fetchall()

        # The JOIN retrieves the registered patient's name and code.
        query = """
            SELECT
                a.*,
                p.patient_code,
                p.full_name,
                p.phone
            FROM appointments AS a
            JOIN patients AS p ON p.id = a.patient_id
        """

        parameters = ()

        # Only appointments matching the selected status are returned.
        if status_filter:
            query += " WHERE LOWER(TRIM(a.status)) = LOWER(?)"
            parameters = (status_filter,)

        query += """
            ORDER BY
                a.appointment_date DESC,
                a.appointment_time DESC
        """

        appointment_rows = connection.execute(
            query, parameters
        ).fetchall()

    return render_template(
        "appointments/index.html",
        patients=patients_list,
        appointments=appointment_rows,
        status_filter=status_filter,
        today=date.today().isoformat(),
    )


# =========================================================
# RESCHEDULE / EDIT APPOINTMENT
# =========================================================

@app.route(
    "/appointments/<int:appointment_id>/edit",
    methods=["GET", "POST"],
)
def edit_appointment(appointment_id):

    with get_db_connection() as connection:
        appointment = connection.execute("""
            SELECT *
            FROM appointments
            WHERE id = ?
        """, (appointment_id,)).fetchone()

        patients_list = connection.execute("""
            SELECT id, patient_code, full_name
            FROM patients
            ORDER BY full_name COLLATE NOCASE
        """).fetchall()

    if appointment is None:
        flash("Appointment not found.", "danger")
        return redirect(url_for("appointments"))

    if appointment["status"] != "Scheduled":
        flash(
            "Only scheduled appointments can be rescheduled.",
            "warning",
        )
        return redirect(url_for("appointments"))

    if request.method == "POST":
        updated, error = validate_appointment(request.form)

        if error:
            flash(error, "danger")

        else:
            try:
                with get_db_connection() as connection:
                    patient = connection.execute("""
                        SELECT id
                        FROM patients
                        WHERE id = ?
                    """, (updated["patient_id"],)).fetchone()

                    if patient is None:
                        flash(
                            "Select an existing registered patient.",
                            "danger",
                        )
                        return redirect(
                            url_for(
                                "edit_appointment",
                                appointment_id=appointment_id,
                            )
                        )

                    connection.execute("""
                        UPDATE appointments
                        SET patient_id = ?,
                            doctor_name = ?,
                            appointment_date = ?,
                            appointment_time = ?,
                            reason = ?
                        WHERE id = ?
                          AND status = 'Scheduled'
                    """, (
                        updated["patient_id"],
                        updated["doctor_name"],
                        updated["appointment_date"],
                        updated["appointment_time"],
                        updated["reason"],
                        appointment_id,
                    ))

                flash(
                    "Appointment updated successfully.",
                    "success",
                )
                return redirect(url_for("appointments"))

            except sqlite3.IntegrityError:
                flash(
                    "That doctor already has a scheduled appointment "
                    "at this date and time. Choose another slot.",
                    "danger",
                )

            except sqlite3.Error:
                app.logger.exception(
                    "Appointment update database error"
                )
                flash("Could not update the appointment.", "danger")

    return render_template(
        "appointments/edit.html",
        appointment=appointment,
        patients=patients_list,
        today=date.today().isoformat(),
    )


# =========================================================
# APPOINTMENT STATUS: COMPLETE OR CANCEL
# =========================================================

@app.route(
    "/appointments/<int:appointment_id>/status",
    methods=["POST"],
)
def update_appointment_status(appointment_id):

    new_status = request.form.get("status", "").strip()

    if new_status not in {"Completed", "Cancelled"}:
        flash("Invalid appointment status.", "danger")
        return redirect(url_for("appointments"))

    try:
        with get_db_connection() as connection:
            cursor = connection.execute("""
                UPDATE appointments
                SET status = ?
                WHERE id = ?
                  AND status = 'Scheduled'
            """, (new_status, appointment_id))

            if cursor.rowcount == 0:
                flash(
                    "Appointment not found or is no longer scheduled.",
                    "warning",
                )
            else:
                flash(
                    f"Appointment marked as {new_status.lower()}.",
                    "success",
                )

    except sqlite3.Error:
        app.logger.exception(
            "Appointment status update database error"
        )
        flash(
            "Could not update the appointment status.",
            "danger",
        )

    return redirect(url_for("appointments"))


# =========================================================
# APPLICATION ENTRY POINT
# =========================================================

# Keep this initialization because your existing project uses it.
initialize_database()


if __name__ == "__main__":
    app.run(debug=True)