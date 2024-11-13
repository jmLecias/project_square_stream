import subprocess
import numpy as np
import asyncio
from aiortc import VideoStreamTrack
from av import VideoFrame

class RTSPVideoStreamTrack(VideoStreamTrack):
    def __init__(self, rtsp_url):
        super().__init__()
        self.rtsp_url = rtsp_url
        self.direction = "sendrecv"  # You can use "sendrecv" if it's bidirectional, or "sendonly"

        # Start the FFmpeg subprocess
        self.process = subprocess.Popen(
            [
                '.\\ffmpeg-7.1-full_build\\bin\\ffmpeg.exe',
                '-i', rtsp_url,           # RTSP input URL
                '-f', 'rawvideo',          # Output format is raw video
                '-pix_fmt', 'rgb24',       # Pixel format
                '-an',                     # No audio
                '-vcodec', 'rawvideo',     # Use raw video codec
                'pipe:1'                   # Output to stdout
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=10**8
        )

    async def recv(self):
        # Define video dimensions (ensure they match your stream)
        width, height = 640, 480
        frame_size = width * height * 3  # RGB24 has 3 bytes per pixel

        # Read the raw RGB frame from the FFmpeg stdout
        raw_frame = self.process.stdout.read(frame_size)

        if len(raw_frame) != frame_size:
            raise Exception("Could not retrieve frame from FFmpeg stream")
        
        print("Streaming frame") 
        # Convert the raw bytes to a NumPy array and then to a VideoFrame
        frame = np.frombuffer(raw_frame, np.uint8).reshape((height, width, 3))
        video_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        video_frame.pts, video_frame.time_base = self._get_pts_time_base()

        # Simulate frame rate (30fps)
        await asyncio.sleep(1 / 20)
        return video_frame
