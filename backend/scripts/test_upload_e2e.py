import os
import sys
import time
import requests

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

s = requests.Session()
# 1. Login
login_res = s.post('http://127.0.0.1:5000/login', data={'username': 'admin', 'password': 'adminpassword'}, allow_redirects=True)
print('Login Status:', login_res.status_code)

from config import Config

# 2. Upload audio file that matches the existing S3 audio
os.makedirs(Config.UPLOAD_TEMP, exist_ok=True)
temp_audio = os.path.join(Config.UPLOAD_TEMP, 'test_audio.mpeg')

if not os.path.exists(temp_audio):
    from utils import download_from_s3
    print("Downloading sample audio from S3...")
    download_from_s3('audio_097c871b7bf54def9e299bd8a22f25ac.mpeg', temp_audio)



if os.path.exists(temp_audio):
    print(f"Uploading '{temp_audio}' to /upload...")
    with open(temp_audio, 'rb') as f:
        resp = s.post('http://127.0.0.1:5000/upload', files={'file': ('speech_presentation_sample.mpeg', f, 'audio/mpeg')})
    
    print('Upload response:', resp.status_code, resp.json())
    data = resp.json()
    if data.get('status') == 'processing':
        audio_id = data.get('audio_id')
        print(f"Polling status for audio ID {audio_id}...")
        for i in range(20):
            time.sleep(1)
            stat = s.get(f"http://127.0.0.1:5000/audio/status/{audio_id}").json()
            st = stat.get('status')
            sim = stat.get('similarity')
            mf = stat.get('matched_file')
            mt = stat.get('matched_transcript')
            print(f"Poll #{i+1}: status={st}, similarity={sim:.4f} ({sim*100:.2f}%), matched={mf}")
            if st in ('pending_confirmation', 'completed', 'failed'):
                print(f"\n==========================================")
                print(f"IMMEDIATE SIMILARITY DETECTION RESULT:")
                print(f"Status: {st}")
                print(f"Similarity Score: {sim*100:.2f}% Match")
                print(f"Matched Cloud/DB File: {mf}")
                print(f"Matched Transcript Preview: {mt}")
                print(f"==========================================\n")
                break

        # Discard the test upload after verification
        s.post(f"http://127.0.0.1:5000/audio/delete/{audio_id}")
        print("Cleaned up test audio upload.")
else:
    print("test_audio.mpeg not found.")
