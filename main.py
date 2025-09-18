import os
import cv2
import face_recognition
import numpy as np
import mysql.connector
import glob
import time
from datetime import datetime
import threading
from queue import Queue, Empty
from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import uvicorn
import webbrowser
import logging

# --- Configure Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- MySQL Database Configuration ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'vitbpl2028',
    'database': 'project'
}

MIN_TIME_BETWEEN_ATTENDANCE = 43200
FACE_RECOGNITION_TOLERANCE = 0.45

# --- Global Variables for Recognition ---
known_face_encodings = []
known_student_ids = []
known_student_names = []
attendance_log_records = {} # To prevent duplicate log entries in the UI

# --- Threading and Video Stream ---
video_stream = None
detected_faces_data = []
detected_faces_lock = threading.Lock()
stop_threads = threading.Event()
processing_queue = Queue(maxsize=1)

# --- Database Helper Functions ---
def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as err:
        logging.error(f"Database connection error: {err}")
        return None

def load_known_faces():
    global known_face_encodings, known_student_ids, known_student_names
    conn = get_db_connection()
    if not conn:
        logging.error("Could not connect to database to load known faces.")
        return
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT registration_number, name, face_embedding FROM students WHERE face_embedding IS NOT NULL")
        results = cursor.fetchall()
        known_face_encodings.clear()
        known_student_ids.clear()
        known_student_names.clear()
        for reg_no, name, embedding_blob in results:
            known_student_ids.append(reg_no)
            known_student_names.append(name)
            embedding_array = np.frombuffer(embedding_blob, dtype=np.float64)
            known_face_encodings.append(embedding_array)
        logging.info(f"Loaded {len(known_student_ids)} student faces from the database.")
    except mysql.connector.Error as err:
        logging.error(f"Error loading faces from database: {err}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def mark_attendance(student_id):
    try:
        conn = get_db_connection()
        if not conn: return {"status": "DB Error"}
        cursor = conn.cursor()
        cursor.execute("SELECT name, last_attendance_time FROM students WHERE registration_number = %s", (student_id,))
        result = cursor.fetchone()
        if not result:
            return {"status": "Not Registered"}
        student_name, last_time_str = result
        can_mark = True
        if last_time_str:
            last_time = datetime.strptime(str(last_time_str), "%Y-%m-%d %H:%M:%S")
            seconds_elapsed = (datetime.now() - last_time).total_seconds()
            if seconds_elapsed < MIN_TIME_BETWEEN_ATTENDANCE:
                can_mark = False
        if can_mark:
            current_time = datetime.now()
            current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
            update_sql = "UPDATE students SET total_attendance = total_attendance + 1, last_attendance_time = %s WHERE registration_number = %s"
            cursor.execute(update_sql, (current_time_str, student_id))
            insert_sql = "INSERT INTO attendance (student_reg_no, check_in_time) VALUES (%s, %s)"
            cursor.execute(insert_sql, (student_id, current_time_str))
            conn.commit()
            logging.info(f"Attendance marked for student: {student_id}")
            return {"status": "Marked", "name": student_name, "reg_no": student_id, "timestamp": current_time_str}
        else:
            return {"status": "Already Marked", "name": student_name, "reg_no": student_id, "timestamp": str(last_time_str)}
    except mysql.connector.Error as err:
        logging.error(f"Error marking attendance: {err}")
        return {"status": "DB Error"}
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

# --- Frame Processing Worker Thread ---
def face_processing_worker():
    global detected_faces_data, known_face_encodings, known_student_ids, known_student_names, attendance_log_records
    while not stop_threads.is_set():
        try:
            frame = processing_queue.get(timeout=1)
            small_frame = cv2.resize(frame, (0, 0), None, 0.25, 0.25)
            rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_small_frame)
            face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)
            current_frame_data = []
            
            for face_encoding, face_location in zip(face_encodings, face_locations):
                face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
                
                if face_distances.size > 0:
                    best_match_index = np.argmin(face_distances)
                    if face_distances[best_match_index] < FACE_RECOGNITION_TOLERANCE:
                        student_id = known_student_ids[best_match_index]
                        attendance_result = mark_attendance(student_id)
                        
                        if attendance_result.get("status") == "Marked":
                            log_key = f"{attendance_result['reg_no']}-{attendance_result['timestamp']}"
                            if log_key not in attendance_log_records:
                                attendance_log_records[log_key] = {
                                    "name": attendance_result['name'],
                                    "reg_no": attendance_result['reg_no'],
                                    "timestamp": attendance_result['timestamp']
                                }
                        
                        display_name = attendance_result.get('name', 'Unknown')
                        display_reg_no = f"Reg No: {student_id}"
                        display_status = attendance_result.get('status', 'Error')
                        frame_color = (0, 0, 255) # Red default
                        
                        if display_status == "Marked":
                            frame_color = (0, 255, 0) # Green
                        elif display_status == "Already Marked":
                            frame_color = (0, 255, 255) # Yellow
                        elif display_status == "Not Registered":
                            frame_color = (0, 0, 255) # Red
                            display_name = "Unknown"
                    else:
                        display_name = "Unknown"
                        display_reg_no = ""
                        display_status = "Not Registered"
                        frame_color = (0, 0, 255) # Red
                else:
                    display_name = "Unknown"
                    display_reg_no = ""
                    display_status = "Not Registered"
                    frame_color = (0, 0, 255) # Red
                    
                current_frame_data.append({
                    'location': [v * 4 for v in face_location],
                    'name': display_name,
                    'reg_no': display_reg_no,
                    'status': display_status,
                    'color': frame_color
                })
            
            with detected_faces_lock:
                detected_faces_data = current_frame_data
        
        except Empty:
            continue
        except Exception as e:
            logging.error(f"Error in face processing thread: {e}")
            time.sleep(1)

# --- FastAPI App and Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Starting up the application...")
    load_known_faces()
    yield
    logging.info("Shutting down the application...")

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    with open("static/index.html", "r") as f:
        return f.read()

@app.get("/api/latest-attendance")
async def get_latest_attendance():
    global attendance_log_records
    latest_logs = list(attendance_log_records.values())
    attendance_log_records = {} 
    return JSONResponse({"status": "success", "log": latest_logs})

# All other API endpoints from the previous response are unchanged.
# (add-student, students, start_attendance, stop_attendance, video_feed)

if __name__ == "__main__":
    try:
        if not os.path.exists("faces"):
            os.makedirs("faces")
        webbrowser.open_new_tab("http://127.0.0.1:8000")
        uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
    except Exception as e:
        logging.critical(f"Failed to start the application: {e}")