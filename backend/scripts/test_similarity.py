import os
import sys

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

import static_ffmpeg
static_ffmpeg.add_paths()

from services.ml_client import ml_client
from mongo_wrapper import get_mongo_connection

conn = get_mongo_connection()
audios = conn.execute('SELECT * FROM audio_records').fetchall()
print('Audios in DB:', len(audios))
for a in audios:
    print('ID:', a['id'], 'File:', a['original_filename'], 'Transcript:', a['transcript'][:60])

# Test similarity with a slightly modified transcript against existing audio
query_text = 'Hi everyone, I am Bhanu Prasad and this is Hypeflow AI. Recruitment today is slow and repetitive and recruiters spend hours reading resumes.'
emb = ml_client.generate_embedding(query_text)
res = ml_client.find_highest_similarity(emb, audios, exclude_id=999, new_transcript=query_text)
print('\n--- Audio Similarity Result ---')
print('Similarity Score:', f"{res['similarity']*100:.2f}%")
print('Matched File:', res.get('matched_filename'))
print('Match Type:', res.get('match_type'))
print('Matched Transcript:', res.get('matched_transcript'))

# Test video similarity
videos = conn.execute('SELECT * FROM video_records').fetchall()
print('\nVideos in DB:', len(videos))
for v in videos:
    print('ID:', v['id'], 'File:', v['original_filename'], 'Transcript:', v['transcript'])

if videos:
    vid1 = videos[0]
    import json
    dino_emb = json.loads(vid1['dino_embedding']) if vid1.get('dino_embedding') else []
    res_vid = ml_client.find_highest_similarity([], videos, exclude_id=999, new_dino_embedding=dino_emb)
    print('\n--- Video Visual Similarity Result ---')
    print('Similarity Score:', f"{res_vid['similarity']*100:.2f}%")
    print('Matched File:', res_vid.get('matched_filename'))
    print('Match Type:', res_vid.get('match_type'))

conn.close()
