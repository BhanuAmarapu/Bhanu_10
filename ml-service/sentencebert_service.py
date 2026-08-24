import os
import re
import string
import torch
from sentence_transformers import SentenceTransformer
from utils import log_action

class SentenceBERTService:
    def __init__(self):
        self.model = None

    def load_model(self):
        """Loads Sentence-BERT model only once and caches it in memory."""
        if self.model is None:
            # Configurable model name, default to all-MiniLM-L6-v2
            model_name = os.getenv('SENTENCE_BERT_MODEL', 'all-MiniLM-L6-v2')
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"[SentenceBERTService] Loading model '{model_name}' on {device}...")
            try:
                # Try loading locally first for speed and offline robustness
                print(f"[SentenceBERTService] Attempting local-first load for model '{model_name}'...")
                self.model = SentenceTransformer(model_name, device=device, local_files_only=True)
            except Exception as local_err:
                print(f"[SentenceBERTService] Local SentenceTransformer load failed: {local_err}. Trying online loading...")
                try:
                    self.model = SentenceTransformer(model_name, device=device)
                except Exception as e:
                    print(f"[SentenceBERTService] Online SentenceTransformer load failed: {e}")
                    raise e
            print("[SentenceBERTService] Model loaded successfully.")
        return self.model

    def normalize_text(self, text):
        """
        Normalizes text according to the target guidelines:
        - Convert to lowercase
        - Remove punctuation
        - Normalize whitespace
        - Remove unnecessary formatting
        """
        if not text:
            return ""
        
        # 1. Convert to lowercase
        text = text.lower()
        
        # 2. Remove punctuation (keep spaces and alphanumeric characters)
        # Using string.punctuation translate
        text = text.translate(str.maketrans('', '', string.punctuation))
        
        # 3. Normalize whitespace (replace multiple spaces/newlines/tabs with single space, strip)
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text

    def generate_embedding(self, text):
        """
        Generates and returns semantic embedding for normalized text.
        Returns a list of float values.
        """
        if not text:
            return []
            
        log_action("Sentence-BERT Embedding Generated", f"Text preview: {text[:50]}...")
        
        # Normalize text first
        normalized = self.normalize_text(text)
        
        # Ensure model is loaded
        self.load_model()
        
        # Generate embedding
        try:
            embedding = self.model.encode(normalized, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as e:
            raise RuntimeError(f"Sentence-BERT embedding generation failed: {e}")

sentencebert_service = SentenceBERTService()
