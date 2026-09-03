import json
import re
import difflib
import numpy as np
from utils import log_action

def compute_lexical_similarity(t1: str, t2: str) -> float:
    """Computes lexical Jaccard token overlap and SequenceMatcher ratio between two transcripts."""
    if not t1 or not t2:
        return 0.0
    
    # Clean and tokenize
    words1 = set(re.findall(r'\w+', t1.lower()))
    words2 = set(re.findall(r'\w+', t2.lower()))
    
    if not words1 or not words2:
        return 0.0
        
    # Jaccard index
    intersection = len(words1.intersection(words2))
    union = len(words1.union(words2))
    jaccard = intersection / union if union > 0 else 0.0
    
    # Sequence ratio
    seq_ratio = difflib.SequenceMatcher(None, t1.lower().strip(), t2.lower().strip()).ratio()
    
    # Return hybrid lexical score
    return float(max(jaccard, seq_ratio, 0.5 * jaccard + 0.5 * seq_ratio))

class SimilarityService:
    def __init__(self):
        pass

    def find_highest_similarity(self, new_embedding, stored_records, exclude_id=None, table_name="audio_records", new_transcript=None, new_dino_embedding=None):
        """
        Compare new embedding against all stored transcript and visual embeddings using vectorized matrix math + lexical matching.
        Returns:
            dict: {
                "similarity": float (0.0 to 1.0),
                "matched_record": dict (database row fields) or None,
                "match_type": str ("transcript", "visual", or "multimodal"),
                "matched_transcript": str or None,
                "matched_filename": str or None
            }
        """
        log_action("Similarity Calculation Started", f"Comparing against {table_name} records (count: {len(stored_records)}).")
        
        has_text_emb = bool(new_embedding and any(x != 0 for x in new_embedding))
        has_dino_emb = bool(new_dino_embedding and any(x != 0 for x in new_dino_embedding))
        has_transcript = bool(new_transcript and len(new_transcript.strip()) > 3)
        
        if not has_text_emb and not has_dino_emb and not has_transcript:
            return {"similarity": 0.0, "matched_record": None, "match_type": "transcript", "matched_transcript": None, "matched_filename": None}

        if not stored_records:
            log_action("Highest Similarity Found", f"No existing records to compare against.")
            return {"similarity": 0.0, "matched_record": None, "match_type": "transcript", "matched_transcript": None, "matched_filename": None}

        # Filter out excluded record if any
        candidate_records = []
        for r in stored_records:
            if exclude_id is not None and str(r.get('id')) == str(exclude_id):
                continue
            candidate_records.append(r)

        if not candidate_records:
            return {"similarity": 0.0, "matched_record": None, "match_type": "transcript", "matched_transcript": None, "matched_filename": None}

        # Prepare normalized query vectors
        q_text = None
        if has_text_emb:
            q_text = np.array(new_embedding, dtype=np.float32)
            norm = np.linalg.norm(q_text)
            if norm > 0:
                q_text = q_text / norm
            else:
                q_text = None

        q_dino = None
        if has_dino_emb:
            q_dino = np.array(new_dino_embedding, dtype=np.float32)
            norm = np.linalg.norm(q_dino)
            if norm > 0:
                q_dino = q_dino / norm
            else:
                q_dino = None

        n_records = len(candidate_records)
        text_scores = np.zeros(n_records, dtype=np.float32)
        dino_scores = np.zeros(n_records, dtype=np.float32)
        lexical_scores = np.zeros(n_records, dtype=np.float32)

        text_vecs = []
        text_indices = []
        dino_vecs = []
        dino_indices = []

        for idx, record in enumerate(candidate_records):
            # 1. Lexical comparison on raw transcripts
            stored_t = record.get('transcript')
            if has_transcript and stored_t and isinstance(stored_t, str) and not stored_t.startswith("Processing") and not stored_t.startswith("No speech"):
                lex_sim = compute_lexical_similarity(new_transcript, stored_t)
                lexical_scores[idx] = lex_sim

            # 2. Text embedding
            if q_text is not None:
                stored_emb_str = record.get('embedding')
                if stored_emb_str:
                    try:
                        emb = json.loads(stored_emb_str) if isinstance(stored_emb_str, str) else stored_emb_str
                        if emb and isinstance(emb, list) and len(emb) > 0 and any(x != 0 for x in emb):
                            text_vecs.append(emb)
                            text_indices.append(idx)
                    except Exception:
                        pass
                        
            # 3. DINO embedding
            if q_dino is not None:
                stored_dino_str = record.get('dino_embedding')
                if stored_dino_str:
                    try:
                        dino_emb = json.loads(stored_dino_str) if isinstance(stored_dino_str, str) else stored_dino_str
                        if dino_emb and isinstance(dino_emb, list) and len(dino_emb) > 0 and any(x != 0 for x in dino_emb):
                            dino_vecs.append(dino_emb)
                            dino_indices.append(idx)
                    except Exception:
                        pass

        # Batch compute text similarities
        if q_text is not None and text_vecs:
            try:
                T = np.array(text_vecs, dtype=np.float32)
                T_norms = np.linalg.norm(T, axis=1, keepdims=True)
                T_norms[T_norms == 0] = 1.0
                T_normalized = T / T_norms
                sims = np.dot(T_normalized, q_text)
                for i, score in enumerate(sims):
                    text_scores[text_indices[i]] = float(score)
            except Exception as e:
                print(f"[SimilarityService] Batch text similarity error: {e}")

        # Batch compute DINO similarities
        if q_dino is not None and dino_vecs:
            try:
                D = np.array(dino_vecs, dtype=np.float32)
                D_norms = np.linalg.norm(D, axis=1, keepdims=True)
                D_norms[D_norms == 0] = 1.0
                D_normalized = D / D_norms
                sims = np.dot(D_normalized, q_dino)
                for i, score in enumerate(sims):
                    dino_scores[dino_indices[i]] = float(score)
            except Exception as e:
                print(f"[SimilarityService] Batch DINO similarity error: {e}")

        # Combined speech transcript score (blend of semantic and lexical)
        transcript_scores = np.maximum(text_scores, lexical_scores)
        
        # Overall combined scores
        combined_scores = np.maximum(transcript_scores, dino_scores)
        
        if len(combined_scores) == 0 or np.max(combined_scores) <= 0:
            return {"similarity": 0.0, "matched_record": None, "match_type": "transcript", "matched_transcript": None, "matched_filename": None}

        best_idx = int(np.argmax(combined_scores))
        highest_similarity = float(np.clip(combined_scores[best_idx], 0.0, 1.0))
        best_match = candidate_records[best_idx]
        
        if dino_scores[best_idx] > transcript_scores[best_idx]:
            match_type = "visual"
        elif dino_scores[best_idx] > 0.4 and transcript_scores[best_idx] > 0.4:
            match_type = "multimodal"
        else:
            match_type = "transcript"

        matched_fn = best_match.get('original_filename') or best_match.get('file_name')
        matched_tr = best_match.get('transcript')

        log_action("Highest Similarity Found", f"Score: {highest_similarity * 100:.2f}% | File: {matched_fn} | Type: {match_type}")
        
        return {
            "similarity": highest_similarity,
            "matched_record": best_match,
            "match_type": match_type,
            "matched_transcript": matched_tr,
            "matched_filename": matched_fn
        }

similarity_service = SimilarityService()


