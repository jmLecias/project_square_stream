import cv2
from flask import Flask, Response, request, send_from_directory
from flask_cors import CORS
from threading import Thread, Lock
import time
from stream_manager import StreamManager
import os
import subprocess

app = Flask(__name__)
CORS(app, origins=["*"])

# rtsp://CAPSTONE:@CAPSTONE2@192.168.254.106:554/live/ch00_0

# Load MobileNet SSD model for detection
net = cv2.dnn.readNetFromCaffe("MobileNetSSD_deploy.prototxt", "MobileNetSSD_deploy.caffemodel")
labels = {15: "person"}  # Only detecting "person" for simplicity

# Stream manager dictionary to handle each unique RTSP URL
stream_managers = {}
lock = Lock()  # To synchronize access to the stream manager dictionary

OUTPUT_DIR = 'hls'
OUTPUT_FILE = f'{OUTPUT_DIR}/stream.m3u8'

@app.route('/stream')
def stream_route():
    rtsp_url = request.args.get("rtsp")
    apply_model = request.args.get("apply_model", "true").lower() == "true"
    show_boxes = request.args.get("show_boxes", "true").lower() == "true"
    conf_threshold = float(request.args.get("conf_threshold", 0.5))

    if not rtsp_url:
        return "RTSP URL is required", 400

    with lock:
        # Check if the stream manager already exists
        if rtsp_url not in stream_managers:
            # Create a new StreamManager if it doesn't exist
            stream_managers[rtsp_url] = StreamManager(rtsp_url, apply_model, show_boxes, conf_threshold)

    def generate():
        while True:
            frame = stream_managers[rtsp_url].get_frame()
            if frame:
                yield (b'--frame\r\n'
                        b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            else:
                time.sleep(0.1)  # Small delay if no frame is available yet

    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

# @app.route('/stream', methods=['GET'])
# def stream_m3u8():
#     return send_from_directory(directory=OUTPUT_DIR, path='stream.m3u8')

# @app.route('/<path:filename>', methods=['GET'])
# def stream_ts(filename):
#     return send_from_directory(directory=OUTPUT_DIR, path=filename)

# def process_stream():
#     os.makedirs(OUTPUT_DIR, exist_ok=True)
    
#     command = [
#         ".\\ffmpeg-7.1-full_build\\bin\\ffmpeg.exe",
#         "-rtsp_transport", "tcp",  
#         "-i", "rtsp://CAPSTONE:@CAPSTONE2@192.168.254.106:554/live/ch00_0",
#         "-c:v", "libx264",
#         "-preset", "ultrafast",  # Reduce encoding latency
#         "-hls_time", "1",  # Shorter segment duration
#         "-hls_list_size", "2",  # Fewer segments for faster startup
#         "-hls_flags", "delete_segments+omit_endlist",  # Options to reduce latency
#         OUTPUT_FILE
#     ]
    
#     subprocess.Popen(command)

# Start Flask app
if __name__ == '__main__':
    # process_stream()
    app.run(host='0.0.0.0', port=5000, debug=True)
