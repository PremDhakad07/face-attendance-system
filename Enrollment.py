import os
import face_recognition
import numpy as np
import mysql.connector

# --- MySQL Database Configuration ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',     # 🔁 Replace with your MySQL username
    'password': 'vitbpl2028', # 🔁 Replace with your MySQL password
    'database': 'project'    # 🔁 Replace with your database name
}

def enroll_faces():
    """
    Reads images from the 'faces' folder, generates face embeddings, and inserts
    them into the MySQL 'students' table.
    """
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        print("Connected to MySQL database.")

        faces_folder_path = "faces"
        if not os.path.exists(faces_folder_path):
            print("Error: 'faces' folder not found.")
            return

        for filename in os.listdir(faces_folder_path):
            if filename.endswith(('.jpg', '.jpeg', '.png')):
                try:
                    # Extract registration number and name from the filename
                    # e.g., '101_John_Doe.jpg' -> reg_no='101', name='John Doe'
                    parts = os.path.splitext(filename)[0].split('_', 1)
                    if len(parts) < 2:
                        print(f"Warning: Skipping invalid filename format: {filename}")
                        continue
                    reg_no = parts[0]
                    name = parts[1].replace('_', ' ')

                    # Load image and get face encoding
                    image_path = os.path.join(faces_folder_path, filename)
                    image = face_recognition.load_image_file(image_path)
                    face_encodings = face_recognition.face_encodings(image)

                    if not face_encodings:
                        print(f"Warning: No face found in {filename}. Skipping.")
                        continue

                    embedding = face_encodings[0]

                    # Convert the NumPy array to a bytes-like object for the BLOB field
                    embedding_bytes = embedding.tobytes()

                    # Insert into the database
                    sql = "INSERT INTO students (registration_number, name, face_embedding) VALUES (%s, %s, %s)"
                    cursor.execute(sql, (reg_no, name, embedding_bytes))
                    conn.commit()
                    print(f"Enrolled student: {reg_no} - {name}")

                except Exception as e:
                    print(f"Error processing {filename}: {e}")

    except mysql.connector.Error as err:
        print(f"Database error: {err}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()
            print("MySQL connection closed.")

if __name__ == "__main__":
    enroll_faces()