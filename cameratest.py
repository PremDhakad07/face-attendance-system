import cv2

# Initialize the webcam (0 is the default camera)
camera = cv2.VideoCapture(0)

while True:
    # Capture frame-by-frame
    ret, frame = camera.read()
    
    # If frame is read correctly, ret is True
    if not ret:
        print("Failed to grab frame")
        break
    
    # Display the resulting frame
    cv2.imshow('Webcam Feed', frame)
    
    # Press 'q' to exit the video window
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Release the camera and close all OpenCV windows
camera.release()
cv2.destroyAllWindows()
