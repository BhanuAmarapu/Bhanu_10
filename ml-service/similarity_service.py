import json
import numpy as np
from utils import log_action

def cosine_similarity(v1, v2):
    """Calculate the cosine similarity between two numeric vectors."""
    a = np.array(v1)
    b = np.array(v2)
    if a.size == 0 or b.size == 0:
        return 0.0
    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot_product / (norm_a * norm_b))

class SimilarityService:
    def __init__(self):
        pass

    def find_highest_similarity(self, new_embedding, stored_records, exclude_id=None, table_name="audio_records", new_transcript=None, new_dino_embedding=None):
        """
        Compare new embedding against all stored transcript and visual embeddings in target table.
        Returns:
            dict: {
                "similarity": float (0.0 to 1.0),
                "matched_record": dict (database row fields) or None,
                "match_type": str ("transcript" or "visual")
            }
        """
        log_action("Similarity Calculation Started", f"Comparing uploaded embedding against {table_name} records (provided: {len(stored_records)}).")
        
        if not new_embedding:
            return {"similarity": 0.0, "matched_record": None, "match_type": "transcript"}
            
        if new_transcript:
            from sentencebert_service import sentencebert_service
            norm_t = sentencebert_service.normalize_text(new_transcript)
            if len(norm_t.split()) < 5 or len(norm_t) < 15:
                if not new_dino_embedding:
                    log_action("Similarity Check Skipped", f"New transcript too short and no visual embedding provided: '{new_transcript}'")
                    return {"similarity": 0.0, "matched_record": None, "match_type": "transcript"}
                else:
                    new_transcript = None

        if not stored_records:
            log_action("Highest Similarity Found", f"No existing records to compare against.")
            return {"similarity": 0.0, "matched_record": None, "match_type": "transcript"}

        highest_similarity = 0.0
        best_match = None
        match_type = "transcript"

        for record in stored_records:
            try:
                transcript_sim = 0.0
                if new_transcript:
                    stored_transcript = record.get('transcript')
                    skip_transcript = False
                    if stored_transcript:
                        from sentencebert_service import sentencebert_service
                        norm_stored = sentencebert_service.normalize_text(stored_transcript)
                        if len(norm_stored.split()) < 5 or len(norm_stored) < 15:
                            skip_transcript = True
                    else:
                        skip_transcript = True

                    if not skip_transcript:
                        stored_emb_str = record.get('embedding')
                        if stored_emb_str:
                            stored_emb = json.loads(stored_emb_str) if isinstance(stored_emb_str, str) else stored_emb_str
                            transcript_sim = cosine_similarity(new_embedding, stored_emb)

                dino_sim = 0.0
                if new_dino_embedding:
                    stored_dino_str = record.get('dino_embedding')
                    if stored_dino_str:
                        stored_dino = json.loads(stored_dino_str) if isinstance(stored_dino_str, str) else stored_dino_str
                        dino_sim = cosine_similarity(new_dino_embedding, stored_dino)

                similarity = max(transcript_sim, dino_sim)
                if similarity > highest_similarity:
                    highest_similarity = similarity
                    best_match = record
                    match_type = "visual" if dino_sim > transcript_sim else "transcript"
            except Exception as e:
                rec_id = record['id'] if ('id' in record or hasattr(record, '__getitem__')) else 'unknown'
                print(f"[SimilarityService] Error comparing record ID {rec_id}: {e}")
                continue

        log_action("Highest Similarity Found", f"Score: {highest_similarity * 100:.2f}% | File: {best_match['original_filename'] if best_match else 'None'} | Type: {match_type}")
        
        return {
            "similarity": highest_similarity,
            "matched_record": best_match,
            "match_type": match_type
        }

similarity_service = SimilarityService()

