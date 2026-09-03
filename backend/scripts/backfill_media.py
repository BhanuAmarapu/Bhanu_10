import os
import sys
import json
import shutil

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

import static_ffmpeg
static_ffmpeg.add_paths()

from config import Config
from mongo_wrapper import get_mongo_connection
from services.ml_client import ml_client
from utils import download_from_s3

def main():
    print("Connecting to MongoDB for media backfill...")
    conn = get_mongo_connection()
    
    # 1. Backfill audio_records
    all_audios = conn.execute("SELECT * FROM audio_records").fetchall()
    print(f"Total audio records: {len(all_audios)}")
    for a in all_audios:
        aid = a['id']
        fname = a['original_filename']
        s3_key = a.get('s3_object_key') or a.get('uuid_filename')
        print(f"\nProcessing Audio ID {aid}: {fname} (S3 key: {s3_key})")
        
        temp_audio_path = os.path.join(Config.UPLOAD_TEMP, f"manual_audio_{aid}_{fname}")
        local_stored = os.path.join(Config.UPLOAD_STORED, s3_key)
        
        try:
            found = False
            if os.path.exists(local_stored):
                print(f"  Found local stored file at {local_stored}")
                shutil.copy2(local_stored, temp_audio_path)
                found = True
            elif Config.USE_S3:
                print(f"  Downloading {s3_key} from S3...")
                if download_from_s3(s3_key, temp_audio_path):
                    print(f"  Downloaded from S3 successfully ({os.path.getsize(temp_audio_path)} bytes)")
                    found = True
                else:
                    print("  Failed to download from S3.")
                    
            if found and os.path.exists(temp_audio_path):
                print("  Transcribing audio via ML service...")
                res = ml_client.transcribe(temp_audio_path)
                transcript = res.get("transcript", "")
                lang = res.get("language", "en")
                dur = float(res.get("duration", 0.0))
                print(f"  Transcript: '{transcript}' (Language: {lang}, Duration: {dur}s)")
                
                emb = ml_client.generate_embedding(transcript) if transcript else []
                print(f"  Generated SBERT embedding (dim: {len(emb)})")
                
                conn.execute("""
                    UPDATE audio_records 
                    SET transcript = ?, embedding = ?, language = ?, duration = ?, status = 'completed', similarity_score = 0.0
                    WHERE id = ?
                """, (transcript, json.dumps(emb), lang, dur, aid))
                conn.commit()
                print(f"  Updated Audio ID {aid} in database -> status: completed.")
        except Exception as e:
            print(f"  Error processing Audio ID {aid}: {e}")
        finally:
            if os.path.exists(temp_audio_path):
                try: os.remove(temp_audio_path)
                except: pass

    # 2. Backfill video_records
    all_videos = conn.execute("SELECT * FROM video_records").fetchall()
    print(f"\nTotal video records: {len(all_videos)}")
    for v in all_videos:
        vid = v['id']
        fname = v['original_filename']
        s3_key = v.get('s3_object_key') or v.get('uuid_filename')
        print(f"\nProcessing Video ID {vid}: {fname} (S3 key: {s3_key})")
        
        temp_video_path = os.path.join(Config.UPLOAD_TEMP, f"manual_video_{vid}_{fname}")
        local_stored = os.path.join(Config.UPLOAD_STORED, s3_key)
        
        try:
            found = False
            if os.path.exists(local_stored):
                print(f"  Found local stored file at {local_stored}")
                shutil.copy2(local_stored, temp_video_path)
                found = True
            elif Config.USE_S3:
                print(f"  Downloading {s3_key} from S3...")
                if download_from_s3(s3_key, temp_video_path):
                    print(f"  Downloaded from S3 successfully ({os.path.getsize(temp_video_path)} bytes)")
                    found = True
                else:
                    print("  Failed to download from S3.")
                    
            if found and os.path.exists(temp_video_path):
                print("  Processing video via ML service...")
                video_res = ml_client.process_video(temp_video_path)
                transcript = video_res.get("transcript", "No speech detected in video track.")
                lang = video_res.get("language", "en")
                dur = float(video_res.get("duration", 0.0))
                emb = video_res.get("embedding", [])
                dino_emb = video_res.get("dino_embedding", [])
                print(f"  Video transcript: '{transcript}', DINO embedding dim: {len(dino_emb)}")
                
                conn.execute("""
                    UPDATE video_records 
                    SET transcript = ?, embedding = ?, dino_embedding = ?, language = ?, duration = ?, status = 'completed', similarity_score = 0.0
                    WHERE id = ?
                """, (transcript, json.dumps(emb), json.dumps(dino_emb), lang, dur, vid))
                conn.commit()
                print(f"  Updated Video ID {vid} in database -> status: completed.")
        except Exception as e:
            print(f"  Error processing Video ID {vid}: {e}")
        finally:
            if os.path.exists(temp_video_path):
                try: os.remove(temp_video_path)
                except: pass

    conn.close()
    print("\nMedia backfill script finished successfully!")

if __name__ == '__main__':
    main()
