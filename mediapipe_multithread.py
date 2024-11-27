from flask import Flask, Response, request, jsonify
import cv2
import mediapipe as mp
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


def capture_frames(camera_id, rtsp_url):
    face_detection = mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.6)
    
    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        print(f"Error: Unable to open RTSP stream for {camera_id}")
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            print(f"Stream ended for {camera_id}")
            break

        # Downscale the frame
        frame = cv2.resize(frame, (640, 480))

        # Process the frame (face detection)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_detection.process(frame_rgb)

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
    if camera_id not in frames:
        return f"Invalid camera ID: {camera_id}", 404
    return Response(generate_frames(camera_id), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/stream_cameras', methods=['POST'])
def stream__cameras():
    try:
        data = request.json
        cameras = data.get('cameras', [])
        location_id = data.get('location_id')
        camera_type = data.get('camera_type')

        if not isinstance(cameras, list) or not location_id or not camera_type:
            return jsonify({"error": "Invalid input format"}), 400

        new_threads = []
        for camera in cameras:
            camera_id = camera.get('camera_id')
            ip_address = camera.get('ip_address')

            if not camera_id or not ip_address:
                return jsonify({"error": f"Invalid camera entry: {camera}"}), 400

            if camera_id in threads:
                return jsonify({"error": f"Camera {camera_id} already exists"}), 400

            # Add the camera to the frames and start a new thread
            with lock:
                frames[camera_id] = None
            thread = threading.Thread(target=capture_frames, args=(camera_id, ip_address))
            thread.daemon = True
            thread.start()
            threads[camera_id] = thread
            new_threads.append(camera_id)

        return jsonify({"message": "Cameras added successfully", "cameras": new_threads}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500



if __name__ == '__main__':
    # Run the Flask app
    app.run(host='0.0.0.0', port=5000)
