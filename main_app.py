import os
import cv2
import numpy as np
import psycopg2
import hashlib
import time
from datetime import datetime
from flask import Flask, render_template, Response, request, redirect, url_for, session, jsonify
import base64
import sys
import psutil
import signal
import io
import json
import csv

# --- PostgreSQL Database Configuration ---
DB_URL = os.environ.get('DATABASE_URL')

# --- Teacher Password Configuration ---
TEACHER_PASSWORD_HASH = 'f83dfe46f0933ff4ec08b974ce9c5633ecc6cbeb59f572b9b25e1c07e4a18843'

# --- OpenCV Face Recognizer and Cascade Classifier ---
recognizer = cv2.face.LBPHFaceRecognizer_create()
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

# --- Global Data ---
known_faces_data = {}
FACE_THRESHOLD = 60  # Lower value means a stricter match

app = Flask(__name__)
app.secret_key = 'your_super_secret_key'
app.config['MAX_CONTENT_LENGTH'] = 60 * 1024 * 1024

def get_db_connection():
    try:
        if not DB_URL:
            print("Error: DATABASE_URL environment variable is not set.")
            return None
        return psycopg2.connect(DB_URL)
    except psycopg2.Error as err:
        print(f"Database connection error: {err}")
        return None

def load_known_faces():
    global known_faces_data
    known_faces_data.clear()

    conn = get_db_connection()
    if not conn:
        print("Could not connect to database to load faces.")
        return

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT registration_number, name, face_embedding FROM students")
        results = cursor.fetchall()

        face_images = []
        face_labels = []

        for i, (reg_no, name, embedding_blob) in enumerate(results):
            try:
                embedding_array = np.frombuffer(embedding_blob, dtype=np.int32).reshape(100, 100)
                face_images.append(embedding_array)
                face_labels.append(i)

                known_faces_data[i] = {
                    'reg_no': reg_no,
                    'name': name
                }
            except Exception as e:
                print(f"Error processing embedding for {reg_no}: {e}")
                continue

        if face_images:
            recognizer.train(face_images, np.array(face_labels))
            print(f"Loaded and trained recognizer with {len(face_images)} student faces.")
        else:
            print("No faces found in the database. Recognizer not trained.")

    except psycopg2.Error as err:
        print(f"Error loading faces from database: {err}")
    finally:
        if conn and not conn.closed:
            cursor.close()
            conn.close()

def mark_attendance(reg_no, current_time):
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()

        sql_update_student = "UPDATE students SET total_attendance = total_attendance + 1, last_attendance_time = %s WHERE registration_number = %s"
        cursor.execute(sql_update_student, (current_time, reg_no))

        sql_insert_log = "INSERT INTO attendance_log (registration_number, timestamp) VALUES (%s, %s)"
        cursor.execute(sql_insert_log, (reg_no, current_time))

        conn.commit()
        print(f"Attendance marked for {known_faces_data[reg_no]['name']} ({reg_no})")

    except psycopg2.Error as err:
        print(f"Error updating attendance: {err}")
    finally:
        if conn and not conn.closed:
            cursor.close()
            conn.close()

# Initial load of known faces on startup
print("Loading known faces...")
load_known_faces()

@app.route('/')
def home():
    return redirect(url_for('main_menu'))

@app.route('/main_menu')
def main_menu():
    return render_template('main_menu.html')

@app.route('/teacher_login', methods=['GET', 'POST'])
def teacher_login():
    if request.method == 'POST':
        password = request.form['password']
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        if password_hash == TEACHER_PASSWORD_HASH:
            session['logged_in'] = True
            return redirect(url_for('teacher_menu'))
        else:
            return render_template('teacher_login.html', error="Invalid password. Please try again.")
    return render_template('teacher_login.html', error=None)

@app.route('/teacher_menu')
def teacher_menu():
    if not session.get('logged_in'):
        return redirect(url_for('teacher_login'))
    return render_template('teacher_menu.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('main_menu'))

@app.route('/manage_students')
def manage_students():
    if not session.get('logged_in'):
        return redirect(url_for('teacher_login'))

    conn = get_db_connection()
    if not conn:
        return "Database connection error.", 500

    students = []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT registration_number, name, major, year, starting_year, total_attendance FROM students")
        students = cursor.fetchall()
        students = [{"registration_number": s[0], "name": s[1], "major": s[2], "year": s[3], "starting_year": s[4], "total_attendance": s[5]} for s in students]
    except psycopg2.Error as err:
        print(f"Error fetching students: {err}")
        return f"An error occurred while fetching student data: {err}", 500
    finally:
        if conn and not conn.closed:
            cursor.close()
            conn.close()

    return render_template('manage_students.html', students=students)

@app.route('/add_student', methods=['GET', 'POST'])
def add_student():
    if not session.get('logged_in'):
        return redirect(url_for('teacher_login'))

    if request.method == 'POST':
        reg_no = request.form['reg_no']
        name = request.form['name']
        major = request.form['major']
        year = request.form['year']
        starting_year = request.form['starting_year']

        image_data = request.form.get('camera_image_data')
        if not image_data:
            return jsonify({'success': False, 'message': 'No image data provided. Please capture a photo.'}), 400

        try:
            header, encoded_data = image_data.split(',', 1)
            image_bytes = base64.b64decode(encoded_data)
            np_arr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        except Exception as e:
            print(f"Error decoding image data: {e}")
            return jsonify({'success': False, 'message': 'Failed to decode image data. Please try again.'}), 400

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)

        if len(faces) != 1:
            return jsonify({'success': False, 'message': f'Found {len(faces)} faces. Please ensure only one clear face is in the picture.'}), 400

        (x, y, w, h) = faces[0]
        roi_gray = gray[y:y+h, x:x+w]

        # Resize to a consistent size for the recognizer
        resized_roi = cv2.resize(roi_gray, (100, 100))
        embedding_array = np.array(resized_roi).flatten()

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection error.'}), 500

        try:
            cursor = conn.cursor()
            sql = "INSERT INTO students (registration_number, name, major, year, starting_year, face_embedding) VALUES (%s, %s, %s, %s, %s, %s)"
            embedding_bytes = embedding_array.astype(np.int32).tobytes()
            cursor.execute(sql, (reg_no, name, major, year, starting_year, psycopg2.Binary(embedding_bytes)))
            conn.commit()

            print("Student added successfully!")
            load_known_faces()

            return jsonify({'success': True, 'message': 'Student added successfully!', 'redirect_url': url_for('teacher_menu')})

        except psycopg2.Error as err:
            if err.pgcode == '23505': # Unique violation
                return jsonify({'success': False, 'message': f"Error: Registration number {reg_no} already exists."}), 409
            else:
                print(f"Database error: {err}")
                return jsonify({'success': False, 'message': f"An unexpected error occurred: {err}"}), 500
        finally:
            if conn and not conn.closed:
                cursor.close()
                conn.close()

    return render_template('add_student.html', current_year=datetime.now().year)

@app.route('/edit_student/<reg_no>', methods=['GET', 'POST'])
def edit_student(reg_no):
    if not session.get('logged_in'):
        return redirect(url_for('teacher_login'))

    conn = get_db_connection()
    if not conn:
        return "Database connection error.", 500

    student = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM students WHERE registration_number = %s", (reg_no,))
        student = cursor.fetchone()
        if student:
            student = {"registration_number": student[0], "name": student[1], "major": student[2], "year": student[3], "starting_year": student[4], "total_attendance": student[5]}
    except psycopg2.Error as err:
        print(f"Error fetching student data: {err}")
        return f"An error occurred while fetching student data: {err}", 500
    finally:
        if conn and not conn.closed:
            cursor.close()
            conn.close()

    if not student:
        return "Student not found.", 404

    if request.method == 'POST':
        name = request.form['name']
        major = request.form['major']
        year = request.form['year']
        starting_year = request.form['starting_year']

        conn_update = get_db_connection()
        if not conn_update:
            return "Database connection error.", 500

        try:
            cursor_update = conn_update.cursor()
            sql = "UPDATE students SET name = %s, major = %s, year = %s, starting_year = %s WHERE registration_number = %s"
            cursor_update.execute(sql, (name, major, year, starting_year, reg_no))
            conn_update.commit()
            return redirect(url_for('manage_students'))
        except psycopg2.Error as err:
            print(f"Error updating student data: {err}")
            return f"An error occurred while updating the student: {err}", 500
        finally:
            if conn_update and not conn_update.closed:
                cursor_update.close()
                conn_update.close()

    return render_template('edit_student.html', student=student, current_year=datetime.now().year)

@app.route('/delete_student/<reg_no>', methods=['POST'])
def delete_student(reg_no):
    if not session.get('logged_in'):
        return redirect(url_for('teacher_login'))

    conn = get_db_connection()
    if not conn:
        return "Database connection error.", 500

    try:
        cursor = conn.cursor()

        cursor.execute("DELETE FROM attendance_log WHERE registration_number = %s", (reg_no,))
        cursor.execute("DELETE FROM students WHERE registration_number = %s", (reg_no,))
        conn.commit()

        load_known_faces()

    except psycopg2.Error as err:
        print(f"Error deleting student: {err}")
        return f"An error occurred while deleting the student: {err}", 500
    finally:
        if conn and not conn.closed:
            cursor.close()
            conn.close()

    return redirect(url_for('manage_students'))

@app.route('/attendance')
def attendance():
    return render_template('index.html')

# New route to process frames from the browser
@app.route('/process_frame', methods=['POST'])
def process_frame():
    data = request.json
    encoded_frame = data['frame']
    
    try:
        header, encoded_data = encoded_frame.split(',', 1)
        image_bytes = base64.b64decode(encoded_data)
        np_arr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)

        for (x, y, w, h) in faces:
            roi_gray = gray[y:y+h, x:x+w]
            resized_roi = cv2.resize(roi_gray, (100, 100))

            label_id, confidence = recognizer.predict(resized_roi)

            name = "Unknown"
            if confidence < FACE_THRESHOLD:
                if label_id in known_faces_data:
                    reg_no = known_faces_data[label_id]['reg_no']
                    name = known_faces_data[label_id]['name']

                    now = datetime.now()
                    last_marked = known_faces_data[label_id].get('last_marked')
                    if not last_marked or (now - last_marked).total_seconds() > 30: # 30-second cooldown
                        mark_attendance(reg_no, now)
                        known_faces_data[label_id]['last_marked'] = now

            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
            cv2.rectangle(frame, (x, y+h-35), (x+w, y+h), (0, 255, 0), cv2.FILLED)
            font = cv2.FONT_HERSHEY_DUPLEX
            cv2.putText(frame, name, (x + 6, y+h - 6), font, 0.5, (255, 255, 255), 1)

        _, buffer = cv2.imencode('.jpg', frame)
        processed_frame = base64.b64encode(buffer).decode('utf-8')
        return jsonify({'frame': processed_frame})

    except Exception as e:
        print(f"Error processing frame: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/get_latest_attendance')
def get_latest_attendance():
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection error.'}), 500

    try:
        cursor = conn.cursor()
        sql = """
        SELECT s.name, s.registration_number AS reg_no, al.timestamp
        FROM attendance_log al
        JOIN students s ON al.registration_number = s.registration_number
        ORDER BY al.timestamp DESC
        LIMIT 10
        """
        cursor.execute(sql)
        latest_attendance = cursor.fetchall()

        latest_attendance = [{"name": row[0], "reg_no": row[1], "timestamp": row[2].strftime('%Y-%m-%d %H:%M:%S')} for row in latest_attendance]

        return jsonify(latest_attendance)
    except psycopg2.Error as err:
        print(f"Error fetching latest attendance log: {err}")
        return jsonify({'error': 'An error occurred fetching data.'}), 500
    finally:
        if conn and not conn.closed:
            cursor.close()
            conn.close()

@app.route('/shutdown', methods=['POST'])
def shutdown():
    print("Shutting down the server...")
    os.kill(os.getpid(), signal.SIGINT)
    parent_pid = os.getppid()
    try:
        parent = psutil.Process(parent_pid)
        if parent:
            parent.terminate()
            parent.wait(timeout=3)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
        pass
    except Exception as e:
        print(f"An unexpected error occurred during termination: {e}")
    sys.exit(0)
    return "Server is shutting down..."

@app.route('/export_students_csv')
def export_students_csv():
    if not session.get('logged_in'):
        return redirect(url_for('teacher_login'))

    conn = get_db_connection()
    if not conn:
        return "Database connection error.", 500

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT registration_number, name, major, year, starting_year, total_attendance FROM students")
        students = cursor.fetchall()

        output = io.StringIO()
        writer = csv.writer(output)

        header = ['Registration Number', 'Name', 'Major', 'Year', 'Starting Year', 'Total Attendance']
        writer.writerow(header)

        for student in students:
            writer.writerow(student)

        csv_data = output.getvalue()

        response = Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=students_data.csv"}
        )
        return response

    except psycopg2.Error as err:
        print(f"Error exporting data to CSV: {err}")
        return "An error occurred while exporting data.", 500
    finally:
        if conn and not conn.closed:
            cursor.close()
            conn.close()

if __name__ == '__main__':
    app.run(debug=True)