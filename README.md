Face Attendance System

A simple Face Recognition-based Attendance System that uses a webcam to detect and recognize faces, and mark attendance automatically.

🚀 Features

Real-time face detection using webcam
Face recognition using stored images
Automatic attendance marking
Timestamp-based record keeping

🛠️ Tech Stack
Language: Python
Libraries: OpenCV, face_recognition, NumPy

📂 Project Structure

face-attendance-system/
│── images/              # Images of registered users
│── main.py              # Main program file
│── encode.py            # Script for encoding faces
│── attendance.csv       # Attendance records
│── requirements.txt     # Dependencies

⚙️ Installation

1. Clone the Repository
git clone https://github.com/PremDhakad07/face-attendance-system.git
cd face-attendance-system

2. Install Dependencies
pip install -r requirements.txt

▶️ Usage

Step 1: Add Images
Add images of people in the images/ folder
Use clear images with visible faces

Step 2: Encode Faces
python encode.py

Step 3: Run the Program
python main.py

Step 4: Attendance Output
Attendance is stored in attendance.csv

🧠 How It Works

Reads images from the dataset
Converts faces into encodings
Captures live video using webcam
Matches detected faces with stored encodings
Marks attendance in a CSV file with time

📄 License

This project is for educational purposes.