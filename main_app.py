import os
import cv2
import face_recognition
import numpy as np
import mysql.connector
import glob
import hashlib
import time
from datetime import datetime, timedelta
from flask import Flask, render_template, Response, request, redirect, url_for, session, jsonify
import webbrowser
import base64
import sys
import psutil
import signal
import subprocess
import csv
import io
import json

# --- MySQL Database Configuration ---
DB_CONFIG = {
    'host': os.environ.get('MYSQL_HOST'),
    'user': os.environ.get('MYSQL_USER'),
    'password': os.environ.get('MYSQL_PASSWORD'),
    'database': os.environ.get('MYSQL_DATABASE')
}

# --- Teacher Password Configuration ---
# The hash for the password 'vitbpl'
TEACHER_PASSWORD_HASH = '38c2f17ffe9cc7c7e78e962581b0e49b178f129b4e9af1a79b18d440c0338306'

# Time in seconds to wait before marking attendance for the same person again
MIN_TIME_BETWEEN_ATTENDANCE = 43200

# The tolerance for face recognition. Lower is stricter.
FACE_RECOGNITION_TOLERANCE = 0.6

app = Flask(__name__)
app.secret_key = 'your_super_secret_key'

# Add this line to increase the maximum request size to 60MB
app.config['MAX_CONTENT_LENGTH'] = 60 * 1024 * 1024

# Dictionary to store known faces and their encodings
known_faces_data = {} # Stores {'reg_no': {'embedding': np.array, 'name': 'student name', 'last_marked': datetime}}

def get_db_connection():
    """
    Establishes a connection to the MySQL database.
    Prompts the user for credentials only once if environment variables are not set.
    """
    global DB_CONFIG
    
    # Check if all required credentials are in the DB_CONFIG dictionary
    required_keys = ['host', 'user', 'password', 'database']
    missing_keys = [key for key in required_keys if not DB_CONFIG.get(key)]

    if missing_keys:
        print("-----------------------------------------------------")
        print("Database credentials are not set.")
        print("Please provide them now:")
        print("-----------------------------------------------------")
        try:
            for key in missing_keys:
                value = input(f"Enter a value for {key}: ")
                DB_CONFIG[key] = value
        except (KeyboardInterrupt, SystemExit):
            print("\nSetup cancelled. Exiting.")
            sys.exit(0)
            
    # Re-check for missing values after user input
    re_check_missing_keys = [key for key in required_keys if not DB_CONFIG.get(key)]
    if re_check_missing_keys:
        print("\nDatabase credentials are still missing. Exiting.")
        sys.exit(1)

    try:
        # Use the DB_CONFIG dictionary to connect
        return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as err:
        print(f"Database connection error: {err}")
        print("Please check your database credentials and ensure the MySQL server is running.")
        return None

def load_known_faces():
    """Loads all student data and face embeddings from the database into memory."""
    global known_faces_data
    known_faces_data.clear()
    conn = get_db_connection()
    if not conn:
        print("Could not connect to database to load faces.")
        return
    
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT registration_number, name, face_embedding, last_attendance_time FROM students")
        results = cursor.fetchall()
        
        for reg_no, name, embedding_blob, last_time in results:
            try:
                # Convert the blob back to a numpy array
                embedding_array = np.frombuffer(embedding_blob, dtype=np.float64)
                known_faces_data[reg_no] = {
                    'name': name,
                    'embedding': embedding_array,
                    'last_marked': last_time
                }
            except Exception as e:
                print(f"Error processing embedding for {reg_no}: {e}")
                continue
        
        print(f"Loaded {len(known_faces_data)} student faces from the database.")
    except mysql.connector.Error as err:
        print(f"Error loading faces from database: {err}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def mark_attendance(reg_no, current_time):
    """
    Marks attendance for a student by updating the database.
    """
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        
        # Update the student's total attendance and last_attendance_time
        sql_update_student = "UPDATE students SET total_attendance = total_attendance + 1, last_attendance_time = %s WHERE registration_number = %s"
        cursor.execute(sql_update_student, (current_time, reg_no))
        
        # Insert a new attendance log record
        sql_insert_log = "INSERT INTO attendance_log (registration_number, timestamp) VALUES (%s, %s)"
        cursor.execute(sql_insert_log, (reg_no, current_time))
        
        conn.commit()
        print(f"Attendance marked for {known_faces_data[reg_no]['name']} ({reg_no})")
        
    except mysql.connector.Error as err:
        print(f"Error updating attendance: {err}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

# Initial load of known faces on startup
print("Loading known faces...")
load_known_faces()

# --- Utility Functions ---
def generate_frames():
    camera = cv2.VideoCapture(0)
    if not camera.isOpened():
        print("Error: Could not open camera.")
        return

    # Pre-calculate a list of known face embeddings for faster comparison
    known_face_embeddings = [data['embedding'] for data in known_faces_data.values()]
    known_student_ids = list(known_faces_data.keys())
    
    frame_counter = 0
    frame_skip_rate = 3
    
    while True:
        success, frame = camera.read()
        if not success:
            break
        
        if frame_counter % frame_skip_rate == 0:
            small_frame = cv2.resize(frame, (0, 0), fx=0.2, fy=0.2)
            frame_rgb = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(frame_rgb)
            face_encodings = face_recognition.face_encodings(frame_rgb, face_locations)

            for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
                top *= 5
                right *= 5
                bottom *= 5
                left *= 5
                
                name = "Unknown"
                
                if known_face_embeddings:
                    matches = face_recognition.compare_faces(known_face_embeddings, face_encoding, tolerance=FACE_RECOGNITION_TOLERANCE)
                    
                    if True in matches:
                        matched_index = matches.index(True)
                        matched_reg_no = known_student_ids[matched_index]
                        
                        student_info = known_faces_data.get(matched_reg_no)
                        if student_info:
                            name = student_info['name']
                            now = datetime.now()
                            
                            # Check the last marked time from the in-memory cache
                            last_marked_time = student_info.get('last_marked')
                            
                            if not last_marked_time or (now - last_marked_time).total_seconds() > MIN_TIME_BETWEEN_ATTENDANCE:
                                # Update the in-memory cache immediately
                                student_info['last_marked'] = now
                                # Call the database update function
                                mark_attendance(matched_reg_no, now)

                # Draw a box around the face
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                # Draw a label with the name
                cv2.rectangle(frame, (left, bottom - 35), (right, bottom), (0, 255, 0), cv2.FILLED)
                font = cv2.FONT_HERSHEY_DUPLEX
                cv2.putText(frame, name, (left + 6, bottom - 6), font, 1.0, (255, 255, 255), 1)

        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    
    # Ensure camera is released when the loop breaks
    camera.release()
    print("Camera released.")

# --- Routes ---
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
        return "Database connection error. Please ensure MySQL is running and credentials are correct.", 500

    students = []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT registration_number, name, major, year, starting_year, total_attendance FROM students")
        students = cursor.fetchall()
    except mysql.connector.Error as err:
        print(f"Error fetching students: {err}")
        return f"An error occurred while fetching student data: {err}", 500
    finally:
        if conn and conn.is_connected():
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
        
        image_data = None
        img = None
        
        # Check for image data from camera first
        if 'camera_image_data' in request.form and request.form['camera_image_data']:
            image_data = request.form['camera_image_data']
            # Decode the image from base64
            try:
                header, encoded_data = image_data.split(',', 1)
                image_bytes = base64.b64decode(encoded_data)
                np_arr = np.frombuffer(image_bytes, np.uint8)
                img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            except Exception as e:
                print(f"Error decoding camera image data: {e}")
                return jsonify({'success': False, 'message': 'Failed to decode camera image data. Please try again.'}), 400
        # Then check for file upload
        elif 'face_image' in request.files and request.files['face_image'].filename != '':
            file = request.files['face_image']
            try:
                img = cv2.imdecode(np.frombuffer(file.read(), np.uint8), cv2.IMREAD_COLOR)
            except Exception as e:
                print(f"Error decoding uploaded image file: {e}")
                return jsonify({'success': False, 'message': 'Failed to decode uploaded image. Please ensure the file is a valid image.'}), 400
        else:
            return jsonify({'success': False, 'message': 'No image data provided. Please upload an image or capture a photo.'}), 400
        
        if img is None:
            return jsonify({'success': False, 'message': 'Failed to process image. Please ensure the image is valid.'}), 400
        
        # Find faces in the captured image
        face_locations = face_recognition.face_locations(img)
        if not face_locations:
            return jsonify({'success': False, 'message': 'No face found in the image. Please try again.'}), 400

        # Encode the face
        face_encoding = face_recognition.face_encodings(img, face_locations)[0]
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection error. Please ensure MySQL is running.'}), 500
        
        try:
            cursor = conn.cursor()
            
            # Save the face encoding and student data
            sql = "INSERT INTO students (registration_number, name, major, year, starting_year, face_embedding) VALUES (%s, %s, %s, %s, %s, %s)"
            # Convert the numpy array to bytes for storage in MySQL BLOB
            embedding_bytes = face_encoding.astype(np.float64).tobytes()
            cursor.execute(sql, (reg_no, name, major, year, starting_year, embedding_bytes))
            conn.commit()
            
            print("Student added successfully!")
            
            # After adding, reload known faces to update the in-memory cache
            load_known_faces()
            
            # Return a JSON response with a success message and redirect URL
            return jsonify({'success': True, 'message': 'Student added successfully!', 'redirect_url': url_for('teacher_menu')})
            
        except mysql.connector.Error as err:
            if err.errno == 1062: # Duplicate entry error
                return jsonify({'success': False, 'message': f"Error: Registration number {reg_no} already exists."}), 409
            else:
                print(f"Database error: {err}")
                return jsonify({'success': False, 'message': f"An unexpected error occurred: {err}"}), 500
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
                
    current_year = datetime.now().year
    return render_template('add_student.html', current_year=current_year)

@app.route('/edit_student/<reg_no>', methods=['GET', 'POST'])
def edit_student(reg_no):
    if not session.get('logged_in'):
        return redirect(url_for('teacher_login'))

    conn = get_db_connection()
    if not conn:
        return "Database connection error. Please ensure MySQL is running.", 500

    student = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM students WHERE registration_number = %s", (reg_no,))
        student = cursor.fetchone()
    except mysql.connector.Error as err:
        print(f"Error fetching student data: {err}")
        return f"An error occurred while fetching student data: {err}", 500
    finally:
        if conn and conn.is_connected():
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
            return "Database connection error. Please ensure MySQL is running.", 500
        
        try:
            cursor_update = conn_update.cursor()
            sql = "UPDATE students SET name = %s, major = %s, year = %s, starting_year = %s WHERE registration_number = %s"
            cursor_update.execute(sql, (name, major, year, starting_year, reg_no))
            conn_update.commit()
            return redirect(url_for('manage_students'))
        except mysql.connector.Error as err:
            print(f"Error updating student data: {err}")
            return f"An error occurred while updating the student: {err}", 500
        finally:
            if conn_update and conn_update.is_connected():
                cursor_update.close()
                conn_update.close()

    current_year = datetime.now().year
    return render_template('edit_student.html', student=student, current_year=current_year)

@app.route('/delete_student/<reg_no>', methods=['POST'])
def delete_student(reg_no):
    if not session.get('logged_in'):
        return redirect(url_for('teacher_login'))

    conn = get_db_connection()
    if not conn:
        return "Database connection error. Please ensure MySQL is running.", 500

    try:
        cursor = conn.cursor()
        
        # First, delete associated records in the attendance_log table
        cursor.execute("DELETE FROM attendance_log WHERE registration_number = %s", (reg_no,))
        
        # Then, delete the student from the students table
        cursor.execute("DELETE FROM students WHERE registration_number = %s", (reg_no,))
        conn.commit()
        
        # After deleting, reload known faces to remove the entry from the in-memory cache
        load_known_faces()
        
    except mysql.connector.Error as err:
        print(f"Error deleting student: {err}")
        return f"An error occurred while deleting the student: {err}", 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

    return redirect(url_for('manage_students'))

@app.route('/attendance')
def attendance():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/get_latest_attendance')
def get_latest_attendance():
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection error.'}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        sql = """
        SELECT s.name, s.registration_number AS reg_no, al.timestamp
        FROM attendance_log al
        JOIN students s ON al.registration_number = s.registration_number
        ORDER BY al.timestamp DESC
        LIMIT 10
        """
        cursor.execute(sql)
        latest_attendance = cursor.fetchall()
        
        # Format the timestamp to a more readable string if needed
        for row in latest_attendance:
            row['timestamp'] = row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            
        return jsonify(latest_attendance)
    except mysql.connector.Error as err:
        print(f"Error fetching latest attendance log: {err}")
        return jsonify({'error': 'An error occurred fetching data.'}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/shutdown', methods=['POST'])
def shutdown():
    print("Shutting down the server...")
    
    # Send a signal to the current process
    os.kill(os.getpid(), signal.SIGINT)
    
    print("Attempting to terminate parent process...")
    
    parent_pid = os.getppid()
    try:
        parent = psutil.Process(parent_pid)
        if parent:
            parent.terminate() # Request termination
            parent.wait(timeout=3) # Wait for parent to terminate (optional timeout)
            print(f"Parent process with PID {parent_pid} terminated successfully using psutil.")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        print(f"Parent process with PID {parent_pid} not found or access denied. It may have already terminated.")
    except psutil.TimeoutExpired:
        print(f"Parent process with PID {parent_pid} did not terminate within timeout. Forcing kill.")
        try:
            parent.kill() # Force kill if terminate didn't work
            print(f"Parent process with PID {parent_pid} forcefully terminated.")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            print(f"Could not forcefully terminate parent process with PID {parent_pid}.")
    except Exception as e:
        print(f"An unexpected error occurred during termination: {e}")
        
    print("Goodbye!")
    
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
        cursor = conn.cursor(dictionary=True)
        # Fetch all student data except for the face_embedding, which is not needed for the CSV
        cursor.execute("SELECT registration_number, name, major, year, starting_year, total_attendance FROM students")
        students = cursor.fetchall()
        
        # Use a BytesIO buffer to write the CSV data to memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write the header row
        header = ['Registration Number', 'Name', 'Major', 'Year', 'Starting Year', 'Total Attendance']
        writer.writerow(header)
        
        # Write the data rows
        for student in students:
            writer.writerow([
                student['registration_number'],
                student['name'],
                student['major'],
                student['year'],
                student['starting_year'],
                student['total_attendance']
            ])
            
        # Get the string value from the buffer
        csv_data = output.getvalue()
        
        # Create a Flask Response with the CSV data
        response = Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=students_data.csv"}
        )
        return response
        
    except mysql.connector.Error as err:
        print(f"Error exporting data to CSV: {err}")
        return "An error occurred while exporting data.", 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == '__main__':
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        print("Starting Flask server and opening browser...")
        time.sleep(2)
    app.run()