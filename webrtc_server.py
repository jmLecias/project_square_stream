import asyncio
import json
import websockets
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
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

    pc.on("iceconnectionstatechange", lambda: print(f"ICE connection state: {pc.iceConnectionState}"))

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
            sdp_mid = candidate.get("sdpMid", "")
            sdp_mline_index = candidate.get("sdpMLineIndex", 0)

            # print(f"Candidate data: {candidate}") # Candidate data: {'candidate': 'candidate:673270360 1 udp 2122194687 192.168.137.1 53936 typ host generation 0 ufrag oV8u network-id 1 network-cost 10', 'sdpMid': '6', 'sdpMLineIndex': 0, 'usernameFragment': 'oV8u'}
            
            candidate_str = candidate.get('candidate', '')
            candidate_parts = candidate_str.split()

            # Ensure we have enough parts in the candidate string
            if len(candidate_parts) >= 8:
                ice_candidate = RTCIceCandidate(
                    foundation=candidate_parts[0].split(":")[1],  # 'candidate:673270360' -> '673270360'
                    component=int(candidate_parts[1]),
                    protocol=candidate_parts[2],
                    priority=int(candidate_parts[3]),
                    ip=candidate_parts[4],
                    port=int(candidate_parts[5]),
                    type=candidate_parts[7],
                    sdpMid=sdp_mid,
                    sdpMLineIndex=sdp_mline_index
                )
                await pc.addIceCandidate(ice_candidate)
            else:
                print("Candidate string does not have enough parts:", candidate_str)

    await pc.close()
    connected_clients.remove(websocket)
    print("Client disconnected")


async def main():
    start_server = websockets.serve(handle_signaling, "0.0.0.0", 8765)
    print("WebSocket server started at ws://localhost:8765")

    server = await start_server
    await server.wait_closed() 

if __name__ == "__main__":
    asyncio.run(main())