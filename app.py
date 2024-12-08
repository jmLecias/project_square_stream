from flask import Flask, Response, request, jsonify
import cv2
import mediapipe as mp
import threading
import time
from datetime import datetime, timezone
import base64
from io import BytesIO
import requests
from pystray import Icon, MenuItem, Menu
from PIL import Image
import sys
import os
import threading
from flask_cors import CORS

# Flask app
app = Flask(__name__)
CORS(app)

# Initialize MediaPipe Face Detection
mp_face_detection = mp.solutions.face_detection

frames = {}
threads = {}
lock = threading.Lock()


def capture_frames(camera_id, rtsp_url, location_id, group_id):
    face_detection = mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.6)
    
    if(rtsp_url == "0"):
        cap = cv2.VideoCapture(0) 
    else:
        cap = cv2.VideoCapture(rtsp_url)
        
    if not cap.isOpened():
        print(f"Error: Unable to open RTSP stream for {camera_id}")
        return

    previous_detection_count = 0
    last_sent_time = 0
    debounce_interval = 4  # Seconds to wait before sending another request

    while True:
        ret, frame = cap.read()
        if not ret:
            print(f"Stream ended for {camera_id}")
            break

        frame = cv2.resize(frame, (640, 480))

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_detection.process(frame_rgb)

        current_detection_count = len(results.detections) if results.detections else 0

        if not previous_detection_count == current_detection_count:
            previous_detection_count = current_detection_count
            now = time.time()
            
            if current_detection_count > 0 and (now - last_sent_time) >= debounce_interval:
                last_sent_time = now

                # Update the previous detection count

                _, buffer = cv2.imencode('.jpg', frame)

                # Prepare datetime in ISO format
                datetime_now = datetime.now(timezone.utc).isoformat()

                # Prepare the data in FormData format (mimicking FormData in JS)
                files = {
                    'capturedFrames': (f"{datetime_now}_location_{location_id}.png", BytesIO(buffer), 'image/png')
                }

                data = {
                    'datetime': datetime_now,
                    'location_id': location_id,
                    'group_id': group_id,
                }

                # Send the request to the backend
                try:
                    response = requests.post(
                        'https://api.official-square.site/face/recognize-faces', 
                        files=files,  # 'files' holds the image file to send
                        data=data,    # 'data' holds the rest of the fields
                        timeout=20    # 20 secs for slow connection
                    )

                    if response.status_code == 200:
                        print(f"Recognition request sent successfully: {response.json()}")
                    else:
                        print(f"Failed to send recognition request: {response}")
                except Exception as e:
                    print(f"Error sending recognition request: {str(e)}")


        # Draw detections
        if results.detections:
            for detection in results.detections:
                bboxC = detection.location_data.relative_bounding_box
                h, w, _ = frame.shape
                bbox = (
                    int(bboxC.xmin * w),
                    int(bboxC.ymin * h),
                    int(bboxC.width * w),
                    int(bboxC.height * h),
                )
                cv2.rectangle(frame, (bbox[0], bbox[1]),
                                    (bbox[0] + bbox[2], bbox[1] + bbox[3]),
                                    (255, 0, 0), 2)

        # Store the frame with a lock
        with lock:
            frames[camera_id] = frame

    cap.release()


def generate_frames(camera_id):
    while True:
        with lock:
            frame = frames.get(camera_id)

        if frame is not None:
            # Encode the frame to JPEG
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
            if not ret:
                continue

            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')


@app.route('/video_feed/<camera_id>')
def video_feed(camera_id):
    if int(camera_id) not in frames:
        return f"Invalid camera ID: {camera_id}", 404
    return Response(generate_frames(int(camera_id)), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/stream_cameras', methods=['POST'])
def stream_cameras():
    try:
        data = request.json
        cameras = data.get('cameras', [])

        if not isinstance(cameras, list):
            return jsonify({"error": "Invalid input format"}), 400

        started_threads = []
        for camera in cameras:
            camera_id = camera.get('camera_id')
            rtsp_url = camera.get('rtsp_url')
            location_id = camera.get('location_id')
            group_id = camera.get('group_id')

            if not camera_id or not rtsp_url:
                return jsonify({"error": f"Invalid camera entry: {camera}"}), 400
            
            if camera_id in threads:
                started_threads.append(camera_id)
                continue
            else:
                if (rtsp_url == "0"):
                    cap = cv2.VideoCapture(0)
                else:
                    cap = cv2.VideoCapture(rtsp_url)
                if not cap.isOpened():
                    print(f"RTSP URL unavailable: {rtsp_url}")
                    continue  # Skip this camera if the RTSP URL is not accessible
                cap.release()
                
                # Add the camera to the frames and start a new thread
                with lock:
                    frames[camera_id] = None
                    
                thread = threading.Thread(target=capture_frames, args=(camera_id, rtsp_url, location_id, group_id))
                thread.daemon = True
                thread.start()
                threads[camera_id] = thread
                started_threads.append(camera_id)

        return jsonify({"message": "Cameras initiated successfully", "cameras": started_threads}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    
@app.route('/stream_camera', methods=['POST'])
def stream_camera():
    try:
        camera = request.json

        if not camera:
            return jsonify({"error": "Camera object is required"}), 400

        camera_id = camera.get('camera_id')
        rtsp_url = camera.get('rtsp_url')
        location_id = camera.get('location_id')
        group_id = camera.get('group_id')

        if not camera_id or not rtsp_url:
            return jsonify({"error": "Missing required fields: 'camera_id' and 'rtsp_url'"}), 400

        if camera_id in threads:
            return jsonify({"message": f"Camera {camera_id} is already streaming", "camera_id": camera_id}), 200

        # Test RTSP URL or webcam
        if rtsp_url == "0":
            cap = cv2.VideoCapture(0)
        else:
            cap = cv2.VideoCapture(rtsp_url)

        if not cap.isOpened():
            return jsonify({"error": f"RTSP URL unavailable: {rtsp_url}"}), 400

        cap.release()

        # Add the camera to the frames and start a new thread
        with lock:
            frames[camera_id] = None

        thread = threading.Thread(target=capture_frames, args=(camera_id, rtsp_url, location_id, group_id))
        thread.daemon = True
        thread.start()
        threads[camera_id] = thread

        return jsonify({"message": f"Camera {camera_id} started successfully", "camera_id": camera_id}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500



def create_image():
    # Determine the path for the bundled logo image
    if getattr(sys, 'frozen', False):  # If running as a bundled .exe
        logo_path = os.path.join(sys._MEIPASS, 'official-square.png')
    else:
        logo_path = 'official-square.png'  # When running normally (not bundled)

    # Open and resize the logo image
    image = Image.open(logo_path)
    image = image.resize((64, 64), Image.Resampling.LANCZOS)
    return image

def quit_action(icon, item):
    icon.stop()
    print("Application quitting...")
    os._exit(0)  # Forcefully exit


def start_tray():
    # Create tray icon
    icon = Icon("OfficialSquareRtspStreamer", create_image(), menu=Menu(MenuItem("Quit", quit_action)))
    icon.run()


if __name__ == '__main__':
    # Start the Flask app in a separate thread
    flask_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000))
    flask_thread.daemon = True
    flask_thread.start()

    # Start the system tray icon
    start_tray()
