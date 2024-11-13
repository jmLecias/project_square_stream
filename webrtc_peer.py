import asyncio
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
from aiortc.contrib.media import MediaPlayer
from firebase_admin import credentials, firestore, initialize_app

# RTSP URLs for different formats
# "rtsp://CAPSTONE:@CAPSTONE2@192.168.254.106:554/live/ch00_0"    # RTSP V380 FORMAT
# "rtsp://CAPSTONE:@CAPSTONE2@192.168.254.106:554/stream1"    # RTSP TAPO FORMAT

# Firebase setup
cred = credentials.Certificate("project-square-f33d7-firebase-adminsdk-76o0v-1c3e419466.json")
initialize_app(cred)
db = firestore.client()

code = "UliEtjEVxzJBJHrhaE89"
rtsp_url = "rtsp://CAPSTONE:@CAPSTONE2@192.168.254.105:554/live/ch00_0"


async def main(doc_id, video_source):
    # Set up Peer Connection and media player
    print("Initializing PeerConnection and MediaPlayer")
    pc = RTCPeerConnection()
    
    print("Initializing MediaPlayer for RTSP stream")
    player = MediaPlayer(
        video_source,
        options={
            "analyzeduration": "10000000",
            "probesize": "10000000",
            "rtsp_transport": "tcp"  # Try forcing TCP transport for RTSP
        }
    )
    print("MediaPlayer initialized:", player)
    print("Audio tracks:", player.audio)
    print("Video tracks:", player.video)
    
    # If player.audio or player.video is not None, you can add tracks
    if player.audio:
        for audio_track in player.audio:
            pc.addTrack(audio_track)
    if player.video:
        for video_track in [player.video]:  # Wrap in list if it's a single track
            pc.addTrack(video_track)

    # Retrieve the offer from Firebase
    print(f"Retrieving offer from Firebase for doc_id: {doc_id}")
    doc_ref = db.collection("calls").document(doc_id)
    call_data = doc_ref.get().to_dict()
    offer = call_data.get("offer")
    if not offer:
        print("Offer not found in Firebase!")
        return

    # Set the remote description with the offer from the browser
    print("Setting remote description")
    await pc.setRemoteDescription(RTCSessionDescription(sdp=offer["sdp"], type=offer["type"]))

    # Create an answer and set it as the local description
    print("Creating and setting local description (answer)")
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    doc_ref.update({"answer": {"type": answer.type, "sdp": answer.sdp}})

    # Listen for incoming ICE candidates in Firestore
    async def add_ice_candidates():
        offer_candidates = doc_ref.collection("offerCandidates")
        
        # Callback function to handle changes
        def callback(doc_snapshot, changes, read_time):
            for doc in doc_snapshot:
                cd = doc.to_dict()
                print(f"Candidate Data: {cd}")
                candidate = RTCIceCandidate(cd['component'], cd['foundation'], cd['ip'], cd['port'], cd['priority'], cd['protocol'], cd['type'])
                
                # Create a new event loop for the background thread and run the coroutine
                loop = asyncio.new_event_loop() 
                asyncio.run_coroutine_threadsafe(pc.addIceCandidate(candidate), loop)  # Add the candidate asynchronously

        # Listen to changes in the Firestore collection
        offer_candidates.on_snapshot(callback)

    # Add local ICE candidates to Firestore
    @pc.on("icecandidate")
    async def on_icecandidate(event):
        if event.candidate:
            print("Sending ICE candidate:", event.candidate)
            doc_ref.collection("answerCandidates").add(event.candidate.to_dict())

    # Handle track reception
    @pc.on("track")
    def on_track(track):
        print("Track received:", track)

    # Run candidate listener in background
    asyncio.create_task(add_ice_candidates())

    # Keep the loop running by awaiting any long-running task
    await asyncio.Event().wait()  # This keeps the event loop alive indefinitely.
    
# Run main function with Firebase document ID and video source
print("Starting main function")
asyncio.run(main(code, rtsp_url))
