# Walkthrough: Video Speech Extraction & Similarity Pipeline

I have implemented speech-to-text extraction, SBERT semantic embedding generation, similarity checks, and AJAX polling for video files—matching the existing audio deduplication pipeline.

---

## Technical Implementations

### 1. Video Speech Similarity Pipeline
- **Database Schema ([app.py](file:///c:/Users/amara/Workspace/final01/main-project-main/app.py))**:
  - Dynamically altered the `video_records` table on startup to add fields: `transcript`, `embedding`, `language`, `duration`, `similarity_score`, `status`, `matched_file`, and `matched_transcript`.
- **Background Pipeline**:
  - Replaced the synchronous video upload handler to run asynchronously in a daemon thread.
  - Video uploads are synced to **AWS S3** immediately within seconds.
  - **FFmpeg Integration**: The background thread executes FFmpeg to extract the audio track from the video as a 16kHz mono `.mp3` file:
    `ffmpeg -y -i <video_path> -vn -acodec libmp3lame -ar 16000 -ac 1 <temp_audio_path>`
  - **Whisper & SBERT Execution**: Transcribes speech with Whisper ASR, generates semantic vector embeddings using SBERT, and calculates cosine similarity against existing transcripts in the `video_records` database table.
  - Sets the status to `'pending_confirmation'` if similarity $\ge 60\%$, else `'completed'`.
- **Status API Endpoint**:
  - Added `/video/status/<int:video_id>` and `/video/confirm_store/<int:video_id>`.

### 2. Frontend Polling & Confirmation
- **AJAX Polling ([templates/upload.html](file:///c:/Users/amara/Workspace/final01/main-project-main/templates/upload.html))**:
  - When a video is uploaded, Javascript initiates a 2-second interval loop querying `/video/status/<id>`.
  - Dynamically updates the AI loader screen text to reflect video processing details.
  - Displays the confirmation modal if similarity $\ge 60\%$, dynamically customizing prompt texts (e.g. *"Similar Video Found"*, *"Do you want to store this video?"*).
- **Dashboard Representation ([templates/dashboard.html](file:///c:/Users/amara/Workspace/final01/main-project-main/templates/dashboard.html))**:
  - Restructured the Videos tab to show symmetric info (Status, Duration, Highest Similarity %, Transcript Preview, and Actions).
  - Displays **Store anyway** and **Cancel** buttons next to pending videos.

---

## Verification Results

### Automated Integration Tests
- **Video transcription polling test**: Created [test_video_transcription_polling.py](file:///C:/Users/amara/.gemini/antigravity-ide/brain/495435b1-c8b8-4c07-9c75-1ca84e9d5fa3/scratch/test_video_transcription_polling.py):
  ```
  --- Testing upload video file (Immediate async response) ---
  [AsyncVideo] Uploaded my_movie.mp4 to S3 immediately.
  [AsyncVideo] Extracting audio track using command: ffmpeg -y -i ... -vn -acodec libmp3lame -ar 16000 -ac 1 ...
  [AsyncVideo] Audio track successfully extracted. Running Whisper transcription...
  Upload response: 200 - {'message': 'Video file uploaded and is being processed in the background.', 'status': 'processing', 'video_id': 401}

  --- Testing video poll status 1 (Processing) ---
  Poll 1 response: 200 - {'matched_file': None, 'matched_transcript': None, 'similarity': None, 'status': 'processing'}

  --- Testing video poll status 2 (Pending Confirmation) ---
  Poll 2 response: 200 - {'matched_file': 'previous_video.mp4', 'matched_transcript': 'this is video transcript', 'similarity': 0.82, 'status': 'pending_confirmation'}

  [OK] Video speech extraction, transcription, and polling flow tests passed!
  ```
- **Audio Polling Test**: [test_polling_deduplication.py](file:///C:/Users/amara/.gemini/antigravity-ide/brain/495435b1-c8b8-4c07-9c75-1ca84e9d5fa3/scratch/test_polling_deduplication.py) runs and completes.

All tests passed successfully and changes have been pushed to GitHub.
