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
from PIL import Image, ImageTk, ImageDraw, ImageFont

# --- MySQL Database Configuration ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'vitbpl2028',
    'database': 'project'
}

# Time in seconds to wait before marking attendance for the same person again
MIN_TIME_BETWEEN_ATTENDANCE = 43200

# Tolerance for face recognition. A higher value is more forgiving.
FACE_RECOGNITION_TOLERANCE = 0.6

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
def enroll_fingerprint_with_progress(callback):
    """
    (SIMULATED) Captures a fingerprint template with progress updates.
    """
    try:
        # Simulate initial state before scan
        time.sleep(1)
        
        # Simulate the actual scan process with percentage updates
        for i in range(1, 6):
            time.sleep(0.5)
            callback(i * 20)
            
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

# --- Student Manager GUI ---
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
        add_window = tk.Toplevel(self.master)
        add_window.title("Add New Student")
        add_window.geometry("800x600")

        self.captured_face_embedding = None
        self.captured_fingerprint_template = None
        self.cap = None
        self.cam_thread_id = None
        
        # UI Layout
        main_frame = ttk.Frame(add_window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        input_frame = ttk.Frame(main_frame)
        input_frame.pack(side=tk.LEFT, padx=20, pady=10)
        
        camera_frame = ttk.Frame(main_frame)
        camera_frame.pack(side=tk.RIGHT, padx=20, pady=10)
        
        ttk.Label(input_frame, text="Registration Number:").pack(pady=2)
        self.reg_no_entry = ttk.Entry(input_frame)
        self.reg_no_entry.pack(pady=2)
        
        ttk.Label(input_frame, text="Full Name:").pack(pady=2)
        self.name_entry = ttk.Entry(input_frame)
        self.name_entry.pack(pady=2)
        
        ttk.Label(input_frame, text="Major:").pack(pady=2)
        self.major_entry = ttk.Entry(input_frame)
        self.major_entry.pack(pady=2)
        
        ttk.Label(input_frame, text="Current Year:").pack(pady=2)
        self.year_entry = ttk.Entry(input_frame)
        self.year_entry.pack(pady=2)
        
        ttk.Label(input_frame, text="Starting Year:").pack(pady=2)
        self.start_year_entry = ttk.Entry(input_frame)
        self.start_year_entry.pack(pady=2)

        self.cam_label = ttk.Label(camera_frame, text="Camera Not Running")
        self.cam_label.pack()
        
        self.camera_button = ttk.Button(input_frame, text="Start Camera", command=self.toggle_camera)
        self.camera_button.pack(pady=10)
        
        self.capture_button = ttk.Button(input_frame, text="Capture Face", command=self.capture_face_from_feed, state='disabled')
        self.capture_button.pack(pady=5)
        
        self.fingerprint_button = ttk.Button(input_frame, text="Capture Fingerprint", command=self.capture_fingerprint)
        self.fingerprint_button.pack(pady=10)

        self.save_button = ttk.Button(input_frame, text="Save Student", command=self.save_student, state='disabled')
        self.save_button.pack(pady=10)
        
        self.status_label = ttk.Label(input_frame, text="", font=("Helvetica", 12))
        self.status_label.pack(pady=10)
        
        self.progress_bar = ttk.Progressbar(input_frame, orient='horizontal', length=200, mode='determinate')
        self.progress_label = ttk.Label(input_frame, text="")

    def toggle_camera(self):
        if self.cap is None or not self.cap.isOpened():
            self.start_camera_feed()
            self.camera_button.config(text="Stop Camera")
            self.capture_button.config(state='normal')
            self.status_label.config(text="Camera is active", foreground="blue")
        else:
            self.stop_camera_feed()
            self.camera_button.config(text="Start Camera")
            self.capture_button.config(state='disabled')
            self.status_label.config(text="Camera is off", foreground="black")

    def start_camera_feed(self):
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.cam_label.config(text="Error: Could not open camera.")
            return

        def show_frame():
            if not self.master.winfo_exists(): return
            
            ret, frame = self.cap.read()
            if ret:
                frame = cv2.flip(frame, 1)
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                face_locations = face_recognition.face_locations(rgb_frame)
                
                for (top, right, bottom, left) in face_locations:
                    cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                
                img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                imgtk = ImageTk.PhotoImage(image=img)
                self.cam_label.imgtk = imgtk
                self.cam_label.config(image=imgtk)
                self.cam_thread_id = self.cam_label.after(10, show_frame)
            else:
                self.stop_camera_feed()

        show_frame()

    def stop_camera_feed(self):
        if self.cam_thread_id:
            self.cam_label.after_cancel(self.cam_thread_id)
            self.cam_thread_id = None
        if self.cap:
            self.cap.release()
            self.cap = None

    def capture_face_from_feed(self):
        if self.cap is None or not self.cap.isOpened():
            messagebox.showerror("Camera Error", "Camera is not active.")
            return

        ret, frame = self.cap.read()
        if not ret:
            self.status_label.config(text="Failed to capture image!", foreground="red")
            return

        self.stop_camera_feed()

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame)
        
        if len(face_locations) == 1:
            self.captured_face_embedding = face_recognition.face_encodings(rgb_frame, face_locations)[0]
            self.status_label.config(text="Face captured successfully!", foreground="green")
            self.update_save_button_state()

            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            imgtk = ImageTk.PhotoImage(image=img)
            self.cam_label.imgtk = imgtk
            self.cam_label.config(image=imgtk)
        else:
            self.captured_face_embedding = None
            self.status_label.config(text="No single face detected. Try again.", foreground="red")
            self.toggle_camera()
        
    def capture_fingerprint(self):
        self.progress_bar.pack(pady=5)
        self.progress_label.pack(pady=2)
        self.progress_bar['value'] = 0
        self.progress_label.config(text="0% Stored")
        self.status_label.config(text="Place your finger on the sensor...", foreground="blue")

        def on_progress(percent):
            self.progress_bar['value'] = percent
            self.progress_label.config(text=f"{percent}% Stored")
            self.master.update_idletasks()

        def capture_thread():
            self.captured_fingerprint_template = enroll_fingerprint_with_progress(on_progress)
            self.master.after(0, self.progress_bar.pack_forget)
            self.master.after(0, self.progress_label.pack_forget)
            if self.captured_fingerprint_template:
                self.master.after(0, self.status_label.config, text="Fingerprint captured successfully!", foreground="green")
                self.master.after(0, self.update_save_button_state)
            else:
                self.master.after(0, self.status_label.config, text="Fingerprint capture failed!", foreground="red")

        threading.Thread(target=capture_thread).start()

    def update_save_button_state(self):
        if self.captured_face_embedding is not None and self.captured_fingerprint_template is not None:
            self.save_button.config(state='normal')
        else:
            self.save_button.config(state='disabled')

    def save_student(self):
        reg_no = self.reg_no_entry.get()
        name = self.name_entry.get()
        major = self.major_entry.get()
        year = self.year_entry.get()
        starting_year = self.start_year_entry.get()
        
        if not all([reg_no, name, major, year, starting_year]):
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
            
            sql = "INSERT INTO students (registration_number, name, face_embedding, fingerprint_template, major, year, starting_year) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            cursor.execute(sql, (reg_no, name, self.captured_face_embedding.tobytes(), self.captured_fingerprint_template, major, year, starting_year))
            conn.commit()
            messagebox.showinfo("Success", f"Student '{name}' added successfully!")
            load_known_data()
            self.master.destroy()
            
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to add student: {e}")
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

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
    def __init__(self, master):
        self.master = master
        master.title("Combined Attendance System")
        master.geometry("1000x700")
        
        self.main_frame = ttk.Frame(master, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.video_frame = ttk.Frame(self.main_frame, relief="solid", borderwidth=1)
        self.video_frame.pack(side=tk.LEFT, padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        self.info_frame = ttk.Frame(self.main_frame, relief="solid", borderwidth=1, width=350)
        self.info_frame.pack(side=tk.RIGHT, padx=10, pady=10, fill=tk.Y)
        self.info_frame.pack_propagate(False)

        # Video label inside the video frame
        self.video_label = ttk.Label(self.video_frame, text="Camera Feed")
        self.video_label.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # UI elements in the info frame
        ttk.Label(self.info_frame, text="System Status", font=("Helvetica", 14, "bold")).pack(pady=(10, 5))
        
        self.face_status_label = ttk.Label(self.info_frame, text="Face: Scanning...", font=("Helvetica", 12))
        self.face_status_label.pack(pady=5)
        
        self.fingerprint_status_label = ttk.Label(self.info_frame, text="Fingerprint: Waiting...", font=("Helvetica", 12))
        self.fingerprint_status_label.pack(pady=5)
        
        ttk.Separator(self.info_frame, orient='horizontal').pack(fill='x', pady=10)
        
        ttk.Label(self.info_frame, text="Recent Attendance", font=("Helvetica", 14, "bold")).pack(pady=(5, 5))
        
        self.recent_attendance_list = tk.Listbox(self.info_frame, height=15, width=40, font=("Helvetica", 10))
        self.recent_attendance_list.pack(pady=(0, 10), padx=10, fill=tk.BOTH, expand=True)
        
        self.back_button = ttk.Button(self.info_frame, text="Go Back", command=self.stop_attendance)
        self.back_button.pack(pady=10)

        self.frame_count = 0
        self.process_every = 5
        self.cap = None
        self.worker_thread = None
        self.scan_thread = None
        
        self.start_combined_attendance()
        
        self.recent_log = []

    def update_recent_log(self, student_name, auth_method):
        self.recent_log.insert(0, f"{student_name} ({auth_method})")
        if len(self.recent_log) > 5:
            self.recent_log.pop()
        
        self.recent_attendance_list.delete(0, tk.END)
        for entry in self.recent_log:
            self.recent_attendance_list.insert(tk.END, entry)

    def start_combined_attendance(self):
        global camera_active, stop_threads, detected_faces_data, processing_queue
        
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
        
        self.scan_thread = threading.Thread(target=self.fingerprint_scan_worker)
        self.scan_thread.daemon = True
        self.scan_thread.start()
        
        self.update_video()

    def update_video(self):
        if not self.master.winfo_exists() or not camera_active:
            return
            
        success, frame = self.cap.read()
        if success:
            frame = cv2.flip(frame, 1)
            
            self.frame_count += 1
            if self.frame_count % self.process_every == 0:
                try:
                    while not processing_queue.empty():
                        processing_queue.get_nowait()
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
                    cv2.putText(frame, face_data['name'], (x1, y1 - 10), font, 0.7, (255, 255, 255), 2)
                    cv2.putText(frame, face_data['status'], (x1, y2 + 20), font, 0.7, (255, 255, 255), 2)
            
            img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(img)
            imgtk = ImageTk.PhotoImage(image=img)
            self.video_label.imgtk = imgtk
            self.video_label.config(image=imgtk)
            
        self.master.after(10, self.update_video)
    
    def face_processing_worker(self):
        while not stop_threads.is_set():
            if not self.master.winfo_exists(): break
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
                            mark_result = mark_attendance(student_id, "Face")
                            display_status = mark_result
                            
                            if mark_result == "Marked":
                                frame_color = (0, 255, 0)
                                self.master.after(0, self.face_status_label.config, text=f"Face: Recognized {student_name}!")
                                self.master.after(0, self.update_recent_log, student_name, "Face")
                            elif mark_result == "Already Marked":
                                frame_color = (0, 255, 255)
                                self.master.after(0, self.face_status_label.config, text=f"Face: {student_name} Already Checked In")
                            else:
                                self.master.after(0, self.face_status_label.config, text="Face: Not Recognized")

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

    def fingerprint_scan_worker(self):
        while not stop_threads.is_set():
            if not self.master.winfo_exists(): break
            self.master.after(0, self.fingerprint_status_label.config, text="Fingerprint: Place finger on sensor...", foreground="blue")
            
            time.sleep(2) # Wait for finger placement
            
            scanned_template_data = enroll_fingerprint_with_progress(lambda p: self.master.after(0, self.fingerprint_status_label.config, text=f"Fingerprint: Scanning... {p}%", foreground="blue"))
            
            if scanned_template_data is None:
                self.master.after(0, self.fingerprint_status_label.config, text="Fingerprint: Scan failed. Try again.", foreground="red")
                time.sleep(2)
                continue
            
            match_found = False
            for student in known_fingerprints:
                if compare_fingerprints(scanned_template_data, student['fingerprint_template']):
                    reg_no = student['registration_number']
                    name = student['name']
                    mark_result = mark_attendance(reg_no, "Fingerprint")
                    
                    if mark_result == "Marked":
                        self.master.after(0, self.fingerprint_status_label.config, text=f"Fingerprint: Match Found for {name}!", foreground="green")
                        self.master.after(0, self.update_recent_log, name, "Fingerprint")
                    elif mark_result == "Already Marked":
                        self.master.after(0, self.fingerprint_status_label.config, text=f"Fingerprint: {name} Already Checked In", foreground="orange")
                    else:
                        self.master.after(0, self.fingerprint_status_label.config, text="Fingerprint: Database Error", foreground="red")
                    
                    match_found = True
                    break
            
            if not match_found:
                self.master.after(0, self.fingerprint_status_label.config, text="Fingerprint: Not Recognized.", foreground="red")
            
            time.sleep(2)

    def stop_attendance(self):
        global camera_active, stop_threads
        camera_active = False
        stop_threads.set()
        
        if hasattr(self, 'cap') and self.cap is not None and self.cap.isOpened():
            self.cap.release()
        
        if hasattr(self, 'worker_thread') and self.worker_thread.is_alive():
            self.worker_thread.join()
        
        if hasattr(self, 'scan_thread') and self.scan_thread.is_alive():
            self.scan_thread.join()
            
        self.master.destroy()

class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Integrated Attendance System")
        self.state('zoomed')
        
        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        
        self.title_label = ttk.Label(self, text="Integrated Attendance System", font=("Helvetica", 16, "bold"))
        self.title_label.pack(pady=20)
        
        ttk.Button(self, text="Student Management", command=self.open_student_manager).pack(pady=5, fill=tk.X, padx=50)
        ttk.Button(self, text="Start Combined Attendance", command=self.open_combined_attendance).pack(pady=5, fill=tk.X, padx=50)
        ttk.Button(self, text="Exit", command=self.on_closing).pack(pady=10, fill=tk.X, padx=50)
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        load_known_data()

    def open_student_manager(self):
        manager_window = tk.Toplevel(self)
        StudentManagerGUI(manager_window)

    def open_combined_attendance(self):
        attendance_window = tk.Toplevel(self)
        AttendanceGUI(attendance_window)
        
    def on_closing(self):
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            self.destroy()

if __name__ == "__main__":
    app = MainApp()
    app.mainloop()