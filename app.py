from flask import Flask, render_template, request, redirect, url_for
import psutil
import sqlite3
from datetime import datetime

app = Flask(__name__)

DATABASE = "cloudpulse.db"


# ---------------- DATABASE ----------------

def create_database():
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monitoring_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cpu REAL NOT NULL,
            memory REAL NOT NULL,
            disk REAL NOT NULL,
            health TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alert_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resource TEXT NOT NULL,
            usage REAL NOT NULL,
            status TEXT NOT NULL,
            message TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            warning_threshold REAL NOT NULL,
            critical_threshold REAL NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resource_states (
            resource TEXT PRIMARY KEY,
            status TEXT NOT NULL
        )
    """)

    cursor.execute("""
        INSERT OR IGNORE INTO settings
        (id, warning_threshold, critical_threshold)
        VALUES (1, 70, 85)
    """)

    for resource in ["CPU", "Memory", "Storage"]:
        cursor.execute("""
            INSERT OR IGNORE INTO resource_states
            (resource, status)
            VALUES (?, ?)
        """, (resource, "Normal"))

    connection.commit()
    connection.close()


# ---------------- SETTINGS ----------------

def get_thresholds():
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT warning_threshold, critical_threshold
        FROM settings
        WHERE id = 1
    """)

    result = cursor.fetchone()

    connection.close()

    return result[0], result[1]


def update_thresholds(warning, critical):
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE settings
        SET warning_threshold = ?,
            critical_threshold = ?
        WHERE id = 1
    """, (warning, critical))

    connection.commit()
    connection.close()


# ---------------- STATUS ----------------

def get_status(value, warning, critical):
    if value >= critical:
        return "Critical"

    elif value >= warning:
        return "Warning"

    else:
        return "Normal"


# ---------------- RESOURCE STATE ----------------

def get_previous_status(resource):
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT status
        FROM resource_states
        WHERE resource = ?
    """, (resource,))

    result = cursor.fetchone()

    connection.close()

    if result:
        return result[0]

    return "Normal"


def update_resource_status(resource, status):
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE resource_states
        SET status = ?
        WHERE resource = ?
    """, (status, resource))

    connection.commit()
    connection.close()


# ---------------- MONITORING ----------------

def save_reading(cpu, memory, disk, health):
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    recorded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO monitoring_history
        (cpu, memory, disk, health, recorded_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        cpu,
        memory,
        disk,
        health,
        recorded_at
    ))

    connection.commit()
    connection.close()


def get_recent_history():
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT cpu, memory, disk, health, recorded_at
        FROM monitoring_history
        ORDER BY id DESC
        LIMIT 10
    """)

    history = cursor.fetchall()

    connection.close()

    return history


# ---------------- ALERTS ----------------

def save_alert(resource, usage, status):
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    recorded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    message = f"{resource} usage reached {usage}%"

    cursor.execute("""
        INSERT INTO alert_history
        (resource, usage, status, message, recorded_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        resource,
        usage,
        status,
        message,
        recorded_at
    ))

    connection.commit()
    connection.close()


def process_alert(resource, usage, status):

    previous_status = get_previous_status(resource)

    # Save only when the status changes
    if status != previous_status:

        if status != "Normal":
            save_alert(
                resource,
                usage,
                status
            )

        update_resource_status(
            resource,
            status
        )


def get_alert_history():
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT resource, usage, status, message, recorded_at
        FROM alert_history
        ORDER BY id DESC
        LIMIT 10
    """)

    alerts = cursor.fetchall()

    connection.close()

    return alerts


# ---------------- DASHBOARD ----------------

@app.route("/")
def dashboard():

    warning_threshold, critical_threshold = get_thresholds()

    cpu_usage = psutil.cpu_percent(interval=1)
    memory_usage = psutil.virtual_memory().percent
    disk_usage = psutil.disk_usage("/").percent

    cpu_status = get_status(
        cpu_usage,
        warning_threshold,
        critical_threshold
    )

    memory_status = get_status(
        memory_usage,
        warning_threshold,
        critical_threshold
    )

    disk_status = get_status(
        disk_usage,
        warning_threshold,
        critical_threshold
    )

    statuses = [
        cpu_status,
        memory_status,
        disk_status
    ]

    if "Critical" in statuses:
        health = "Critical"

    elif "Warning" in statuses:
        health = "Warning"

    else:
        health = "Normal"

    resources = [
        ("CPU", cpu_usage, cpu_status),
        ("Memory", memory_usage, memory_status),
        ("Storage", disk_usage, disk_status)
    ]

    alerts = []

    for resource, usage, status in resources:

        if status != "Normal":
            alerts.append(
                f"{resource} usage is {status}: {usage}%"
            )

        # Prevent duplicate alert records
        process_alert(
            resource,
            usage,
            status
        )

    save_reading(
        cpu_usage,
        memory_usage,
        disk_usage,
        health
    )

    history = get_recent_history()

    alert_history = get_alert_history()

    graph_history = list(reversed(history))

    graph_times = []
    graph_cpu = []
    graph_memory = []
    graph_disk = []

    for record in graph_history:

        graph_cpu.append(record[0])
        graph_memory.append(record[1])
        graph_disk.append(record[2])

        graph_times.append(
            record[4].split(" ")[1]
        )

    return render_template(
        "dashboard.html",

        cpu=cpu_usage,
        memory=memory_usage,
        disk=disk_usage,

        cpu_status=cpu_status,
        memory_status=memory_status,
        disk_status=disk_status,

        health=health,

        alerts=alerts,
        alert_history=alert_history,

        history=history,

        graph_times=graph_times,
        graph_cpu=graph_cpu,
        graph_memory=graph_memory,
        graph_disk=graph_disk,

        warning_threshold=warning_threshold,
        critical_threshold=critical_threshold
    )


# ---------------- SETTINGS ----------------

@app.route("/settings", methods=["GET", "POST"])
def settings():

    warning_threshold, critical_threshold = get_thresholds()

    error = None

    if request.method == "POST":

        try:
            warning = float(
                request.form["warning_threshold"]
            )

            critical = float(
                request.form["critical_threshold"]
            )

            if warning < 0 or critical > 100:

                error = (
                    "Thresholds must be between 0 and 100."
                )

            elif warning >= critical:

                error = (
                    "Warning threshold must be lower "
                    "than critical threshold."
                )

            else:

                update_thresholds(
                    warning,
                    critical
                )

                return redirect(
                    url_for("dashboard")
                )

        except ValueError:

            error = "Please enter valid numbers."

    return render_template(
        "settings.html",

        warning_threshold=warning_threshold,
        critical_threshold=critical_threshold,

        error=error
    )


if __name__ == "__main__":
    create_database()
    app.run(host="0.0.0.0", port=5000, debug=False)