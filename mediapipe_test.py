from flask import Flask, Response
import cv2
import mediapipe as mp

# Flask app
app = Flask(__name__)

# RTSP stream URL
rtsp_url_1 = "rtsp://CAPSTONE:@CAPSTONE2@192.168.1.7:554/live/ch00_0"
rtsp_url_2 = "rtsp://CAPSTONE:@CAPSTONE2@192.168.1.8:554/live/ch00_0"

# Initialize MediaPipe Face Detection
mp_face_detection = mp.solutions.face_detection
face_detection = mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.6)

# Function to generate frames for MJPEG stream
def generate_frames(rtsp_url):
    cap = cv2.VideoCapture(rtsp_url)

    if not cap.isOpened():
        print("Error: Unable to open RTSP stream.")
        return

    while True:
        ret, frame = cap.read()
        if not ret:
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

        # Encode with lower quality
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
        if not ret:
            break

        # Limit frame rate

        # Yield the frame
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

    cap.release()

# Flask route for the video feed
@app.route('/video_feed_1')
def video_feed_1():
    return Response(generate_frames(rtsp_url_1), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/video_feed_2')
def video_feed_2():
    return Response(generate_frames(rtsp_url_2), mimetype='multipart/x-mixed-replace; boundary=frame')

# Flask route for the webpage
@app.route('/')
def index():
    return '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>Face Detection Stream</title>
    </head>
    <body>
        <h1>Face Detection Stream</h1>
        <img src="/video_feed_1" style="width: 100%; max-width: 640px;">
        <img src="/video_feed_2" style="width: 100%; max-width: 640px;">
        <img src="/video_feed_1" style="width: 100%; max-width: 640px;">
        <img src="/video_feed_2" style="width: 100%; max-width: 640px;">
        <img src="/video_feed_1" style="width: 100%; max-width: 640px;">
        <img src="/video_feed_2" style="width: 100%; max-width: 640px;">
    </body>
    </html>
    '''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
