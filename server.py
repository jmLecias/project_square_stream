import argparse
import asyncio
import json
import logging
import os
import ssl
import uuid

import cv2
import numpy as np
import gc
from aiohttp import web
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder, MediaRelay
from av import VideoFrame

ROOT = os.path.dirname(__file__)

logger = logging.getLogger("pc")
pcs = set()
relay = MediaRelay()


net = cv2.dnn.readNetFromCaffe("MobileNetSSD_deploy.prototxt", "MobileNetSSD_deploy.caffemodel")
labels = {15: "person"}  # Only detecting "person" for simplicity

face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

class VideoTransformTrack(MediaStreamTrack):
    """
    A video stream track that transforms frames from another track.
    """

    kind = "video"

    def __init__(self, track, transform, conf_threshold=0.5):
        super().__init__()
        self.track = track
        self.transform = transform
        self.conf_threshold = conf_threshold

    async def recv(self):
        orig_frame = await self.track.recv()
        frame = orig_frame.to_ndarray(format="bgr24")

        gc.collect()
        
        # # Perform object detection
        # blob = cv2.dnn.blobFromImage(frame, 0.007843, (300, 300), 127.5)
        # net.setInput(blob)
        # detections = net.forward()
        
        # # Draw bounding boxes and labels for detected persons
        # for i in range(detections.shape[2]):
        #     confidence = detections[0, 0, i, 2]
        #     if confidence > self.conf_threshold:
        #         idx = int(detections[0, 0, i, 1])
        #         if idx in labels:
        #             box = detections[0, 0, i, 3:7] * np.array(
        #                 [frame.shape[1], frame.shape[0], frame.shape[1], frame.shape[0]]
        #             )
        #             (x1, y1, x2, y2) = box.astype("int")
        #             cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        #             label = f"{labels[idx]}: {confidence:.2f}"
        #             cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # # Convert modified frame back to VideoFrame format
        # new_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        # new_frame.pts = orig_frame.pts
        # new_frame.time_base = orig_frame.time_base
        
        # return new_frame
        
        # gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)  # Convert to grayscale for Haar Cascade
        # faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        
        # # Draw bounding boxes for detected faces
        # for (fx, fy, fw, fh) in faces:
        #     cv2.rectangle(frame, (fx, fy), (fx + fw, fy + fh), (255, 0, 0), 2)
        #     cv2.putText(frame, "Face", (fx, fy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

        # Convert modified frame back to VideoFrame format
        new_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        new_frame.pts = orig_frame.pts
        new_frame.time_base = orig_frame.time_base

        return orig_frame
            


async def index(request):
    content = open(os.path.join(ROOT, "index.html"), "r").read()
    return web.Response(content_type="text/html", text=content)


async def javascript(request):
    content = open(os.path.join(ROOT, "client.js"), "r").read()
    return web.Response(content_type="application/javascript", text=content)


async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pc_id = "PeerConnection(%s)" % uuid.uuid4()
    pcs.add(pc)

    def log_info(msg, *args):
        logger.info(pc_id + " " + msg, *args)

    log_info("Created for %s", request.remote)

    # prepare local media
    audio_player = MediaPlayer(os.path.join(ROOT, "demo-instruct.wav"))
    
    video_player = MediaPlayer(
    "rtsp://CAPSTONE:@CAPSTONE2@192.168.254.105:554/live/ch00_0",
    options={
        "rtsp_transport": "tcp",               # Force TCP transport
        "buffer_size": "65536",                # Set a higher buffer size
        "max_delay": "500000",                 # Max delay for buffering in microseconds
        "stimeout": "5000000",                 # Set a timeout for the stream
        "fflags": "nobuffer",                  # Disable buffer (or use lower latency buffer)
        "flags": "low_delay",                  # Low latency mode
        "analyzeduration": "10000000",
        "probesize": "10000000"
    }
)
    if args.record_to:
        recorder = MediaRecorder(args.record_to)
    else:
        recorder = MediaBlackhole()

    @pc.on("datachannel")
    def on_datachannel(channel):
        @channel.on("message")
        def on_message(message):
            if isinstance(message, str) and message.startswith("ping"):
                channel.send("pong" + message[4:])

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        log_info("Connection state is %s", pc.connectionState)
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    @pc.on("track")
    def on_track(track):
        log_info("Track %s received", track.kind)

        if track.kind == "audio":
            pc.addTrack(audio_player.audio)
            recorder.addTrack(track)
        elif track.kind == "video":
            pc.addTrack(
                VideoTransformTrack(
                    relay.subscribe(video_player.video), transform=params["video_transform"]
                )
            )
            if args.record_to:
                recorder.addTrack(relay.subscribe(track))

        @track.on("ended")
        async def on_ended():
            log_info("Track %s ended", track.kind)
            await recorder.stop()

    # handle offer
    await pc.setRemoteDescription(offer)
    await recorder.start()

    # send answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )


async def on_shutdown(app):
    # close peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="WebRTC audio / video / data-channels demo"
    )
    parser.add_argument("--cert-file", help="SSL certificate file (for HTTPS)")
    parser.add_argument("--key-file", help="SSL key file (for HTTPS)")
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host for HTTP server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port for HTTP server (default: 8080)"
    )
    parser.add_argument("--record-to", help="Write received media to a file.")
    parser.add_argument("--verbose", "-v", action="count")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.cert_file:
        ssl_context = ssl.SSLContext()
        ssl_context.load_cert_chain(args.cert_file, args.key_file)
    else:
        ssl_context = None

    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/", index)
    app.router.add_get("/client.js", javascript)
    app.router.add_post("/offer", offer)
    web.run_app(
        app, access_log=None, host=args.host, port=args.port, ssl_context=ssl_context
    )
