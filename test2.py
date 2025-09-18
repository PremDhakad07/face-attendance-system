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
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from PIL import Image, ImageTk

# --- MySQL Database Configuration ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'vitbpl2028',
    'database': 'project'
}

# Time in seconds to wait before marking attendance for the same person again
MIN_TIME_BETWEEN_ATTENDANCE = 43200

# Tolerance for face recognition. Lower is stricter. 0.45 is a good balance.
FACE_RECOGNITION_TOLERANCE = 0.45

# --- Global Variables for GUI and Threads ---
known_face_encodings = []
known_student_ids = []
known_student_names = []
known_fingerprints = []
detected_faces_data = []

detected_faces_lock = threading.Lock()
stop_threads = threading.Event()
processing_queue = Queue(maxsize=1)
camera_active = False

# --- Database Helper Functions ---
def get_db_connection():
    """Establishes and returns a MySQL database connection."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as err:
        print(f"Database connection error: {err}")
        return None

def load_known_data():
    """
    Loads face embeddings and fingerprint templates from the MySQL database.
    This function is called once at startup.
    """
    global known_face_encodings, known_student_ids, known_student_names, known_fingerprints
    
    conn = get_db_connection()
    if not conn:
        messagebox.showerror("Error", "Could not connect to database.")
        return
        
    try:
        cursor = conn.cursor(dictionary=True)
        # Load Face Data
        cursor.execute("SELECT registration_number, name, face_embedding FROM students WHERE face_embedding IS NOT NULL")
        face_results = cursor.fetchall()
        
        known_face_encodings.clear()
        known_student_ids.clear()
        known_student_names.clear()
        
        for row in face_results:
            known_student_ids.append(row['registration_number'])
            known_student_names.append(row['name'])
            embedding_array = np.frombuffer(row['face_embedding'], dtype=np.float64)
            known_face_encodings.append(embedding_array)
            
        # Load Fingerprint Data
        cursor.execute("SELECT registration_number, name, fingerprint_template FROM students WHERE fingerprint_template IS NOT NULL")
        known_fingerprints = cursor.fetchall()

        print(f"Loaded {len(known_student_ids)} face templates and {len(known_fingerprints)} fingerprint templates.")
        
    except mysql.connector.Error as err:
        messagebox.showerror("Database Error", f"Error loading data from database: {err}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def mark_attendance(student_id, auth_method):
    """Marks attendance for a given student ID."""
    try:
        conn = get_db_connection()
        if not conn: return "DB Error"
        cursor = conn.cursor()
        
        cursor.execute("SELECT name, last_attendance_time FROM students WHERE registration_number = %s", (student_id,))
        result = cursor.fetchone()
        
        if not result: return "Not Registered"
            
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
            
            insert_sql = "INSERT INTO attendance (student_reg_no, check_in_time, auth_method) VALUES (%s, %s, %s)"
            cursor.execute(insert_sql, (student_id, current_time, auth_method))
            
            conn.commit()
            print(f"Attendance marked for student: {student_id} via {auth_method}.")
            return "Marked"
        else:
            return "Already Marked"
            
    except mysql.connector.Error as err:
        print(f"Error marking attendance: {err}")
        return "DB Error"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

# --- Fingerprint Helper Functions (Simulated) ---
def enroll_fingerprint():
    """
    (SIMULATED) Captures a fingerprint template.
    A real system would use a hardware SDK to read the sensor.
    """
    try:
        # Simulate a fingerprint template as a dictionary of features
        dummy_template = {
            'minutiae': np.random.randint(10, 50, size=5).tolist(),
            'ridges': np.random.rand(5).tolist()
        }
        
        print("Simulated fingerprint captured successfully.")
        return json.dumps(dummy_template).encode('utf-8')
    except Exception as e:
        print(f"Simulated fingerprint enrollment error: {e}")
        return None

def compare_fingerprints(scanned_template_data, known_template_data):
    """
    (SIMULATED) Compares a new scan to a known template.
    A real system would use a dedicated matching algorithm.
    """
    try:
        scanned_template = json.loads(scanned_template_data)
        known_template = json.loads(known_template_data)
        
        # A simple, simulated comparison: check if all features match
        if (scanned_template['minutiae'] == known_template['minutiae'] and
            np.allclose(scanned_template['ridges'], known_template['ridges'], atol=0.1)):
            return True
        return False
    except Exception as e:
        print(f"Error comparing fingerprints: {e}")
        return False

# --- Face & Fingerprint Manager Functions (GUI-based) ---
class StudentManagerGUI:
    def __init__(self, master):
        self.master = master
        master.title("Student Manager")
        master.geometry("500x300")
        
        self.frame = ttk.Frame(master, padding="10")
        self.frame.pack(fill=tk.BOTH, expand=True)

        ttk.Button(self.frame, text="Add New Student", command=self.add_student_gui).pack(pady=5, fill=tk.X)
        ttk.Button(self.frame, text="Edit Student Details", command=self.edit_student_gui).pack(pady=5, fill=tk.X)
        ttk.Button(self.frame, text="Delete Student", command=self.delete_student_gui).pack(pady=5, fill=tk.X)
        ttk.Button(self.frame, text="Show All Students", command=self.show_students_gui).pack(pady=5, fill=tk.X)
        ttk.Button(self.frame, text="Exit", command=master.destroy).pack(pady=10, fill=tk.X)

    def add_student_gui(self):
        # A new Toplevel window for the form
        add_window = tk.Toplevel(self.master)
        add_window.title("Add New Student")

        reg_no_label = ttk.Label(add_window, text="Registration Number:")
        reg_no_label.pack(pady=5)
        reg_no_entry = ttk.Entry(add_window)
        reg_no_entry.pack(pady=5)
        
        name_label = ttk.Label(add_window, text="Full Name:")
        name_label.pack(pady=5)
        name_entry = ttk.Entry(add_window)
        name_entry.pack(pady=5)
        
        major_label = ttk.Label(add_window, text="Major:")
        major_label.pack(pady=5)
        major_entry = ttk.Entry(add_window)
        major_entry.pack(pady=5)
        
        def save_student():
            reg_no = reg_no_entry.get()
            name = name_entry.get()
            major = major_entry.get()
            
            if not all([reg_no, name, major]):
                messagebox.showerror("Input Error", "All fields are required!")
                return
            
            conn = get_db_connection()
            if not conn: return
            
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT registration_number FROM students WHERE registration_number = %s", (reg_no,))
                if cursor.fetchone():
                    messagebox.showerror("Error", f"Registration number '{reg_no}' already exists.")
                    return
                
                messagebox.showinfo("Camera Ready", "Please position your face clearly in the center of the camera. The camera will close automatically.")
                embedding, _ = self.capture_face_and_get_embedding()
                if embedding is None:
                    messagebox.showerror("Error", "Failed to capture face. Aborting.")
                    return
                
                messagebox.showinfo("Fingerprint Ready", "Please be ready to scan your finger.")
                fingerprint_template = enroll_fingerprint()
                if fingerprint_template is None:
                    messagebox.showerror("Error", "Failed to capture fingerprint. Aborting.")
                    return
                
                sql = "INSERT INTO students (registration_number, name, face_embedding, fingerprint_template, major) VALUES (%s, %s, %s, %s, %s)"
                cursor.execute(sql, (reg_no, name, embedding.tobytes(), fingerprint_template, major))
                conn.commit()
                messagebox.showinfo("Success", f"Student '{name}' added successfully!")
                load_known_data() # Reload data after new student is added
                add_window.destroy()
                
            except Exception as e:
                messagebox.showerror("Database Error", f"Failed to add student: {e}")
            finally:
                if conn and conn.is_connected():
                    cursor.close()
                    conn.close()

        ttk.Button(add_window, text="Save Student", command=save_student).pack(pady=10)

    def capture_face_and_get_embedding(self):
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            messagebox.showerror("Camera Error", "Failed to open camera.")
            return None, None
            
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            messagebox.showerror("Camera Error", "Failed to capture a frame.")
            return None, None
            
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame)
        
        if len(face_locations) == 1:
            embedding = face_recognition.face_encodings(rgb_frame, face_locations)[0]
            return embedding, frame
        else:
            return None, None

    def edit_student_gui(self):
        reg_no = simpledialog.askstring("Edit Student", "Enter Registration Number:")
        if not reg_no: return
        
        conn = get_db_connection()
        if not conn: return
        
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM students WHERE registration_number = %s", (reg_no,))
            student_data = cursor.fetchone()
            
            if not student_data:
                messagebox.showerror("Not Found", f"Student '{reg_no}' not found.")
                return

            new_name = simpledialog.askstring("Edit Name", "Enter New Name:", initialvalue=student_data['name'])
            if new_name is None: return

            new_major = simpledialog.askstring("Edit Major", "Enter New Major:", initialvalue=student_data['major'])
            if new_major is None: return

            sql = "UPDATE students SET name = %s, major = %s WHERE registration_number = %s"
            cursor.execute(sql, (new_name, new_major, reg_no))
            conn.commit()
            messagebox.showinfo("Success", f"Student '{reg_no}' updated successfully!")
            load_known_data()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to edit student: {e}")
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    def delete_student_gui(self):
        reg_no = simpledialog.askstring("Delete Student", "Enter Registration Number:")
        if not reg_no: return
        
        if not messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete student '{reg_no}'?"):
            return
            
        conn = get_db_connection()
        if not conn: return
        
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM attendance WHERE student_reg_no = %s", (reg_no,))
            cursor.execute("DELETE FROM students WHERE registration_number = %s", (reg_no,))
            
            conn.commit()
            
            # Clean up image files
            face_files = glob.glob(f"faces/{reg_no}_*.jpg")
            for file in face_files:
                os.remove(file)
                
            messagebox.showinfo("Success", f"Student '{reg_no}' and their data deleted.")
            load_known_data()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete student: {e}")
            conn.rollback()
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    def show_students_gui(self):
        show_window = tk.Toplevel(self.master)
        show_window.title("Registered Students")
        
        tree = ttk.Treeview(show_window, columns=("reg_no", "name", "major", "total_attendance"), show="headings")
        tree.heading("reg_no", text="Reg No")
        tree.heading("name", text="Name")
        tree.heading("major", text="Major")
        tree.heading("total_attendance", text="Attendance")
        
        tree.column("reg_no", width=120)
        tree.column("name", width=150)
        tree.column("major", width=120)
        tree.column("total_attendance", width=100)
        
        conn = get_db_connection()
        if not conn: return
        
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT registration_number, name, major, total_attendance FROM students")
            students = cursor.fetchall()
            
            for student in students:
                tree.insert("", "end", values=(
                    student['registration_number'],
                    student['name'],
                    student['major'],
                    student['total_attendance']
                ))
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to retrieve students: {e}")
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
        
        tree.pack(fill=tk.BOTH, expand=True)
        
# --- Attendance System GUI ---
class AttendanceGUI:
    def __init__(self, master, auth_method):
        self.master = master
        self.auth_method = auth_method
        master.title(f"{auth_method} Attendance System")
        master.geometry("800x600")
        
        self.label = ttk.Label(master, text=f"Scanning for {auth_method}...", font=("Helvetica", 16))
        self.label.pack(pady=10)
        
        if self.auth_method == "Face":
            self.video_label = ttk.Label(master)
            self.video_label.pack()
            self.start_camera()
        else: # Fingerprint
            self.status_label = ttk.Label(master, text="Waiting for scan...", font=("Helvetica", 14))
            self.status_label.pack(pady=20)
            self.start_fingerprint_scan()
        
        self.back_button = ttk.Button(master, text="Go Back", command=self.stop_attendance)
        self.back_button.pack(pady=10)

    def start_camera(self):
        global camera_active, stop_threads, detected_faces_data, processing_queue
        
        if not known_face_encodings:
            messagebox.showinfo("Info", "No known faces found. Please register students first.")
            return

        camera_active = True
        stop_threads.clear()
        
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            messagebox.showerror("Camera Error", "Failed to open camera.")
            self.stop_attendance()
            return
            
        self.cap.set(3, 640)
        self.cap.set(4, 480)
        
        self.worker_thread = threading.Thread(target=self.face_processing_worker)
        self.worker_thread.daemon = True
        self.worker_thread.start()
        
        self.update_video()

    def update_video(self):
        if not camera_active:
            return
            
        success, frame = self.cap.read()
        if success:
            frame = cv2.flip(frame, 1)
            
            try:
                processing_queue.put_nowait(frame.copy())
            except Empty:
                pass
            
            with detected_faces_lock:
                current_detected_faces = detected_faces_data.copy()
            
            if current_detected_faces:
                for face_data in current_detected_faces:
                    y1, x2, y2, x1 = [v * 4 for v in face_data['location']]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), face_data['color'], 2)
                    
                    font = cv2.FONT_HERSHEY_DUPLEX
                    draw_text_with_outline(frame, face_data['name'], (x1, y1 - 10), font, 0.7, (255, 255, 255), 2)
                    draw_text_with_outline(frame, face_data['status'], (x1, y2 + 20), font, 0.7, (255, 255, 255), 2)
            
            img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(img)
            imgtk = ImageTk.PhotoImage(image=img)
            self.video_label.imgtk = imgtk
            self.video_label.config(image=imgtk)
            
        self.master.after(10, self.update_video)
    
    def face_processing_worker(self):
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
                    display_status = "Not Registered"
                    frame_color = (0, 0, 255)
                    
                    if known_face_encodings:
                        face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
                        best_match_index = np.argmin(face_distances)
                        
                        if face_distances[best_match_index] < FACE_RECOGNITION_TOLERANCE:
                            student_id = known_student_ids[best_match_index]
                            student_name = known_student_names[best_match_index]
                            
                            display_name = student_name
                            display_status = mark_attendance(student_id, "Face")
                            
                            if display_status == "Marked":
                                frame_color = (0, 255, 0)
                            elif display_status == "Already Marked":
                                frame_color = (0, 255, 255)
                                
                    current_frame_data.append({
                        'location': face_location,
                        'name': display_name,
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

    def start_fingerprint_scan(self):
        self.scan_thread = threading.Thread(target=self.fingerprint_scan_worker)
        self.scan_thread.daemon = True
        self.scan_thread.start()

    def fingerprint_scan_worker(self):
        while not stop_threads.is_set():
            self.status_label.config(text="Place finger on scanner...")
            time.sleep(3) # Simulate scan delay
            
            scanned_template_data = enroll_fingerprint()
            
            if scanned_template_data is None:
                self.status_label.config(text="Scan failed. Try again.")
                time.sleep(2)
                continue
            
            match_found = False
            for student in known_fingerprints:
                if compare_fingerprints(scanned_template_data, student['fingerprint_template']):
                    reg_no = student['registration_number']
                    name = student['name']
                    status = mark_attendance(reg_no, "Fingerprint")
                    self.status_label.config(text=f"Match Found! {name} - {status}")
                    match_found = True
                    break
            
            if not match_found:
                self.status_label.config(text="Fingerprint not recognized.")
            
            time.sleep(2)

    def stop_attendance(self):
        global camera_active, stop_threads
        camera_active = False
        stop_threads.set()
        
        if hasattr(self, 'cap') and self.cap.isOpened():
            self.cap.release()
        
        if hasattr(self, 'worker_thread') and self.worker_thread.is_alive():
            self.worker_thread.join()
        
        if hasattr(self, 'scan_thread') and self.scan_thread.is_alive():
            self.scan_thread.join()
            
        self.master.destroy()

def draw_text_with_outline(image, text, position, font, scale, color, thickness):
    """Draws text with a black outline for better visibility."""
    cv2.putText(image, text, position, font, scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
    cv2.putText(image, text, position, font, scale, color, thickness, cv2.LINE_AA)

class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Integrated Attendance System")
        self.geometry("400x300")
        
        self.title_label = ttk.Label(self, text="Welcome to Attendance System", font=("Helvetica", 16))
        self.title_label.pack(pady=20)
        
        ttk.Button(self, text="Student Management", command=self.open_student_manager).pack(pady=5, fill=tk.X, padx=50)
        ttk.Button(self, text="Start Face Attendance", command=lambda: self.open_attendance("Face")).pack(pady=5, fill=tk.X, padx=50)
        ttk.Button(self, text="Start Fingerprint Attendance", command=lambda: self.open_attendance("Fingerprint")).pack(pady=5, fill=tk.X, padx=50)
        ttk.Button(self, text="Exit", command=self.on_closing).pack(pady=10, fill=tk.X, padx=50)
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Load data at startup
        load_known_data()

    def open_student_manager(self):
        manager_window = tk.Toplevel(self)
        StudentManagerGUI(manager_window)

    def open_attendance(self, method):
        attendance_window = tk.Toplevel(self)
        AttendanceGUI(attendance_window, method)
        
    def on_closing(self):
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            self.destroy()

if __name__ == "__main__":
    app = MainApp()
    app.mainloop()