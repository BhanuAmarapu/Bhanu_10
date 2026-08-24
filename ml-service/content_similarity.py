"""
Content-Level Similarity Detection Module
Detects near-duplicate files based on content similarity (90%+ match)
even when files have different names or sizes.
"""
from sentence_transformers import SentenceTransformer, util
import torch
import pickle
import os
from config import Config

try:
    from PIL import Image
except ImportError:
    print("WARNING: PIL not installed.")

import base64
from openai import OpenAI


class SBERTModel:
    """Singleton for SBERT model to avoid reloading"""
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            print("[DEBUG] Loading Sentence-BERT model (all-MiniLM-L6-v2)...")
            # Force CPU for stability in diverse environments unless CUDA is explicitly needed
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            try:
                cls._instance = SentenceTransformer('all-MiniLM-L6-v2', device=device)
            except Exception as e:
                print(f"[DEBUG] SBERT online load failed: {e}. Retrying with local_files_only=True...")
                try:
                    cls._instance = SentenceTransformer('all-MiniLM-L6-v2', device=device, local_files_only=True)
                except Exception as inner_e:
                    print(f"[DEBUG] SBERT local cache load failed: {inner_e}")
                    raise inner_e
        return cls._instance


class DINOv2Model:
    """Singleton for DINOv2 model for image similarity"""
    _instance = None
    _processor = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            print("[DEBUG] Loading DINOv2 model (facebook/dinov2-small)...")
            from transformers import AutoImageProcessor, AutoModel
            import torch
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            try:
                cls._processor = AutoImageProcessor.from_pretrained('facebook/dinov2-small')
                cls._instance = AutoModel.from_pretrained('facebook/dinov2-small').to(device)
            except Exception as e:
                print(f"[DEBUG] DINOv2 online load failed: {e}. Retrying with local_files_only=True...")
                try:
                    cls._processor = AutoImageProcessor.from_pretrained('facebook/dinov2-small', local_files_only=True)
                    cls._instance = AutoModel.from_pretrained('facebook/dinov2-small', local_files_only=True).to(device)
                except Exception as inner_e:
                    print(f"[DEBUG] DINOv2 local cache load failed: {inner_e}")
                    raise inner_e
        return cls._instance, cls._processor


class ContentSimilarityDetector:
    """Detect content-level similarity for files using SBERT"""
    
    # Class-level cache to persist across multiple uploads
    _embedding_cache = {}
    _cache_file = os.path.join(Config.BASE_DIR, 'ml_data', 'embedding_cache.pkl')
    _cache_loaded = False
    
    _dino_embedding_cache = {}
    _dino_cache_file = os.path.join(Config.BASE_DIR, 'ml_data', 'dino_cache.pkl')
    _dino_cache_loaded = False
    
    def __init__(self, similarity_threshold=0.60, image_similarity_threshold=0.90):
        """
        Initialize content similarity detector
        
        Args:
            similarity_threshold: Minimum similarity score (0-1) to consider text files similar
            image_similarity_threshold: Minimum similarity score (0-1) to consider images similar
        """
        self.similarity_threshold = similarity_threshold
        self.image_similarity_threshold = image_similarity_threshold
        self.model = SBERTModel.get_instance()
        self.dino_model, self.dino_processor = DINOv2Model.get_instance()
        
        # Load persistent cache if not already loaded
        if not ContentSimilarityDetector._cache_loaded:
            try:
                if os.path.exists(ContentSimilarityDetector._cache_file):
                    with open(ContentSimilarityDetector._cache_file, 'rb') as f:
                        ContentSimilarityDetector._embedding_cache = pickle.load(f)
                    print(f"[DEBUG] Loaded {len(ContentSimilarityDetector._embedding_cache)} embeddings from persistent cache")
            except Exception as e:
                print(f"[DEBUG] Error loading embedding cache: {e}")
            ContentSimilarityDetector._cache_loaded = True

        if not ContentSimilarityDetector._dino_cache_loaded:
            try:
                if os.path.exists(ContentSimilarityDetector._dino_cache_file):
                    with open(ContentSimilarityDetector._dino_cache_file, 'rb') as f:
                        ContentSimilarityDetector._dino_embedding_cache = pickle.load(f)
                    print(f"[DEBUG] Loaded {len(ContentSimilarityDetector._dino_embedding_cache)} DINOv2 embeddings from cache")
            except Exception as e:
                print(f"[DEBUG] Error loading DINOv2 cache: {e}")
            ContentSimilarityDetector._dino_cache_loaded = True
        
        # Text file extensions to process
        self.text_extensions = {
            'txt', 'md', 'py', 'js', 'java', 'cpp', 'c', 'h', 
            'html', 'css', 'json', 'xml', 'csv', 'log', 'sql', 'pdf'
        }
        
        # Image file extensions to process
        self.image_extensions = {
            'png', 'jpg', 'jpeg', 'webp', 'gif'
        }
    
    def is_text_file(self, filename):
        """Check if file is a text file based on extension"""
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        return ext in self.text_extensions
    
    def extract_text_from_pdf(self, file_path):
        """
        Extract text content from PDF file
        
        Args:
            file_path: Path to PDF file
            
        Returns:
            Extracted text as string, or None if error
        """
        try:
            import PyPDF2
            text = ""
            with open(file_path, 'rb') as pdf_file:
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                num_pages = len(pdf_reader.pages)
                print(f"[DEBUG] PDF has {num_pages} pages")
                
                for page_num in range(num_pages):
                    page = pdf_reader.pages[page_num]
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                
                print(f"[DEBUG] Extracted {len(text)} characters from PDF")
                return text if text.strip() else None
        except Exception as e:
            print(f"[DEBUG] Error extracting text from PDF {file_path}: {e}")
            return None
    
    def read_file_content(self, file_path):
        """
        Read file content as text
        
        Args:
            file_path: Path to file
            
        Returns:
            File content as string, or None if error
        """
        lower_path = file_path.lower()
        
        # Check if it's an image file
        if lower_path.endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
            try:
                # Initialize OpenAI client only if API key is provided
                if not getattr(Config, 'OPENAI_API_KEY', None):
                    print("[WARNING] OPENAI_API_KEY is not set. Image analysis skipped.")
                    return None
                    
                client = OpenAI(api_key=Config.OPENAI_API_KEY)
                
                with open(file_path, "rb") as image_file:
                    base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                    
                mime_type = "image/jpeg"
                if lower_path.endswith('.png'): mime_type = "image/png"
                elif lower_path.endswith('.webp'): mime_type = "image/webp"
                elif lower_path.endswith('.gif'): mime_type = "image/gif"
                
                print(f"[DEBUG] Sending image {file_path} to GPT-4 Vision for analysis...")
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an AI assistant that analyzes images to help with deduplication. You extract any text present in the image and describe the visual content (objects, layout, structure). Return a unified text representation containing both extracted text and your visual description."
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Analyze this image and extract all text and describe its visual components."},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{mime_type};base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=500
                )
                result_text = response.choices[0].message.content
                print(f"[DEBUG] GPT-4 Vision analysis completed for {file_path}")
                return result_text if result_text and result_text.strip() else None
            except Exception as e:
                print(f"[DEBUG] Error extracting text/visuals from image {file_path} using GPT-4 Vision: {e}")
                return None
                
        # Check if it's a PDF file
        if lower_path.endswith('.pdf'):
            return self.extract_text_from_pdf(file_path)
        
        # For text files, read normally
        try:
            # Try UTF-8 first
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            try:
                # Fallback to latin-1
                with open(file_path, 'r', encoding='latin-1') as f:
                    return f.read()
            except Exception as e:
                print(f"Error reading file {file_path}: {e}")
                return None
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return None
    
    def compute_text_similarity(self, text1, text2):
        """
        Compute similarity between two text strings using Sentence-BERT
        
        Args:
            text1: First text string
            text2: Second text string
            
        Returns:
            Similarity score (0-1)
        """
        if not text1 or not text2:
            return 0.0
        
        try:
            # Encode texts to get dense embeddings
            embeddings = self.model.encode([text1, text2], convert_to_tensor=True)
            
            # Compute cosine similarity
            similarity = util.cos_sim(embeddings[0], embeddings[1])
            
            return float(similarity.item())
        except Exception as e:
            print(f"Error computing SBERT similarity: {e}")
            return 0.0
    
    def is_image_file(self, filename):
        """Check if file is an image file based on extension"""
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        return ext in self.image_extensions

    def compute_dinov2_embedding(self, file_path):
        """Compute DINOv2 image embedding"""
        try:
            from PIL import Image
            import torch
            image = Image.open(file_path).convert('RGB')
            inputs = self.dino_processor(images=image, return_tensors="pt")
            
            # Move to device if needed
            device = next(self.dino_model.parameters()).device
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.dino_model(**inputs)
                
            # Use the CLS token representation as the image embedding
            last_hidden_states = outputs.last_hidden_state
            image_embedding = last_hidden_states[:, 0, :]
            return image_embedding
        except Exception as e:
            print(f"[DEBUG] Error computing DINOv2 embedding for {file_path}: {e}")
            return None

    def find_similar_files(self, file_path, filename, current_hash, existing_files):
        """
        Find files with similar content using SBERT for text and DINOv2 for images
        
        Args:
            file_path: Path to uploaded file
            filename: Name of uploaded file
            current_hash: Hash of current file (to exclude exact duplicates)
            existing_files: List of existing files from DB to compare against
            
        Returns:
            List of similar files with similarity scores
        """
        print(f"\n[DEBUG] Semantic Similarity Detection Started")
        print(f"[DEBUG] Checking file: {filename}")
        
        is_text = self.is_text_file(filename)
        is_image = self.is_image_file(filename)
        
        if not is_text and not is_image:
            print(f"[DEBUG] File {filename} is NOT a text or image file - skipping")
            return []
            
        new_embedding = None
        new_dino_embedding = None
        
        if is_image:
            print(f"[DEBUG] Extracting DINOv2 embedding for image: {filename}")
            new_dino_embedding = self.compute_dinov2_embedding(file_path)
            if new_dino_embedding is None:
                print(f"[DEBUG] Could not extract DINOv2 embedding from {file_path}")
                return []
                
            # Also extract text using GPT-4 Vision for multimodal analysis, but similarity will be DINO
            self.read_file_content(file_path) # Just to log it, though not strictly needed here
        
        elif is_text:
            # Read content of uploaded file
            new_content = self.read_file_content(file_path)
            if not new_content:
                print(f"[DEBUG] Could not read content from {file_path}")
                return []
            
            print(f"[DEBUG] Successfully read {len(new_content)} characters from uploaded file")
            # Encode new content once
            new_embedding = self.model.encode(new_content, convert_to_tensor=True)
        
        import torch
        print(f"[DEBUG] Found {len(existing_files)} existing files to compare")
        
        similar_files = []
        batch_texts = []
        batch_metadata = []
        
        # Process in batches for efficiency
        BATCH_SIZE = 32 # Adjust based on memory/GPU
        
        for file_row in existing_files:
            existing_filename = file_row['file_name']
            file_id = file_row['id']
            
            if is_image and self.is_image_file(existing_filename):
                if file_id in ContentSimilarityDetector._dino_embedding_cache:
                    cached_dino = ContentSimilarityDetector._dino_embedding_cache[file_id]
                    import torch.nn.functional as F
                    similarity_score = F.cosine_similarity(new_dino_embedding, cached_dino).item()
                    
                    if similarity_score >= self.image_similarity_threshold:
                        print(f"[DEBUG] ✓ DINO CACHE MATCH FOUND! {existing_filename} is {similarity_score:.2%} similar")
                        similar_files.append({
                            'id': file_row['id'],
                            'file_name': file_row['file_name'],
                            'file_size': file_row['file_size'],
                            'file_hash': file_row['file_hash'],
                            'upload_timestamp': file_row['upload_timestamp'],
                            'stored_path': file_row['stored_path'],
                            'similarity': similarity_score
                        })
                # If an image is not in cache, we skip it since computing it would require fetching from S3/disk
                
            elif is_text and self.is_text_file(existing_filename):
                existing_content = file_row['content_text']
                if existing_content:
                    if file_id in ContentSimilarityDetector._embedding_cache:
                        # Compute similarity directly from cache
                        cached_embedding = ContentSimilarityDetector._embedding_cache[file_id]
                        cos_scores = util.cos_sim(new_embedding, cached_embedding)[0]
                        similarity_score = float(cos_scores[0].item())
                        if similarity_score >= self.similarity_threshold:
                            print(f"[DEBUG] ✓ SBERT CACHE MATCH FOUND! {existing_filename} is {similarity_score:.2%} similar")
                            similar_files.append({
                                'id': file_row['id'],
                                'file_name': file_row['file_name'],
                                'file_size': file_row['file_size'],
                                'file_hash': file_row['file_hash'],
                                'upload_timestamp': file_row['upload_timestamp'],
                                'stored_path': file_row['stored_path'],
                                'similarity': similarity_score
                            })
                    else:
                        batch_texts.append(existing_content)
                        batch_metadata.append(file_row)
                
            if len(batch_texts) >= BATCH_SIZE:
                self._process_batch(new_embedding, batch_texts, batch_metadata, similar_files)
                batch_texts = []
                batch_metadata = []
        
        # Process remaining files
        if batch_texts:
            self._process_batch(new_embedding, batch_texts, batch_metadata, similar_files)
            
        print(f"[DEBUG] Completed comparison, found {len(similar_files)} matches")
        
        # Sort by similarity (highest first)
        similar_files.sort(key=lambda x: x['similarity'], reverse=True)
        
        return similar_files[:5]  # Return top 5 most similar

    def add_dino_cache(self, file_id, file_path):
        """Add image to DINOv2 cache after successful upload"""
        if self.is_image_file(file_path):
            embedding = self.compute_dinov2_embedding(file_path)
            if embedding is not None:
                ContentSimilarityDetector._dino_embedding_cache[file_id] = embedding
                try:
                    os.makedirs(os.path.dirname(ContentSimilarityDetector._dino_cache_file), exist_ok=True)
                    with open(ContentSimilarityDetector._dino_cache_file, 'wb') as f:
                        pickle.dump(ContentSimilarityDetector._dino_embedding_cache, f)
                except Exception as e:
                    print(f"[DEBUG] Error saving DINOv2 cache: {e}")

    def _process_batch(self, new_embedding, batch_texts, batch_metadata, results_list):
        """Helper to process a batch of texts for similarity using SBERT"""
        try:
            # Encode whole batch at once
            batch_embeddings = self.model.encode(batch_texts, convert_to_tensor=True)
            
            # Cache the computed embeddings
            for i, meta in enumerate(batch_metadata):
                ContentSimilarityDetector._embedding_cache[meta['id']] = batch_embeddings[i:i+1]
                
            # Save persistent cache
            try:
                os.makedirs(os.path.dirname(ContentSimilarityDetector._cache_file), exist_ok=True)
                with open(ContentSimilarityDetector._cache_file, 'wb') as f:
                    pickle.dump(ContentSimilarityDetector._embedding_cache, f)
            except Exception as e:
                print(f"[DEBUG] Error saving embedding cache: {e}")
                
            # Compute similarities for the whole batch
            cos_scores = util.cos_sim(new_embedding, batch_embeddings)[0]
            
            for i, score in enumerate(cos_scores):
                similarity_score = float(score.item())
                if similarity_score >= self.similarity_threshold:
                    meta = batch_metadata[i]
                    print(f"[DEBUG] ✓ MATCH FOUND! {meta['file_name']} is {similarity_score:.2%} similar")
                    results_list.append({
                        'id': meta['id'],
                        'file_name': meta['file_name'],
                        'file_size': meta['file_size'],
                        'file_hash': meta['file_hash'],
                        'upload_timestamp': meta['upload_timestamp'],
                        'stored_path': meta['stored_path'],
                        'similarity': similarity_score
                    })
        except Exception as e:
            print(f"[DEBUG] Error processing batch: {e}")



def detect_similar_content(file_path, filename, file_hash, existing_files, threshold=0.60):
    """
    Main function to detect similar content
    
    Args:
        file_path: Path to uploaded file
        filename: Name of file
        file_hash: Hash of file
        existing_files: List of existing files from DB to compare against
        threshold: Similarity threshold (default 0.60 = 60%)
        
    Returns:
        List of similar files with similarity scores
    """
    detector = ContentSimilarityDetector(similarity_threshold=threshold)
    return detector.find_similar_files(file_path, filename, file_hash, existing_files)
