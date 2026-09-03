"""
Content-Level Similarity Detection Module
Detects near-duplicate files based on content similarity (60%+ match)
across ALL file formats: text, code, PDF, Word (DOCX/DOC), PowerPoint (PPTX), 
Spreadsheets (XLSX/CSV), Rich Text (RTF/ODT/EPUB), Images, and binary files.
"""
from sentence_transformers import SentenceTransformer, util
import torch
import pickle
import os
import re
import difflib
from config import Config

try:
    from PIL import Image
except ImportError:
    print("WARNING: PIL not installed.")

import base64
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class SBERTModel:
    """Singleton for SBERT model to avoid reloading"""
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            print("[DEBUG] Loading Sentence-BERT model (all-MiniLM-L6-v2)...")
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
            try:
                from transformers import AutoImageProcessor, AutoModel
                device = 'cuda' if torch.cuda.is_available() else 'cpu'
                try:
                    cls._processor = AutoImageProcessor.from_pretrained('facebook/dinov2-small', local_files_only=True)
                    cls._instance = AutoModel.from_pretrained('facebook/dinov2-small', local_files_only=True).to(device)
                    print("[DEBUG] DINOv2 loaded from local cache.")
                except Exception:
                    cls._processor = AutoImageProcessor.from_pretrained('facebook/dinov2-small')
                    cls._instance = AutoModel.from_pretrained('facebook/dinov2-small').to(device)
                    print("[DEBUG] DINOv2 loaded successfully.")
            except Exception as e:
                print(f"[DEBUG] DINOv2 load warning: {e}")
                return None, None
        return cls._instance, cls._processor


class ContentSimilarityDetector:
    """Detect content-level similarity for any file using hybrid SBERT + Lexical + DINOv2"""
    
    # Class-level cache to persist across multiple uploads
    _embedding_cache = {}
    _cache_file = os.path.join(Config.BASE_DIR, 'ml_data', 'embedding_cache.pkl')
    _cache_loaded = False
    
    _dino_embedding_cache = {}
    _dino_cache_file = os.path.join(Config.BASE_DIR, 'ml_data', 'dino_cache.pkl')
    _dino_cache_loaded = False
    
    def __init__(self, similarity_threshold=0.60, image_similarity_threshold=0.60):
        self.similarity_threshold = similarity_threshold
        self.image_similarity_threshold = image_similarity_threshold
        self.model = SBERTModel.get_instance()
        self.dino_model = None
        self.dino_processor = None
        
        # Load persistent caches
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
        
        self.image_extensions = {
            'png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'tiff', 'svg', 'ico', 'avif', 'heic'
        }

    def is_image_file(self, filename):
        """Check if file is an image file based on extension"""
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        return ext in self.image_extensions

    def is_text_file(self, filename):
        """True for non-image, non-audio, non-video files that can be processed as text/content"""
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        media_exts = {'mp3', 'wav', 'aac', 'flac', 'm4a', 'mpeg', 'mpg', 'ogg', 'opus', 'amr', 'wma', 'mpga', 'mp2',
                      'mp4', 'avi', 'mov', 'mkv', 'webm', 'wmv', 'flv'}
        if ext in media_exts or ext in self.image_extensions:
            return False
        return True

    # ----------------------------------------------------------------------
    # Universal Content Extraction Methods
    # ----------------------------------------------------------------------

    def extract_text_from_pdf(self, file_path):
        """Extract text from PDF file using PyPDF2 with fallback"""
        try:
            import PyPDF2
            text = ""
            with open(file_path, 'rb') as pdf_file:
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                num_pages = len(pdf_reader.pages)
                for page_num in range(num_pages):
                    page = pdf_reader.pages[page_num]
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                
                cleaned = re.sub(r'\s+', ' ', text).strip()
                if cleaned:
                    print(f"[DEBUG] Extracted {len(cleaned)} characters from PDF")
                    return cleaned
        except Exception as e:
            print(f"[DEBUG] PyPDF2 extraction error: {e}")
        
        # Fallback to string extraction from raw bytes
        return self.extract_printable_strings(file_path)

    def extract_text_from_docx(self, file_path):
        """Extract text from DOCX file using standard zipfile/xml parser"""
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            with zipfile.ZipFile(file_path) as z:
                xml_content = z.read('word/document.xml')
                tree = ET.fromstring(xml_content)
                paragraphs = []
                for p in tree.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
                    texts = [node.text for node in p.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t') if node.text]
                    if texts:
                        paragraphs.append("".join(texts))
                extracted = "\n".join(paragraphs).strip()
                cleaned = re.sub(r'\s+', ' ', extracted).strip()
                if cleaned:
                    print(f"[DEBUG] Extracted {len(cleaned)} characters from DOCX")
                    return cleaned
        except Exception as e:
            print(f"[DEBUG] DOCX extraction error: {e}")
            
        return self.extract_printable_strings(file_path)

    def extract_text_from_pptx(self, file_path):
        """Extract text from PPTX presentation slides"""
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            texts = []
            with zipfile.ZipFile(file_path) as z:
                for name in z.namelist():
                    if name.startswith('ppt/slides/slide') and name.endswith('.xml'):
                        slide_xml = z.read(name)
                        tree = ET.fromstring(slide_xml)
                        for node in tree.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}t'):
                            if node.text:
                                texts.append(node.text)
            extracted = " ".join(texts).strip()
            if extracted:
                print(f"[DEBUG] Extracted {len(extracted)} characters from PPTX")
                return extracted
        except Exception as e:
            print(f"[DEBUG] PPTX extraction error: {e}")
        return self.extract_printable_strings(file_path)

    def extract_text_from_xlsx(self, file_path):
        """Extract text and strings from XLSX spreadsheet"""
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            texts = []
            with zipfile.ZipFile(file_path) as z:
                if 'xl/sharedStrings.xml' in z.namelist():
                    ss_xml = z.read('xl/sharedStrings.xml')
                    tree = ET.fromstring(ss_xml)
                    for node in tree.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t'):
                        if node.text:
                            texts.append(node.text)
            extracted = " ".join(texts).strip()
            if extracted:
                print(f"[DEBUG] Extracted {len(extracted)} characters from XLSX")
                return extracted
        except Exception as e:
            print(f"[DEBUG] XLSX extraction error: {e}")
        return self.extract_printable_strings(file_path)

    def extract_text_from_odt(self, file_path):
        """Extract text from ODT / ODS / ODP document"""
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            with zipfile.ZipFile(file_path) as z:
                if 'content.xml' in z.namelist():
                    c_xml = z.read('content.xml')
                    tree = ET.fromstring(c_xml)
                    texts = [elem.text for elem in tree.iter() if elem.text]
                    extracted = " ".join(texts).strip()
                    if extracted:
                        return extracted
        except Exception as e:
            print(f"[DEBUG] ODT extraction error: {e}")
        return self.extract_printable_strings(file_path)

    def extract_text_from_epub(self, file_path):
        """Extract text from EPUB e-book"""
        try:
            import zipfile
            texts = []
            with zipfile.ZipFile(file_path) as z:
                for name in z.namelist():
                    if name.endswith(('.html', '.xhtml', '.htm')):
                        html_content = z.read(name).decode('utf-8', errors='ignore')
                        clean_text = re.sub(r'<[^>]+>', ' ', html_content)
                        texts.append(clean_text)
            extracted = re.sub(r'\s+', ' ', " ".join(texts)).strip()
            if extracted:
                return extracted
        except Exception as e:
            print(f"[DEBUG] EPUB extraction error: {e}")
        return self.extract_printable_strings(file_path)

    def extract_printable_strings(self, file_path, min_length=4):
        """Extract readable ASCII / UTF-8 text strings from binary or unknown files"""
        try:
            with open(file_path, 'rb') as f:
                content = f.read(500000)  # Read up to 500KB
            
            # Find runs of printable characters
            pattern = re.compile(rb'[\x20-\x7E\t\n\r]{' + str(min_length).encode() + rb',}')
            matches = pattern.findall(content)
            extracted = " ".join([m.decode('ascii', errors='ignore') for m in matches])
            cleaned = re.sub(r'\s+', ' ', extracted).strip()
            if len(cleaned) > 20:
                print(f"[DEBUG] Extracted {len(cleaned)} characters of printable text from binary {file_path}")
                return cleaned
        except Exception as e:
            print(f"[DEBUG] Binary string extraction error: {e}")
        return None

    def read_file_content(self, file_path, filename=None):
        """
        Universal content reader for ANY file format.
        Extracts representative text representation suitable for SBERT semantic embedding.
        """
        if not file_path or not os.path.exists(file_path):
            return None
            
        name_to_check = (filename if filename else os.path.basename(file_path)).lower()
        lower_path = file_path.lower()
        
        # 1. Image Files
        if self.is_image_file(name_to_check) or self.is_image_file(lower_path):
            if OpenAI and getattr(Config, 'OPENAI_API_KEY', None):
                try:
                    client = OpenAI(api_key=Config.OPENAI_API_KEY)
                    with open(file_path, "rb") as image_file:
                        base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                        
                    mime_type = "image/jpeg"
                    if name_to_check.endswith('.png'): mime_type = "image/png"
                    elif name_to_check.endswith('.webp'): mime_type = "image/webp"
                    elif name_to_check.endswith('.gif'): mime_type = "image/gif"
                    
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {
                                "role": "system",
                                "content": "Analyze this image and describe text, visual components, layout, and subject matter for similarity detection."
                            },
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": "Extract all text and describe visual details of this image."},
                                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}}
                                ]
                            }
                        ],
                        max_tokens=500
                    )
                    return response.choices[0].message.content
                except Exception as e:
                    print(f"[DEBUG] GPT-4 Vision extraction note: {e}")
            return f"[Image file: {name_to_check}]"

        # 2. PDF Documents
        if name_to_check.endswith('.pdf') or lower_path.endswith('.pdf'):
            res = self.extract_text_from_pdf(file_path)
            if res: return res

        # 3. Word Documents (.docx, .doc)
        if name_to_check.endswith(('.docx', '.doc')) or lower_path.endswith(('.docx', '.doc')):
            res = self.extract_text_from_docx(file_path)
            if res: return res

        # 4. PowerPoint (.pptx, .ppt)
        if name_to_check.endswith(('.pptx', '.ppt')) or lower_path.endswith(('.pptx', '.ppt')):
            res = self.extract_text_from_pptx(file_path)
            if res: return res

        # 5. Excel (.xlsx, .xls)
        if name_to_check.endswith(('.xlsx', '.xls')) or lower_path.endswith(('.xlsx', '.xls')):
            res = self.extract_text_from_xlsx(file_path)
            if res: return res

        # 6. OpenDocument (.odt, .ods, .odp)
        if name_to_check.endswith(('.odt', '.ods', '.odp')) or lower_path.endswith(('.odt', '.ods', '.odp')):
            res = self.extract_text_from_odt(file_path)
            if res: return res

        # 7. E-books (.epub)
        if name_to_check.endswith('.epub') or lower_path.endswith('.epub'):
            res = self.extract_text_from_epub(file_path)
            if res: return res

        # 8. Standard Text, Code, Scripts, Markup, Config Files
        encodings = ['utf-8', 'latin-1', 'cp1252', 'utf-16', 'iso-8859-1']
        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    content = f.read()
                    if content:
                        cleaned = re.sub(r'\s+', ' ', content).strip()
                        return cleaned if cleaned else content
            except (UnicodeDecodeError, Exception):
                continue

        # 9. Fallback for binary / archive / unknown data formats
        return self.extract_printable_strings(file_path)

    # ----------------------------------------------------------------------
    # Hybrid Similarity Computation (SBERT + Lexical Jaccard + Sequence)
    # ----------------------------------------------------------------------

    def compute_text_similarity(self, text1, text2):
        """
        Compute robust hybrid similarity between two text strings:
        Combines SBERT semantic cosine similarity with Lexical Jaccard token overlap.
        """
        if not text1 or not text2:
            return 0.0
        
        t1_clean = re.sub(r'\s+', ' ', str(text1)).strip()
        t2_clean = re.sub(r'\s+', ' ', str(text2)).strip()
        
        if not t1_clean or not t2_clean:
            return 0.0
            
        if t1_clean == t2_clean:
            return 1.0

        sbert_sim = 0.0
        try:
            # Bound text length for fast SBERT encoding
            capped_t1 = t1_clean[:4000]
            capped_t2 = t2_clean[:4000]
            with torch.inference_mode():
                embeddings = self.model.encode([capped_t1, capped_t2], convert_to_tensor=True)
                cos_sim = util.cos_sim(embeddings[0], embeddings[1])
                sbert_sim = max(0.0, min(1.0, float(cos_sim.item())))
        except Exception as e:
            print(f"[DEBUG] SBERT similarity error: {e}")

        # Compute lexical word set Jaccard similarity
        words1 = set(re.findall(r'\b\w{2,}\b', t1_clean.lower()))
        words2 = set(re.findall(r'\b\w{2,}\b', t2_clean.lower()))
        jaccard_sim = 0.0
        if words1 and words2:
            intersection = len(words1.intersection(words2))
            union = len(words1.union(words2))
            jaccard_sim = float(intersection / union) if union > 0 else 0.0

        # SequenceMatcher for shorter strings / code snippets
        seq_sim = 0.0
        if len(t1_clean) < 1000 and len(t2_clean) < 1000:
            seq_sim = difflib.SequenceMatcher(None, t1_clean, t2_clean).ratio()

        # Hybrid maximum / weighted blend
        final_score = max(sbert_sim, jaccard_sim, seq_sim)
        return float(final_score)

    def compute_dinov2_embedding(self, file_path):
        """Compute DINOv2 image embedding"""
        try:
            if self.dino_model is None or self.dino_processor is None:
                self.dino_model, self.dino_processor = DINOv2Model.get_instance()
            if self.dino_model is None or self.dino_processor is None:
                return None
            image = Image.open(file_path).convert('RGB')
            inputs = self.dino_processor(images=image, return_tensors="pt")
            
            device = next(self.dino_model.parameters()).device
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.dino_model(**inputs)
                
            last_hidden_states = outputs.last_hidden_state
            image_embedding = last_hidden_states[:, 0, :]
            return image_embedding
        except Exception as e:
            print(f"[DEBUG] Error computing DINOv2 embedding for {file_path}: {e}")
            return None

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

    # ----------------------------------------------------------------------
    # Main Similarity Detection Engine
    # ----------------------------------------------------------------------

    def find_similar_files(self, file_path, filename, current_hash, existing_files):
        """
        Find files with similar content using hybrid SBERT/Lexical for text/documents/code
        and DINOv2 for images across ALL files.
        """
        print(f"\n[DEBUG] ========== CONTENT SIMILARITY CHECK STARTED ==========")
        print(f"[DEBUG] Target File: {filename} (Hash: {current_hash[:12] if current_hash else 'N/A'})")
        
        is_image = self.is_image_file(filename)
        
        new_dino_embedding = None
        new_text_content = None
        new_text_embedding = None
        
        if is_image:
            print(f"[DEBUG] Extracting DINOv2 embedding for image: {filename}")
            new_dino_embedding = self.compute_dinov2_embedding(file_path)
        else:
            new_text_content = self.read_file_content(file_path, filename=filename)
            if new_text_content:
                capped = new_text_content[:4000]
                print(f"[DEBUG] Successfully extracted {len(new_text_content)} chars from {filename}")
                try:
                    with torch.inference_mode():
                        new_text_embedding = self.model.encode(capped, convert_to_tensor=True)
                except Exception as emb_err:
                    print(f"[DEBUG] Embedding encoding error: {emb_err}")
            else:
                print(f"[DEBUG] Could not extract text content from {filename}")

        if new_dino_embedding is None and new_text_content is None:
            print(f"[DEBUG] No visual or text representation could be generated for {filename}")
            return []

        print(f"[DEBUG] Evaluating against {len(existing_files)} existing files in database...")
        
        similar_files = []
        batch_texts = []
        batch_metadata = []
        BATCH_SIZE = 32
        
        for file_row in existing_files:
            existing_filename = file_row.get('file_name', '')
            file_id = file_row.get('id')
            existing_hash = file_row.get('file_hash')
            
            # Skip comparing identical hash if passed
            if current_hash and existing_hash == current_hash:
                continue
                
            # Case A: Both files are Images -> Visual DINOv2 matching
            if is_image and self.is_image_file(existing_filename):
                import torch.nn.functional as F
                cached_dino = None
                
                # Check stored dino_embedding in DB row first
                stored_dino = file_row.get('dino_embedding')
                if stored_dino:
                    try:
                        import json
                        d_list = json.loads(stored_dino) if isinstance(stored_dino, str) else stored_dino
                        if d_list and isinstance(d_list, list):
                            cached_dino = torch.tensor([d_list], dtype=torch.float32)
                    except Exception:
                        pass
                
                # Check in-memory cache fallback
                if cached_dino is None and file_id in ContentSimilarityDetector._dino_embedding_cache:
                    cached_dino = ContentSimilarityDetector._dino_embedding_cache[file_id]
                    
                if cached_dino is not None and new_dino_embedding is not None:
                    try:
                        score = F.cosine_similarity(new_dino_embedding, cached_dino).item()
                        score = max(0.0, min(1.0, float(score)))
                        if score >= self.image_similarity_threshold:
                            print(f"[DEBUG] [IMAGE MATCH] {existing_filename} is {score:.2%} similar")
                            similar_files.append({
                                'id': file_id,
                                'file_name': existing_filename,
                                'file_size': file_row.get('file_size', 0),
                                'file_hash': existing_hash,
                                'upload_timestamp': file_row.get('upload_timestamp'),
                                'stored_path': file_row.get('stored_path', ''),
                                'similarity': score,
                                'match_type': 'visual'
                            })
                    except Exception as img_sim_err:
                        print(f"[DEBUG] Image similarity calculation error: {img_sim_err}")
                continue

            # Case B: Text / Document / Code / Binary matching
            existing_content = file_row.get('content_text')
            
            if existing_content and new_text_embedding is not None:
                # Check in-memory embedding cache
                if file_id in ContentSimilarityDetector._embedding_cache:
                    cached_emb = ContentSimilarityDetector._embedding_cache[file_id]
                    try:
                        cos_scores = util.cos_sim(new_text_embedding, cached_emb)[0]
                        sbert_score = float(cos_scores[0].item())
                        
                        # Hybrid check with Jaccard for high accuracy
                        words1 = set(re.findall(r'\b\w{2,}\b', new_text_content.lower()[:2000]))
                        words2 = set(re.findall(r'\b\w{2,}\b', str(existing_content).lower()[:2000]))
                        jaccard_score = len(words1.intersection(words2)) / len(words1.union(words2)) if words1 and words2 else 0.0
                        
                        score = max(sbert_score, jaccard_score)
                        score = max(0.0, min(1.0, score))
                        
                        if score >= self.similarity_threshold:
                            print(f"[DEBUG] [SBERT CACHE MATCH] {existing_filename} is {score:.2%} similar")
                            similar_files.append({
                                'id': file_id,
                                'file_name': existing_filename,
                                'file_size': file_row.get('file_size', 0),
                                'file_hash': existing_hash,
                                'upload_timestamp': file_row.get('upload_timestamp'),
                                'stored_path': file_row.get('stored_path', ''),
                                'similarity': score,
                                'match_type': 'text'
                            })
                    except Exception as cache_err:
                        print(f"[DEBUG] SBERT cache scoring error: {cache_err}")
                else:
                    batch_texts.append(str(existing_content)[:4000])
                    batch_metadata.append(file_row)
                    
            if len(batch_texts) >= BATCH_SIZE:
                self._process_batch(new_text_embedding, new_text_content, batch_texts, batch_metadata, similar_files)
                batch_texts = []
                batch_metadata = []

        # Process any remaining files in batch
        if batch_texts and new_text_embedding is not None:
            self._process_batch(new_text_embedding, new_text_content, batch_texts, batch_metadata, similar_files)

        # Sort by similarity descending
        similar_files.sort(key=lambda x: x['similarity'], reverse=True)
        print(f"[DEBUG] Similarity scan complete. Found {len(similar_files)} matching files >= {self.similarity_threshold:.0%}")
        return similar_files[:10]

    def _process_batch(self, new_embedding, new_content, batch_texts, batch_metadata, results_list):
        """Helper to process a batch of texts using SBERT + Lexical validation"""
        try:
            with torch.inference_mode():
                batch_embeddings = self.model.encode(batch_texts, convert_to_tensor=True)
                
            for i, meta in enumerate(batch_metadata):
                ContentSimilarityDetector._embedding_cache[meta['id']] = batch_embeddings[i:i+1]
                
            # Save persistent cache asynchronously/safely
            try:
                os.makedirs(os.path.dirname(ContentSimilarityDetector._cache_file), exist_ok=True)
                with open(ContentSimilarityDetector._cache_file, 'wb') as f:
                    pickle.dump(ContentSimilarityDetector._embedding_cache, f)
            except Exception:
                pass
                
            cos_scores = util.cos_sim(new_embedding, batch_embeddings)[0]
            
            for i, score in enumerate(cos_scores):
                sbert_score = float(score.item())
                meta = batch_metadata[i]
                
                # Hybrid lexical verification
                words1 = set(re.findall(r'\b\w{2,}\b', str(new_content).lower()[:2000]))
                words2 = set(re.findall(r'\b\w{2,}\b', str(batch_texts[i]).lower()[:2000]))
                jaccard_score = len(words1.intersection(words2)) / len(words1.union(words2)) if words1 and words2 else 0.0
                
                final_score = max(sbert_score, jaccard_score)
                final_score = max(0.0, min(1.0, final_score))
                
                if final_score >= self.similarity_threshold:
                    print(f"[DEBUG] [MATCH FOUND] {meta['file_name']} is {final_score:.2%} similar")
                    results_list.append({
                        'id': meta['id'],
                        'file_name': meta['file_name'],
                        'file_size': meta.get('file_size', 0),
                        'file_hash': meta.get('file_hash'),
                        'upload_timestamp': meta.get('upload_timestamp'),
                        'stored_path': meta.get('stored_path', ''),
                        'similarity': final_score,
                        'match_type': 'text'
                    })
        except Exception as e:
            print(f"[DEBUG] Error processing text batch: {e}")


def detect_similar_content(file_path, filename, file_hash, existing_files, threshold=0.60):
    """
    Main function to detect similar content across any files
    """
    detector = ContentSimilarityDetector(similarity_threshold=threshold)
    return detector.find_similar_files(file_path, filename, file_hash, existing_files)
