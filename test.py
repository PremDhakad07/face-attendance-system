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
import json

# --- MySQL Database Configuration ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'vitbpl2028',
    'database': 'project'
}

# Time in seconds to wait before marking attendance for the same person again
# 12 hours * 60 minutes/hour * 60 seconds/minute = 43200
MIN_TIME_BETWEEN_ATTENDANCE = 43200

# Tolerance for face recognition. Lower is stricter. 0.45 is a good balance.
FACE_RECOGNITION_TOLERANCE = 0.45

# --- Multithreading Global Variables ---
detected_faces_data = []
detected_faces_lock = threading.Lock()
stop_threads = threading.Event()
processing_queue = Queue(maxsize=1)

# --- Database Helper Functions ---
def get_db_connection():
    """Establishes and returns a MySQL database connection."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as err:
        print(f" Database connection error: {err}")
        return None

def load_known_faces():
    """
    Loads face embeddings, registration numbers, and names from the MySQL database.
    """
    known_face_encodings = []
    known_student_ids = []
    known_student_names = []
    
    conn = get_db_connection()
    if not conn:
        print("Error: Could not connect to database to load known faces.")
        return [], [], []

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT registration_number, name, face_embedding FROM students WHERE face_embedding IS NOT NULL")
        results = cursor.fetchall()
        
        for reg_no, name, embedding_blob in results:
            known_student_ids.append(reg_no)
            known_student_names.append(name)
            embedding_array = np.frombuffer(embedding_blob, dtype=np.float64)
            known_face_encodings.append(embedding_array)
            
        print(f"Loaded {len(known_student_ids)} student faces from the database.")
        
    except mysql.connector.Error as err:
        print(f"Error loading faces from database: {err}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
    
    return known_face_encodings, known_student_ids, known_student_names

# --- Fingerprint Helper Functions (Simulated) ---
def enroll_fingerprint():
    """
    (SIMULATED) Captures a fingerprint template.
    A real system would use a hardware SDK to read the fingerprint sensor.
    """
    print("\n[Fingerprint Enrollment] Please place your finger on the scanner...")
    
    time.sleep(3) # Simulate the time it takes to scan
    
    # Simulate a fingerprint template as a dictionary of features
    dummy_template = {
        'minutiae': np.random.randint(10, 50, size=5).tolist(),
        'ridges': np.random.rand(5).tolist()
    }
    
    print("Fingerprint captured successfully.")
    # Return as a JSON string to store in the database blob
    return json.dumps(dummy_template).encode('utf-8')

def compare_fingerprints(scanned_template_data, known_template_data):
    """
    (SIMULATED) Compares a new scan to a known template.
    A real system would use a dedicated matching algorithm from the SDK.
    """
    try:
        scanned_template = json.loads(scanned_template_data)
        known_template = json.loads(known_template_data)
        
        # A simple, simulated comparison: check if all features match
        # In a real system, a tolerance or score would be used
        if (scanned_template['minutiae'] == known_template['minutiae'] and
            np.allclose(scanned_template['ridges'], known_template['ridges'], atol=0.1)):
            return True
        return False
    except Exception as e:
        print(f"Error comparing fingerprints: {e}")
        return False

def load_known_fingerprints():
    """Loads fingerprint templates and student data from the database."""
    conn = get_db_connection()
    if not conn: return []
    
    known_fingerprints = []
    
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT registration_number, name, fingerprint_template FROM students WHERE fingerprint_template IS NOT NULL")
        known_fingerprints = cursor.fetchall()
            
    except Exception as err:
        print(f"Error loading fingerprint data: {err}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
            
    return known_fingerprints

# --- Face Capture and Embedding Helper ---
def capture_face_and_get_embedding():
    """
    Captures a face from the webcam, allowing the user to position themselves
    before saving the image and generating the embedding.
    """
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print(" Error: Camera failed to open. Make sure it's not in use by another application.")
        return None, None

    print("\n Please position your face clearly in the center of the camera. Press 's' to save the image, or 'q' to cancel.")
    
    embedding = None
    captured_image_frame = None
    
    while True:
        ret, frame = cap.read()
        if not ret:
            print(" Error: Failed to capture frame from camera.")
            break

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame)
        
        if len(face_locations) == 1:
            top, right, bottom, left = face_locations[0]
            cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
            cv2.putText(frame, "Press 's' to save", (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        elif len(face_locations) > 1:
            cv2.putText(frame, "Multiple faces detected!", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        else:
            cv2.putText(frame, "No face detected.", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        
        cv2.imshow('Capture Face', frame)
        
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('s'):
            if len(face_locations) == 1:
                face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
                embedding = face_encodings[0]
                captured_image_frame = frame.copy()
                print(" Face detected and embedding captured. Image saved.")
                break
            else:
                print(" No single face detected. Please position your face and try again.")
        
        if key == ord('q'):
            print("Capture cancelled by user.")
            break

    cap.release()
    cv2.destroyAllWindows()
    return embedding, captured_image_frame

# --- OpenCV Text Drawing Helper ---
def draw_text_with_outline(image, text, position, font, scale, color, thickness):
    """Draws text with a black outline for better visibility."""
    cv2.putText(image, text, position, font, scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
    cv2.putText(image, text, position, font, scale, color, thickness, cv2.LINE_AA)

# --- Student Management Functions ---
def add_student():
    """Adds a new student with both face and fingerprint data."""
    print("\n--- Add/Update Student ---")
    
    reg_no = input("Enter Registration Number: ")
    name = input("Enter Full Name: ")
    major = input("Enter Major (e.g., Computer Science): ")
    year_str = input("Enter Year (e.g., 2024): ")
    starting_year_str = input("Enter Starting Year (e.g., 2022): ")

    if not all([reg_no, name, major, year_str, starting_year_str]):
        print("All fields are required. Aborting.")
        return

    try:
        year = int(year_str)
        starting_year = int(starting_year_str)
    except ValueError:
        print("Year and Starting Year must be numbers. Aborting.")
        return

    conn = get_db_connection()
    if not conn: return
    
    try:
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM students WHERE registration_number = %s", (reg_no,))
        if cursor.fetchone():
            print(f"\nError: The registration number '{reg_no}' is already registered.")
            return

        embedding, captured_image_frame = capture_face_and_get_embedding()
        if embedding is None:
            print("Failed to capture a face. Aborting student addition.")
            return
            
        fingerprint_template = enroll_fingerprint()
        if fingerprint_template is None:
            print("Failed to capture a fingerprint. Aborting student addition.")
            return
            
        known_face_encodings, known_student_ids, known_student_names = load_known_faces()
        
        if known_face_encodings:
            face_distances = face_recognition.face_distance(known_face_encodings, embedding)
            best_match_index = np.argmin(face_distances)
            
            if face_distances[best_match_index] < FACE_RECOGNITION_TOLERANCE:
                registered_name = known_student_names[best_match_index]
                registered_reg_no = known_student_ids[best_match_index]
                print(f"\nError: This face is already registered to '{registered_name}' (Reg No: {registered_reg_no}).")
                print("Aborting new student addition.")
                return

        known_fingerprints = load_known_fingerprints()
        if known_fingerprints:
            for student in known_fingerprints:
                if compare_fingerprints(fingerprint_template, student['fingerprint_template']):
                    print(f"\nError: This fingerprint is already registered to '{student['name']}' (Reg No: {student['registration_number']}).")
                    print("Aborting new student addition.")
                    return

        faces_dir = "faces"
        if not os.path.exists(faces_dir):
            os.makedirs(faces_dir)
        
        file_path = os.path.join(faces_dir, f"{reg_no}_{name.replace(' ', '_')}.jpg")
        cv2.imwrite(file_path, captured_image_frame)
        print(f"Captured face saved as '{file_path}'")
        
        sql = """
            INSERT INTO students (registration_number, name, face_embedding, fingerprint_template, major, year, starting_year, total_attendance)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 0)
        """
        cursor.execute(sql, (reg_no, name, embedding.tobytes(), fingerprint_template, major, year, starting_year))
        conn.commit()
        print(f"Student '{name}' (Reg No: {reg_no}) added successfully.")

    except mysql.connector.Error as err:
        print(f"Database error: {err}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def edit_student():
    """Edits an existing student's details."""
    print("\n--- Edit Student ---")
    reg_no = input("Enter Registration Number of the student to edit: ")
    
    conn = get_db_connection()
    if not conn: return

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM students WHERE registration_number = %s", (reg_no,))
        student_data = cursor.fetchone()

        if not student_data:
            print(f" Student with registration number '{reg_no}' not found.")
            return

        print("\nCurrent student details:")
        print(f" - Name: {student_data['name']}")
        print(f" - Major: {student_data['major']}")
        
        new_name = input(f"Enter new Name ({student_data['name']}): ") or student_data['name']
        new_major = input(f"Enter new Major ({student_data['major']}): ") or student_data['major']
        
        new_year_str = input(f"Enter new Year ({student_data['year']}): ")
        new_year = int(new_year_str) if new_year_str else student_data['year']
        
        new_starting_year_str = input(f"Enter new Starting Year ({student_data['starting_year']}): ")
        new_starting_year = int(new_starting_year_str) if new_starting_year_str else student_data['starting_year']

        sql = """
            UPDATE students SET name = %s, major = %s, year = %s, starting_year = %s
            WHERE registration_number = %s
        """
        cursor.execute(sql, (new_name, new_major, new_year, new_starting_year, reg_no))
        conn.commit()
        print(f"\n Student '{new_name}' (Reg No: {reg_no}) details updated successfully.")

    except ValueError:
        print(" Year and Starting Year must be numbers if provided. Aborting.")
    except mysql.connector.Error as err:
        print(f" Database error: {err}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def delete_student():
    """Deletes a student record and associated files."""
    print("\n--- Delete Student ---")
    reg_no = input("Enter the registration number of the student to delete: ")

    conn = get_db_connection()
    if not conn: return
    
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM students WHERE registration_number = %s", (reg_no,))
        result = cursor.fetchone()
        if not result:
            print(f" Student with registration number '{reg_no}' not found.")
            return

        student_name = result[0]
        confirmation = input(f"Are you sure you want to remove '{student_name}' (Reg No: {reg_no})? (yes/no): ").lower()
        if confirmation != 'yes':
            print("Operation cancelled.")
            return

        cursor.execute("DELETE FROM attendance WHERE student_reg_no = %s", (reg_no,))
        print(f" Deleted {cursor.rowcount} attendance record(s).")
        
        cursor.execute("DELETE FROM students WHERE registration_number = %s", (reg_no,))
        print(f" Deleted student record.")

        face_files = glob.glob(f"faces/{reg_no}_*.jpg")
        if face_files:
            for file_path in face_files:
                os.remove(file_path)
                print(f" Deleted face image file: {file_path}")

        conn.commit()
        print(f" Student '{student_name}' completely removed.")

    except mysql.connector.Error as err:
        print(f" Database error: {err}")
        conn.rollback()
    except OSError as err:
        print(f" File system error: {err}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def show_registered_students():
    """Fetches and displays a list of all registered students from the database."""
    print("\n--- All Registered Students ---")
    conn = get_db_connection()
    if not conn: return

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT registration_number, name, major, year, starting_year, total_attendance FROM students ORDER BY registration_number")
        students = cursor.fetchall()

        if not students:
            print("No students are currently registered.")
            return

        s_no = 1
        print("-" * 97)
        print(f"{'S.No':<5} {'Reg No':<15} {'Name':<25} {'Major':<20} {'Year':<5} {'Start':<5} {'Attendance':<10}")
        print("-" * 97)
        for student in students:
            print(
                f"{s_no:<5} "
                f"{student['registration_number']:<15} "
                f"{student['name']:<25} "
                f"{student['major']:<20} "
                f"{student['year']:<5} "
                f"{student['starting_year']:<5} "
                f"{student['total_attendance']:<10}"
            )
            s_no += 1
        print("-" * 97)

    except mysql.connector.Error as err:
        print(f" Database error: {err}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

# --- Attendance System Core Function ---
def mark_attendance(student_id):
    """
    Marks attendance for a given student ID in the database.
    Returns the attendance status string.
    """
    try:
        conn = get_db_connection()
        if not conn: return "DB Error"
        cursor = conn.cursor()
        
        cursor.execute("SELECT name, last_attendance_time FROM students WHERE registration_number = %s", (student_id,))
        result = cursor.fetchone()
        
        if not result:
            return "Not Registered"
            
        student_name, last_time_str = result
        
        can_mark = True
        if last_time_str:
            last_time = datetime.strptime(str(last_time_str), "%Y-%m-%d %H:%M:%S")
            seconds_elapsed = (datetime.now() - last_time).total_seconds()
            if seconds_elapsed < MIN_TIME_BETWEEN_ATTENDANCE:
                can_mark = False
        
        if can_mark:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            update_sql = "UPDATE students SET total_attendance = total_attendance + 1, last_attendance_time = %s WHERE registration_number = %s"
            cursor.execute(update_sql, (current_time, student_id))
            
            insert_sql = "INSERT INTO attendance (student_reg_no, check_in_time) VALUES (%s, %s)"
            cursor.execute(insert_sql, (student_id, current_time))
            
            conn.commit()
            print(f" Attendance marked for student: {student_id}")
            return "Marked"
        else:
            return "Already Marked"
            
    except mysql.connector.Error as err:
        print(f" Error marking attendance: {err}")
        return "DB Error"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

# --- Frame Processing Worker Thread (for Face Recognition) ---
def face_processing_worker(known_face_encodings, known_student_ids, known_student_names):
    """
    A separate thread to perform the CPU-intensive face recognition tasks.
    """
    global detected_faces_data
    while not stop_threads.is_set():
        try:
            frame = processing_queue.get(timeout=1)
            
            small_frame = cv2.resize(frame, (0, 0), None, 0.25, 0.25)
            rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
            
            face_locations = face_recognition.face_locations(rgb_small_frame)
            face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)
            
            current_frame_data = []
            for face_encoding, face_location in zip(face_encodings, face_locations):
                display_name = "Unknown"
                display_reg_no = ""
                display_status = "Not Registered"
                frame_color = (0, 0, 255)
                
                face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
                
                if face_distances.size > 0:
                    best_match_index = np.argmin(face_distances)
                    if face_distances[best_match_index] < FACE_RECOGNITION_TOLERANCE:
                        student_id = known_student_ids[best_match_index]
                        student_name = known_student_names[best_match_index]
                        
                        display_name = student_name
                        display_reg_no = f"Reg No: {student_id}"
                        display_status = mark_attendance(student_id)
                        
                        if display_status == "Marked":
                            frame_color = (0, 255, 0)
                        elif display_status == "Already Marked":
                            frame_color = (0, 255, 255)
                            
                current_frame_data.append({
                    'location': face_location,
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
            print(f"Error in face processing thread: {e}")
            time.sleep(1)

def run_face_attendance_system():
    """Runs the real-time face recognition and attendance marking system."""
    global detected_faces_data

    print("\n--- Starting Face Recognition Attendance System ---")
    print("Press 'q' to quit the attendance system.")

    known_face_encodings, known_student_ids, known_student_names = load_known_faces()

    if not known_face_encodings:
        print("No known faces found. Please add students first.")
        time.sleep(3)
        return
        
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print(" Error: Camera failed to open.")
        time.sleep(3)
        return
        
    cap.set(3, 640)
    cap.set(4, 480)

    cv2.namedWindow('Face Recognition Attendance', cv2.WINDOW_NORMAL)
    
    stop_threads.clear()
    worker_thread = threading.Thread(target=face_processing_worker, args=(known_face_encodings, known_student_ids, known_student_names))
    worker_thread.daemon = True
    worker_thread.start()

    frame_count = 0
    while True:
        success, frame = cap.read()
        if not success:
            break
        
        frame_count += 1
        if frame_count % 10 == 0:
            try:
                while not processing_queue.empty():
                    processing_queue.get_nowait()
                processing_queue.put_nowait(frame.copy())
            except Exception:
                pass

        with detected_faces_lock:
            current_detected_faces = detected_faces_data.copy()

        if current_detected_faces:
            for face_data in current_detected_faces:
                y1, x2, y2, x1 = [v * 4 for v in face_data['location']]
                
                cv2.rectangle(frame, (x1, y1), (x2, y2), face_data['color'], 2)
                
                font = cv2.FONT_HERSHEY_DUPLEX
                name_font_scale = 0.9 
                reg_status_font_scale = 0.7 
                font_thickness = 2 

                name_text = face_data['name']
                reg_text = face_data['reg_no']
                status_text = face_data['status']

                (name_text_w, name_text_h), _ = cv2.getTextSize(name_text, font, name_font_scale, font_thickness)
                (reg_text_w, reg_text_h), _ = cv2.getTextSize(reg_text, font, reg_status_font_scale, font_thickness)
                (status_text_w, status_text_h), _ = cv2.getTextSize(status_text, font, reg_status_font_scale, font_thickness)

                template_height = name_text_h + reg_text_h + status_text_h + 20
                template_y_start = y2 + 2
                template_y_end = template_y_start + template_height
                
                if template_y_end > frame.shape[0]:
                    template_y_end = frame.shape[0]
                    template_y_start = template_y_end - template_height

                cv2.rectangle(frame, (x1, template_y_start), (x2, template_y_end), (255, 0, 0), cv2.FILLED)
                
                draw_text_with_outline(frame, name_text, (x1, template_y_start + name_text_h + 5), font, name_font_scale, (255, 255, 255), font_thickness)
                draw_text_with_outline(frame, reg_text, (x1, template_y_start + name_text_h + reg_text_h + 10), font, reg_status_font_scale, (255, 255, 255), font_thickness)
                draw_text_with_outline(frame, status_text, (x1, template_y_start + name_text_h + reg_text_h + status_text_h + 15), font, reg_status_font_scale, (255, 255, 255), font_thickness)

        cv2.imshow('Face Recognition Attendance', frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    stop_threads.set()
    worker_thread.join()
    cap.release()
    cv2.destroyAllWindows()
    print("Real-time Attendance System stopped.")

# --- New Function: Fingerprint Attendance System ---
def run_fingerprint_attendance_system():
    """Runs the fingerprint-based attendance marking system."""
    print("\n--- Starting Fingerprint Attendance System ---")
    print("Place your finger on the scanner. Press 'q' to quit.")
    
    known_fingerprints = load_known_fingerprints()
    if not known_fingerprints:
        print("No fingerprints registered. Please add students first.")
        return
        
    while True:
        try:
            scanned_template_data = enroll_fingerprint()
            
            match_found = False
            for student in known_fingerprints:
                if compare_fingerprints(scanned_template_data, student['fingerprint_template']):
                    reg_no = student['registration_number']
                    name = student['name']
                    status = mark_attendance(reg_no)
                    print(f"Fingerprint matched! Student: {name} | Status: {status}")
                    match_found = True
                    break
            
            if not match_found:
                print("Fingerprint not recognized.")
            
            print("\nReady for next scan...")
            time.sleep(2)

        except KeyboardInterrupt:
            print("Fingerprint attendance stopped by user.")
            break
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cv2.destroyAllWindows()
    print("Fingerprint Attendance System stopped.")

# --- Main Application Menu ---
def main_app_menu():
    """Displays the main application menu and handles user choices."""
    while True:
        print("\n\n--- Integrated Attendance System ---")
        print("1. Manage Students (Add/Edit/Delete/View)")
        print("2. Start Face Recognition Attendance")
        print("3. Start Fingerprint Attendance")
        print("4. Exit Application")
        
        choice = input("Enter your choice (1-4): ")
        
        if choice == '1':
            student_manager_menu()
        elif choice == '2':
            run_face_attendance_system()
        elif choice == '3':
            run_fingerprint_attendance_system()
        elif choice == '4':
            print("Exiting Integrated Attendance System. Goodbye!")
            break
        else:
            print(" Invalid choice. Please enter a number from 1 to 4.")

def student_manager_menu():
    """Displays the student management menu."""
    while True:
        print("\n--- Student Management Menu ---")
        print("1. Add/Update Student")
        print("2. Edit Student Details")
        print("3. Delete Student")
        print("4. Show All Registered Students")
        print("5. Back to Main Menu")
        
        choice = input("Enter your choice (1-5): ")
        
        if choice == '1':
            add_student()
        elif choice == '2':
            edit_student()
        elif choice == '3':
            delete_student()
        elif choice == '4':
            show_registered_students()
        elif choice == '5':
            print("Returning to Main Menu.")
            break
        else:
            print(" Invalid choice. Please enter a number from 1 to 5.")

if __name__ == "__main__":
    main_app_menu()