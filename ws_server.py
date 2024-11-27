import asyncio
import websockets
import subprocess
import os

# "rtsp://CAPSTONE:@CAPSTONE2@192.168.254.106:554/live/ch00_0"    # RTSP V380 FORMAT

async def stream_rtsp(websocket):
    # FFmpeg command to capture RTSP stream and encode it into H264 format
    ffmpeg_command = [
        'ffmpeg',
        '-i', "rtsp://CAPSTONE:@CAPSTONE2@192.168.254.105:554/live/ch00_0",  # Your RTSP stream URL
        '-rtsp_transport', 'tcp',             # Force RTSP over TCP
        '-probesize', '10000000',             # Increase probe size to 10MB for better stream detection
        '-analyzeduration', '5000000',        # Analyze for 5 seconds
        '-s', '640x480',                      # Set output resolution to 640x480
        '-c:v', 'libx264',                    # Video codec (H.264)
        '-preset', 'fast',                    # Encoding preset (adjust as needed)
        '-tune', 'zerolatency',               # Low latency for real-time streaming
        '-f', 'mpegts',                       # Output format (MPEG Transport Stream)
        'pipe:1'                              # Output to stdout (pipe)
    ]


    print(f"Starting FFmpeg with command: {' '.join(ffmpeg_command)}")

    # Start FFmpeg as a subprocess and pipe the output to the WebSocket
    process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    try:
        while True:
            # Read the output from FFmpeg (video frames)
            data = process.stdout.read(2048)
            
            if not data:
                print("No data received from FFmpeg, exiting...")
                break
            
            print(f"Sending {len(data)} bytes to WebSocket")

            # Send data to WebSocket client
            await websocket.send(data)
    
    except Exception as e:
        print(f"Error streaming video: {e}")
        error_message = process.stderr.read()
        print(f"FFmpeg Error Output: {error_message.decode('utf-8')}")
    
    finally:
        print("Killing FFmpeg process...")
        process.kill()  # Kill FFmpeg process when done
        print("FFmpeg process terminated.")

async def main():
    server = await websockets.serve(stream_rtsp, 'localhost', 8765)
    print("WebSocket server running on ws://localhost:8765")
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
