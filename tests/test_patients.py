
from datetime import date, timedelta

import app as app_module


def get_patient_count(app):
    with app_module.get_db_connection() as connection:
        return connection.execute(
            "SELECT COUNT(*) FROM patients"
        ).fetchone()[0]


def get_patient_id():
    with app_module.get_db_connection() as connection:
        row = connection.execute(
            "SELECT id FROM patients ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return row["id"]


def test_patient_registration_successful(client, app, patient_data):
    response = client.post(
        "/patients",
        data=patient_data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Test Patient" in response.data
    assert get_patient_count(app) == 1

    with app_module.get_db_connection() as connection:
        patient = connection.execute(
            "SELECT * FROM patients"
        ).fetchone()

    assert patient["patient_code"] == "P-00001"
    assert patient["email"] == "test.patient@example.com"


def test_reject_future_date_of_birth(client, app, patient_data):
    patient_data["date_of_birth"] = (
        date.today() + timedelta(days=1)
    ).isoformat()

    response = client.post(
        "/patients",
        data=patient_data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Date of birth cannot be in the future." in response.data
    assert get_patient_count(app) == 0


def test_search_patient_by_name(client, patient_data):
    client.post("/patients", data=patient_data)

    response = client.get("/patients?q=Test%20Patient")

    assert response.status_code == 200
    assert b"Test Patient" in response.data


def test_view_patient_details(client, patient_data):
    client.post("/patients", data=patient_data)
    patient_id = get_patient_id()

    response = client.get(f"/patients/{patient_id}")

    assert response.status_code == 200
    assert b"Test Patient" in response.data


def test_edit_patient_details(client, app, patient_data):
    client.post("/patients", data=patient_data)
    patient_id = get_patient_id()

    updated_data = {
        **patient_data,
        "full_name": "Updated Patient",
        "phone": "9123456780",
    }

    response = client.post(
        f"/patients/{patient_id}/edit",
        data=updated_data,
        follow_redirects=True,
    )

    assert response.status_code == 200

    with app_module.get_db_connection() as connection:
        patient = connection.execute(
            "SELECT * FROM patients WHERE id = ?",
            (patient_id,),
        ).fetchone()

    assert patient["full_name"] == "Updated Patient"
    assert patient["phone"] == "9123456780"


def test_reject_invalid_patient_name(client, app, patient_data):
    patient_data["full_name"] = "123Invalid"

    response = client.post(
        "/patients",
        data=patient_data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert (
        b"Name must contain valid letters and punctuation."
        in response.data
    )
    assert get_patient_count(app) == 0


def test_delete_patient_successfully(client, app, patient_data):
    client.post("/patients", data=patient_data)
    patient_id = get_patient_id()

    response = client.post(
        f"/patients/{patient_id}/delete",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Patient record deleted successfully." in response.data
    assert get_patient_count(app) == 0


def test_prevent_deleting_patient_with_appointment(
    client, app, patient_data
):
    client.post("/patients", data=patient_data)
    patient_id = get_patient_id()

    appointment = {
        "patient_id": str(patient_id),
        "doctor_name": "Dr. Sharma",
        "appointment_date": (
            date.today() + timedelta(days=2)
        ).isoformat(),
        "appointment_time": "10:30",
        "reason": "Routine checkup",
    }

    booking_response = client.post(
        "/appointments",
        data=appointment,
        follow_redirects=True,
    )

    assert booking_response.status_code == 200
    assert b"Appointment booked successfully." in booking_response.data

    response = client.post(
        f"/patients/{patient_id}/delete",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert (
        b"This patient has linked appointments and cannot be deleted."
        in response.data
    )
    assert get_patient_count(app) == 1


def test_view_nonexistent_patient(client):
    response = client.get(
        "/patients/99999",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Patient record not found." in response.data


def test_reject_invalid_phone_number(client, app, patient_data):
    patient_data["phone"] = "abc"

    response = client.post(
        "/patients",
        data=patient_data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Enter a valid phone number." in response.data
    assert get_patient_count(app) == 0


def test_reject_invalid_email(client, app, patient_data):
    patient_data["email"] = "invalid-email"

    response = client.post(
        "/patients",
        data=patient_data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Enter a valid email address." in response.data
    assert get_patient_count(app) == 0


def test_reject_invalid_gender(client, app, patient_data):
    patient_data["gender"] = "Unknown"

    response = client.post(
        "/patients",
        data=patient_data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Select a valid gender option." in response.data
    assert get_patient_count(app) == 0


def test_reject_invalid_date_of_birth(client, app, patient_data):
    patient_data["date_of_birth"] = "not-a-date"

    response = client.post(
        "/patients",
        data=patient_data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Enter a valid date of birth." in response.data
    assert get_patient_count(app) == 0


def test_home_redirects_to_patients(client):
    response = client.get("/")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/patients")


def test_health_check(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "healthy"}


def test_edit_nonexistent_patient(client):
    response = client.get(
        "/patients/99999/edit",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Patient record not found." in response.data


def test_reject_invalid_patient_update(
    client, app, patient_data
):
    client.post("/patients", data=patient_data)
    patient_id = get_patient_id()

    updated_data = {
        **patient_data,
        "phone": "abc",
    }

    response = client.post(
        f"/patients/{patient_id}/edit",
        data=updated_data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Enter a valid phone number." in response.data

    with app_module.get_db_connection() as connection:
        patient = connection.execute(
            "SELECT phone FROM patients WHERE id = ?",
            (patient_id,),
        ).fetchone()

    assert patient["phone"] == patient_data["phone"]


def test_delete_nonexistent_patient(client):
    response = client.post(
        "/patients/99999/delete",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Patient record not found." in response.data
