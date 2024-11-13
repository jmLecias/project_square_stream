import asyncio
import json
import websockets
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer
from rtsp_stream_track import RTSPVideoStreamTrack

# rtsp://CAPSTONE:@CAPSTONE2@192.168.1.89:554/live/ch00_0

# Track connections to manage multiple clients
connected_clients = set()   

# Create a placeholder RTCPeerConnection
async def handle_signaling(websocket):
    print("Client connected")
    
    connected_clients.add(websocket)

    pc = RTCPeerConnection()

    # Create RTSP stream track and add it to the peer connection
    rtsp_url = "rtsp://CAPSTONE:@CAPSTONE2@192.168.1.89:554/live/ch00_0"
    video_track = RTSPVideoStreamTrack(rtsp_url)
    print(f"Track direction: {video_track.direction}")
    pc.addTrack(video_track)

    async for message in websocket:
        data = json.loads(message)
        print("Received message:", data)

        # 1. Handle SDP offer from the client
        if data["type"] == "offer":
            print("Received SDP offer:", data["sdp"]) # To check SDP offer received
            offer = RTCSessionDescription(sdp=data["sdp"], type=data["type"])
            await pc.setRemoteDescription(offer)

            # Create and send SDP answer back to the client
            answer = await pc.createAnswer()
            print("SDP answer:", answer)
            await pc.setLocalDescription(answer)

            await websocket.send(json.dumps({
                "sdp": pc.localDescription.sdp,
                "type": pc.localDescription.type
            }))

        # 2. Handle ICE candidate from the client
        elif data["type"] == "ice-candidate" and data["candidate"]:
            candidate = data["candidate"]
            ice_candidate = {
                "sdpMid": candidate["sdpMid"],
                "sdpMLineIndex": candidate["sdpMLineIndex"],
                "candidate": candidate["candidate"]
            }
            await pc.addIceCandidate(ice_candidate)

    await pc.close()
    connected_clients.remove(websocket)
    print("Client disconnected")


async def main():
    start_server = websockets.serve(handle_signaling, "localhost", 8765)
    print("WebSocket server started at ws://localhost:8765")

    server = await start_server
    await server.wait_closed() 

if __name__ == "__main__":
    asyncio.run(main())