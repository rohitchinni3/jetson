import cv2
import csv
import time
import paramiko
from scp import SCPClient
from ultralytics import YOLO

# Load the YOLOv8 model
model = YOLO('yolov8n.pt')

# Define the class ID for 'person' (class 0 in the COCO dataset)
person_class_id = 0

# Open a video capture object for the webcam (use source=0 for the default webcam)
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Error: Could not open video capture.")
    exit()

# Initialize the SSH client
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    # Connect to the OBU over Ethernet
    ssh.connect(hostname="192.168.1.13", username="guest", password="cdac@123", look_for_keys=False)
    
    # Prepare the SCP client for file transfer
    with SCPClient(ssh.get_transport()) as scp:
        
        # Create or open a CSV file for writing
        csv_filename = 'person_detection.csv'
        with open(csv_filename, mode='w', newline='') as file:
            writer = csv.writer(file)
            # Write the header
            writer.writerow(["Serial Number", "Timestamp", "Number of Detections", "Confidence Range", "Detection (1/0)"])

            serial_number = 1

            while True:
                ret, frame = cap.read()
                if not ret:
                    print("Error: Could not read frame from video capture.")
                    break
                
                # Perform inference
                results = model.predict(source=frame, show=True)

                # Initialize detection status and confidence values
                person_detected = False
                detection_count = 0
                confidence_values = []

                for result in results:
                    for bbox in result.boxes:
                        class_id = int(bbox.cls)
                        confidence = float(bbox.conf)  # Use `conf` instead of `confidence`
                        
                        if class_id == person_class_id:
                            person_detected = True
                            detection_count += 1
                            confidence_values.append(confidence)
                
                # Calculate confidence range
                if confidence_values:
                    min_confidence = min(confidence_values)
                    max_confidence = max(confidence_values)
                    confidence_range = f"{min_confidence:.2f}-{max_confidence:.2f}"
                else:
                    confidence_range = "N/A"
                
                # Record the current timestamp
                timestamp = time.strftime('%Y-%m-%d %H %M %S')
                
                # Write the row to the CSV file
                writer.writerow([serial_number, timestamp, detection_count, confidence_range, "1" if person_detected else "0"])
                file.flush()  # Ensure the data is written to disk
                
                # Transfer the CSV file to the OBU
                try:
                    scp.put(csv_filename, "/home/guest/praneeth/")
                    print(f"File transferred successfully at {timestamp}")
                except Exception as e:
                    print(f"Error during file transfer: {e}")
                
                # Increment the serial number
                serial_number += 1

                # Exit if 'q' is pressed
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

finally:
    # Ensure resources are released properly
    cap.release()
    cv2.destroyAllWindows()
    ssh.close()

