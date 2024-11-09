import cv2
import numpy as np
from threading import Thread, Lock
import subprocess

# Load MobileNet SSD model for detection
net = cv2.dnn.readNetFromCaffe("MobileNetSSD_deploy.prototxt", "MobileNetSSD_deploy.caffemodel")
labels = {15: "person"}  # Only detecting "person" for simplicity

class StreamManager:
    def __init__(self, rtsp_url, show_boxes, apply_model, conf_threshold=0.5):
        self.rtsp_url = rtsp_url
        self.show_boxes = show_boxes
        self.apply_model = apply_model
        self.conf_threshold = conf_threshold
        self.frame = None
        self.thread = Thread(target=self.update_stream, daemon=True)
        self.thread.start()
        self.active = True

    def update_stream(self):
        # Open RTSP stream
        cap = cv2.VideoCapture(self.rtsp_url)
        cap.set(3, 640)  # Width
        cap.set(4, 360)  # Height (360 if 16:9 aspect ratio)
        cap.set(5, 15)  # Frames per second
        
        if not cap.isOpened():
            print(f"Error: Couldn't open RTSP stream {self.rtsp_url}")
            self.active = False
            return

        while self.active:
            ret, frame = cap.read()
            if not ret:
                print(f"Error: Couldn't read frame from {self.rtsp_url}")
                self.active = False
                break

            if self.apply_model:
                # Perform detection
                blob = cv2.dnn.blobFromImage(frame, 0.007843, (300, 300), 127.5)
                net.setInput(blob)
                detections = net.forward()
                
                if self.show_boxes:
                    for i in range(detections.shape[2]):
                        confidence = detections[0, 0, i, 2]
                        if confidence > self.conf_threshold:
                            idx = int(detections[0, 0, i, 1])
                            if idx in labels:
                                box = detections[0, 0, i, 3:7] * np.array(
                                    [frame.shape[1], frame.shape[0], frame.shape[1], frame.shape[0]]
                                )
                                (x1, y1, x2, y2) = box.astype("int")
                                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                                label = f"{labels[idx]}: {confidence:.2f}"
                                cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            # Update current frame
            self.frame = frame

        cap.release()

    def get_frame(self):
        # Encode the frame in JPEG format for streaming
        if self.frame is not None:
            ret, jpeg = cv2.imencode('.jpg', self.frame)
            if ret:
                return jpeg.tobytes()
        return None