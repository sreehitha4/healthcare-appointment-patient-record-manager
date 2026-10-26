
from datetime import date, timedelta

import app as app_module


def register_patient(client, patient_data):
    client.post("/patients", data=patient_data)

    with app_module.get_db_connection() as connection:
        patient = connection.execute(
            "SELECT id FROM patients ORDER BY id DESC LIMIT 1"
        ).fetchone()

    return patient["id"]


def appointment_data(
    patient_id,
    time="10:30",
    reason="Routine checkup",
):
    return {
        "patient_id": str(patient_id),
        "doctor_name": "Dr. Sharma",
        "appointment_date": (
            date.today() + timedelta(days=2)
        ).isoformat(),
        "appointment_time": time,
        "reason": reason,
    }


def get_appointment_count():
    with app_module.get_db_connection() as connection:
        return connection.execute(
            "SELECT COUNT(*) FROM appointments"
        ).fetchone()[0]


def get_appointment_id():
    with app_module.get_db_connection() as connection:
        row = connection.execute(
            "SELECT id FROM appointments ORDER BY id DESC LIMIT 1"
        ).fetchone()

    return row["id"]


def test_book_appointment_successfully(client, patient_data):
    patient_id = register_patient(client, patient_data)

    response = client.post(
        "/appointments",
        data=appointment_data(patient_id),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Appointment booked successfully." in response.data
    assert b"Test Patient" in response.data
    assert get_appointment_count() == 1


def test_reject_appointment_in_the_past(client, patient_data):
    patient_id = register_patient(client, patient_data)
    data = appointment_data(patient_id)
    data["appointment_date"] = (
        date.today() - timedelta(days=1)
    ).isoformat()

    response = client.post(
        "/appointments",
        data=data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert (
        b"Appointment date and time must be in the future."
        in response.data
    )
    assert get_appointment_count() == 0


def test_prevent_duplicate_doctor_time_slot(client, patient_data):
    patient_id = register_patient(client, patient_data)
    data = appointment_data(patient_id)

    client.post("/appointments", data=data)

    response = client.post(
        "/appointments",
        data=data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"already has a scheduled appointment" in response.data
    assert get_appointment_count() == 1


def test_filter_appointments_by_status(client, patient_data):
    patient_id = register_patient(client, patient_data)

    client.post(
        "/appointments",
        data=appointment_data(
            patient_id, time="10:30", reason="Completed visit"
        ),
    )
    completed_id = get_appointment_id()

    client.post(
        f"/appointments/{completed_id}/status",
        data={"status": "Completed"},
    )

    client.post(
        "/appointments",
        data=appointment_data(
            patient_id, time="11:30", reason="Upcoming visit"
        ),
    )

    completed_response = client.get(
        "/appointments?status=Completed"
    )
    scheduled_response = client.get(
        "/appointments?status=Scheduled"
    )

    assert completed_response.status_code == 200
    assert b"Completed visit" in completed_response.data
    assert b"Upcoming visit" not in completed_response.data

    assert scheduled_response.status_code == 200
    assert b"Upcoming visit" in scheduled_response.data
    assert b"Completed visit" not in scheduled_response.data


def test_edit_scheduled_appointment(client, patient_data):
    patient_id = register_patient(client, patient_data)

    client.post(
        "/appointments",
        data=appointment_data(patient_id),
    )
    appointment_id = get_appointment_id()

    response = client.post(
        f"/appointments/{appointment_id}/edit",
        data=appointment_data(
            patient_id, time="12:30", reason="Updated consultation"
        ),
        follow_redirects=True,
    )

    assert response.status_code == 200

    with app_module.get_db_connection() as connection:
        appointment = connection.execute(
            "SELECT * FROM appointments WHERE id = ?",
            (appointment_id,),
        ).fetchone()

    assert appointment["appointment_time"] == "12:30"
    assert appointment["reason"] == "Updated consultation"


def test_reject_invalid_status_update(client, patient_data):
    patient_id = register_patient(client, patient_data)

    client.post(
        "/appointments",
        data=appointment_data(patient_id),
    )
    appointment_id = get_appointment_id()

    response = client.post(
        f"/appointments/{appointment_id}/status",
        data={"status": "Scheduled"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Invalid appointment status." in response.data

    with app_module.get_db_connection() as connection:
        appointment = connection.execute(
            "SELECT status FROM appointments WHERE id = ?",
            (appointment_id,),
        ).fetchone()

    assert appointment["status"] == "Scheduled"


def test_cancel_scheduled_appointment(client, patient_data):
    patient_id = register_patient(client, patient_data)

    client.post(
        "/appointments",
        data=appointment_data(patient_id),
    )
    appointment_id = get_appointment_id()

    response = client.post(
        f"/appointments/{appointment_id}/status",
        data={"status": "Cancelled"},
        follow_redirects=True,
    )

    assert response.status_code == 200

    with app_module.get_db_connection() as connection:
        appointment = connection.execute(
            "SELECT status FROM appointments WHERE id = ?",
            (appointment_id,),
        ).fetchone()

    assert appointment["status"] == "Cancelled"


def test_reject_appointment_for_nonexistent_patient(
    client, patient_data
):
    response = client.post(
        "/appointments",
        data=appointment_data(99999),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert (
        b"Select an existing registered patient."
        in response.data
    )
    assert get_appointment_count() == 0


def test_cannot_edit_completed_appointment(client, patient_data):
    patient_id = register_patient(client, patient_data)

    client.post(
        "/appointments",
        data=appointment_data(patient_id),
    )
    appointment_id = get_appointment_id()

    client.post(
        f"/appointments/{appointment_id}/status",
        data={"status": "Completed"},
    )

    response = client.get(
        f"/appointments/{appointment_id}/edit",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert (
        b"Only scheduled appointments can be rescheduled."
        in response.data
    )


def test_edit_nonexistent_appointment(client):
    response = client.get(
        "/appointments/99999/edit",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Appointment not found." in response.data


def test_reject_invalid_doctor_name(client, patient_data):
    patient_id = register_patient(client, patient_data)
    data = appointment_data(patient_id)
    data["doctor_name"] = "123Invalid"

    response = client.post(
        "/appointments",
        data=data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert get_appointment_count() == 0


def test_reject_invalid_appointment_time(client, patient_data):
    patient_id = register_patient(client, patient_data)
    data = appointment_data(patient_id)
    data["appointment_time"] = "25:90"

    response = client.post(
        "/appointments",
        data=data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert (
        b"Enter a valid appointment date and time."
        in response.data
    )
    assert get_appointment_count() == 0


def test_status_update_for_nonexistent_appointment(client):
    response = client.post(
        "/appointments/99999/status",
        data={"status": "Completed"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert (
        b"Appointment not found or is no longer scheduled."
        in response.data
    )
