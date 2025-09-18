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

# Tolerance for face recognition. Lower is stricter. 0.6 is the default, 0.4 is a very good balance.
FACE_RECOGNITION_TOLERANCE = 0.45

# --- Multithreading Global Variables ---
detected_faces_data = []
detected_faces_lock = threading.Lock()
stop_threads = threading.Event()
# Queue to hold frames for the worker thread to process
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
        cursor.execute("SELECT registration_number, name, face_embedding FROM students")
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
    """Adds a new student or updates an existing one."""
    print("\n--- Add/Update Student ---")
    
    # 1. Ask for all student details first
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
        
        # 2. Check if the registration number already exists
        cursor.execute("SELECT name FROM students WHERE registration_number = %s", (reg_no,))
        existing_student = cursor.fetchone()
        
        if existing_student:
            print(f"\nError: The registration number '{reg_no}' is already registered to '{existing_student[0]}'.")
            print("Please choose a different registration number or use the 'Edit Student' option.")
            return

        # 3. Capture the student's face
        embedding, captured_image_frame = capture_face_and_get_embedding()
        if embedding is None:
            print("Failed to capture a face. Aborting student addition.")
            return
            
        # 4. Check if the captured face already exists in the database
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

        # 5. If both checks pass, save the new student's data
        faces_dir = "faces"
        if not os.path.exists(faces_dir):
            os.makedirs(faces_dir)
        
        file_path = os.path.join(faces_dir, f"{reg_no}_{name.replace(' ', '_')}.jpg")
        cv2.imwrite(file_path, captured_image_frame)
        print(f"Captured face saved as '{file_path}'")
        
        sql = """
            INSERT INTO students (registration_number, name, face_embedding, major, year, starting_year, total_attendance)
            VALUES (%s, %s, %s, %s, %s, %s, 0)
        """
        cursor.execute(sql, (reg_no, name, embedding.tobytes(), major, year, starting_year))
        conn.commit()
        print(f"Student '{name}' (Reg No: {reg_no}) added successfully.")

    except mysql.connector.Error as err:
        print(f"Database error: {err}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def edit_student():
    """Edits an existing student's details, including the registration number."""
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
        for key, value in student_data.items():
            print(f"   - {key}: {value}")

        print("\nPress Enter to keep the current value. Enter a new value to update.")
        
        # --- Get new values from user ---
        new_reg_no = input(f"Enter new Registration Number ({student_data['registration_number']}): ") or student_data['registration_number']
        new_name = input(f"Enter new Name ({student_data['name']}): ") or student_data['name']
        new_major = input(f"Enter new Major ({student_data['major']}): ") or student_data['major']
        
        new_year_str = input(f"Enter new Year ({student_data['year']}): ")
        new_year = int(new_year_str) if new_year_str else student_data['year']
        
        new_starting_year_str = input(f"Enter new Starting Year ({student_data['starting_year']}): ")
        new_starting_year = int(new_starting_year_str) if new_starting_year_str else student_data['starting_year']

        # --- Handle Registration Number and Name Change ---
        old_face_file = glob.glob(f"faces/{reg_no}_*.jpg")
        if new_reg_no != reg_no:
            # Check if the new registration number is already taken by a DIFFERENT student
            cursor.execute("SELECT registration_number FROM students WHERE registration_number = %s AND registration_number != %s", (new_reg_no, reg_no))
            if cursor.fetchone():
                print(f"\nError: The new registration number '{new_reg_no}' is already taken. Aborting.")
                return

            # Update attendance table with the new registration number
            cursor.execute("UPDATE attendance SET student_reg_no = %s WHERE student_reg_no = %s", (new_reg_no, reg_no))
            print(f" Updated {cursor.rowcount} attendance record(s) to new Reg No: {new_reg_no}")

            # Rename the corresponding face file
            if old_face_file:
                old_path = old_face_file[0]
                new_path = os.path.join("faces", f"{new_reg_no}_{new_name.replace(' ', '_')}.jpg")
                os.rename(old_path, new_path)
                print(f" Renamed face file from '{os.path.basename(old_path)}' to '{os.path.basename(new_path)}'")
            else:
                print(" Warning: No corresponding face image file found. This may be an error.")
        else: # Registration number did not change, but name might have
            if old_face_file and new_name != student_data['name']:
                old_path = old_face_file[0]
                new_path = os.path.join("faces", f"{new_reg_no}_{new_name.replace(' ', '_')}.jpg")
                os.rename(old_path, new_path)
                print(f" Renamed face file from '{os.path.basename(old_path)}' to '{os.path.basename(new_path)}'")


        # --- Update Student details in the database ---
        sql = """
            UPDATE students SET registration_number = %s, name = %s, major = %s, year = %s, starting_year = %s
            WHERE registration_number = %s
        """
        cursor.execute(sql, (new_reg_no, new_name, new_major, new_year, new_starting_year, reg_no))
        conn.commit()
        print(f"\n Student '{new_name}' (Reg No: {new_reg_no}) details updated successfully.")

    except ValueError:
        print(" Year and Starting Year must be numbers if provided. Aborting.")
    except mysql.connector.Error as err:
        print(f" Database error: {err}")
    except OSError as err:
        print(f" File system error: {err}")
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
        else:
            print(" Warning: No corresponding face image file found in 'faces' folder.")

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

# --- Frame Processing Worker Thread ---
def face_processing_worker(known_face_encodings, known_student_ids, known_student_names):
    """
    A separate thread to perform the CPU-intensive face recognition tasks.
    """
    global detected_faces_data
    while not stop_threads.is_set():
        try:
            # Get the latest frame from the queue, blocking until one is available
            frame = processing_queue.get(timeout=1)
            
            # --- Face Recognition Logic ---
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
            # No frame in the queue after 1 second, just continue loop
            continue
        except Exception as e:
            print(f"Error in face processing thread: {e}")
            time.sleep(1) # Wait before retrying

def run_attendance_system():
    """Runs the real-time face recognition and attendance marking system."""
    global detected_faces_data

    print("\n--- Starting Real-time Attendance System ---")
    print("Press 'q' to quit the attendance system.")

    known_face_encodings, known_student_ids, known_student_names = load_known_faces()

    if not known_face_encodings:
        print("No known faces found in the database. Please add students first using the 'Manage Students' option.")
        time.sleep(3)
        return
        
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print(" Error: Camera failed to open. Make sure it's not in use by another application.")
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
            print("Camera failed to open during attendance tracking.")
            break
        
        # Main thread's job is just to display the frame and, at intervals,
        # put a frame in the queue for the worker to process.
        frame_count += 1
        if frame_count % 10 == 0: # Process one in every 10 frames for better performance
            try:
                # Clear the queue and put the newest frame
                while not processing_queue.empty():
                    processing_queue.get_nowait()
                processing_queue.put_nowait(frame.copy())
            except Exception:
                pass # Queue is full, just skip this frame

        # Use a lock to safely access the shared data from the worker thread
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

# --- Main Application Menu ---
def main_app_menu():
    """Displays the main application menu and handles user choices."""
    while True:
        print("\n\n--- Integrated Attendance System ---")
        print("1. Manage Students (Add/Edit/Delete/View)")
        print("2. Start Real-time Attendance Tracking")
        print("3. Exit Application")
        
        choice = input("Enter your choice (1-3): ")
        
        if choice == '1':
            student_manager_menu()
        elif choice == '2':
            run_attendance_system()
        elif choice == '3':
            print("Exiting Integrated Attendance System. Goodbye!")
            break
        else:
            print(" Invalid choice. Please enter a number from 1 to 3.")

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