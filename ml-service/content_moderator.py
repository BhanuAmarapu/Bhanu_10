"""
AI Content Moderation Module - Enhanced with TF-IDF

Provides intelligent content moderation using TF-IDF algorithm for:
- Text content filtering (profanity, explicit content, violence)
- Image filename checking
- Video moderation (placeholder)

Uses TF-IDF similarity scoring against known bad content patterns.
"""

import os
import re
from dataclasses import dataclass
from typing import Tuple, List, Optional
from datetime import datetime
from sentence_transformers import SentenceTransformer, util
import torch
import numpy as np


class SBERTModel:
    """Singleton for SBERT model to avoid reloading"""
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            print("[MODERATION] Loading SBERT model (all-MiniLM-L6-v2)...")
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            try:
                cls._instance = SentenceTransformer('all-MiniLM-L6-v2', device=device)
            except Exception as e:
                print(f"[MODERATION] SBERT online load failed: {e}. Retrying with local_files_only=True...")
                try:
                    cls._instance = SentenceTransformer('all-MiniLM-L6-v2', device=device, local_files_only=True)
                except Exception as inner_e:
                    print(f"[MODERATION] SBERT local cache load failed: {inner_e}")
                    raise inner_e
        return cls._instance


@dataclass
class ModerationResult:
    """Result of content moderation check"""
    is_safe: bool
    violation_type: Optional[str] = None
    violation_details: Optional[str] = None
    confidence_score: float = 0.0
    flagged_keywords: List[str] = None
    
    def __post_init__(self):
        if self.flagged_keywords is None:
            self.flagged_keywords = []


class ContentModerator:
    """
    Intelligent content moderation service using Sentence-BERT
    
    Analyzes text content using SBERT similarity against known bad content patterns.
    """
    
    _embeddings_initialized = False
    _explicit_embeddings = None
    _profanity_embeddings = None
    _violence_embeddings = None
    _noise_embeddings = None

    def __init__(self, strict_mode=False, threshold=0.60):
        """
        Initialize content moderator with SBERT
        
        Args:
            strict_mode: If True, uses stricter filtering rules
            threshold: SBERT similarity threshold (0.60 = 60% semantic similarity)
        """
        self.strict_mode = strict_mode
        self.threshold = threshold
        self.model = SBERTModel.get_instance()
        
        # Training data: Examples of bad content for each category
        self.explicit_examples = [
            "explicit adult sexual content pornography",
            "nude naked nsfw erotic sex xxx porn",
            "sexual explicit adult content inappropriate",
            "pornographic material adult entertainment",
            "explicit sexual imagery nude photos"
        ]
        
        self.profanity_examples = [
            "fuck shit damn bitch ass bastard",
            "fucking hell piss cock dick pussy",
            "goddamn motherfucker asshole crap",
            "bullshit fucking damn hell shit",
            "curse words profanity vulgar language"
        ]
        
        self.violence_examples = [
            "kill murder violence weapon gun",
            "torture abuse rape violent attack",
            "terrorism bomb explosive weapon",
            "gore blood violent death murder",
            "hate crime racist violence abuse"
        ]

        self.noise_examples = [
            "random garbage irrelevant technical noise",
            "non-relevant node test data unrelated",
            "asdfghjkl qwerty uiop meaningless text",
            "unrelated technical noise testing string",
            "garbage data nothing to do with application"
        ]
        
        # Pre-encode examples into embeddings ONLY ONCE
        if not ContentModerator._embeddings_initialized:
            print("[MODERATION] Pre-encoding reference examples...")
            ContentModerator._explicit_embeddings = self.model.encode(self.explicit_examples, convert_to_tensor=True)
            ContentModerator._profanity_embeddings = self.model.encode(self.profanity_examples, convert_to_tensor=True)
            ContentModerator._violence_embeddings = self.model.encode(self.violence_examples, convert_to_tensor=True)
            ContentModerator._noise_embeddings = self.model.encode(self.noise_examples, convert_to_tensor=True)
            ContentModerator._embeddings_initialized = True
            
        self.explicit_embeddings = ContentModerator._explicit_embeddings
        self.profanity_embeddings = ContentModerator._profanity_embeddings
        self.violence_embeddings = ContentModerator._violence_embeddings
        self.noise_embeddings = ContentModerator._noise_embeddings
        
    def analyze_text_with_sbert(self, text: str) -> Tuple[str, float, List[str]]:
        """
        Analyze text using SBERT similarity against bad content patterns
        
        Args:
            text: Text content to analyze
            
        Returns:
            Tuple of (violation_type, confidence_score, flagged_keywords)
        """
        if not text.strip():
            return None, 0.0, []
            
        text_lower = text.lower()
        
        try:
            # Encode target text
            text_embedding = self.model.encode(text_lower, convert_to_tensor=True)
            
            # Calculate similarity scores for each category
            explicit_sims = util.cos_sim(text_embedding, self.explicit_embeddings)
            max_explicit_score = float(torch.max(explicit_sims).item())
            
            profanity_sims = util.cos_sim(text_embedding, self.profanity_embeddings)
            max_profanity_score = float(torch.max(profanity_sims).item())
            
            violence_sims = util.cos_sim(text_embedding, self.violence_embeddings)
            max_violence_score = float(torch.max(violence_sims).item())
            
            noise_sims = util.cos_sim(text_embedding, self.noise_embeddings)
            max_noise_score = float(torch.max(noise_sims).item())
            
            # Determine which category has highest score
            scores = {
                'EXPLICIT': max_explicit_score,
                'PROFANITY': max_profanity_score,
                'VIOLENCE': max_violence_score,
                'IRRELEVANT_NOISE': max_noise_score
            }
            
            violation_type = max(scores, key=scores.get)
            confidence = scores[violation_type]
            
            # Extract flagged keywords based on category
            flagged_keywords = []
            if violation_type == 'EXPLICIT':
                keywords = {'explicit', 'adult', 'sexual', 'porn', 'xxx', 'nude', 'naked', 'nsfw', 'sex', 'erotic'}
            elif violation_type == 'PROFANITY':
                keywords = {'fuck', 'shit', 'damn', 'bitch', 'ass', 'bastard', 'hell', 'piss', 'cock', 'dick', 'pussy'}
            elif violation_type == 'VIOLENCE':
                keywords = {'kill', 'murder', 'rape', 'torture', 'abuse', 'violence', 'weapon', 'gun', 'bomb', 'hate'}
            elif violation_type == 'IRRELEVANT_NOISE':
                keywords = {'random', 'garbage', 'irrelevant', 'noise', 'meaningless', 'unrelated', 'test'}
            
            for keyword in keywords:
                if keyword in text_lower:
                    flagged_keywords.append(keyword)
            
            return violation_type, confidence, flagged_keywords
            
        except Exception as e:
            print(f"[MODERATION] SBERT analysis error: {e}")
            return None, 0.0, []
    
    def moderate_text(self, file_path: str) -> ModerationResult:
        """
        Moderate text file content using TF-IDF
        
        Args:
            file_path: Path to text file
            
        Returns:
            ModerationResult with safety status and details
        """
        try:
            # Read file content
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            if not content.strip():
                return ModerationResult(is_safe=True, confidence_score=1.0)
            
            # Analyze with SBERT
            violation_type, confidence, flagged_keywords = self.analyze_text_with_sbert(content)
            
            # Check if confidence exceeds threshold
            if confidence >= self.threshold:
                violation_details = f"SBERT analysis detected {violation_type.lower()} content (similarity: {confidence:.1%})"
                if flagged_keywords:
                    violation_details += f". Found keywords: {', '.join(flagged_keywords[:5])}"
                
                return ModerationResult(
                    is_safe=False,
                    violation_type=violation_type,
                    violation_details=violation_details,
                    confidence_score=confidence,
                    flagged_keywords=flagged_keywords
                )
            
            return ModerationResult(is_safe=True, confidence_score=1.0 - confidence)
            
        except Exception as e:
            print(f"[MODERATION] Error reading text file: {e}")
            # On error, allow upload but log it
            return ModerationResult(
                is_safe=True,
                violation_details=f"Error during moderation: {str(e)}"
            )
    
    def moderate_image(self, file_path: str) -> ModerationResult:
        """
        Moderate image content using GPT-4 Vision (Multimodal Analysis)
        
        Args:
            file_path: Path to image file
            
        Returns:
            ModerationResult with safety status
        """
        try:
            # First perform filename keyword check as a quick filter
            filename = os.path.basename(file_path).lower()
            suspicious_image_keywords = {
                'gun', 'weapon', 'nude', 'naked', 'porn', 'xxx', 'sex',
                'explicit', 'nsfw', 'violence', 'blood', 'gore', 'kill',
                'murder', 'rape', 'abuse', 'hate', 'racist', 'terrorist'
            }
            
            flagged_keywords = [k for k in suspicious_image_keywords if k in filename]
            if flagged_keywords:
                return ModerationResult(
                    is_safe=False,
                    violation_type='EXPLICIT' if any(k in ['nude', 'naked', 'porn', 'xxx', 'sex', 'nsfw'] for k in flagged_keywords) else 'VIOLENCE',
                    violation_details=f"Suspicious filename detected: {', '.join(flagged_keywords)}",
                    confidence_score=0.9,
                    flagged_keywords=flagged_keywords
                )

            # Deep analysis using GPT-4 Vision if API key is present
            from config import Config
            if not getattr(Config, 'OPENAI_API_KEY', None):
                print("[WARNING] OPENAI_API_KEY is not set. Using basic filename moderation only.")
                return ModerationResult(is_safe=True, confidence_score=0.5)

            import base64
            from openai import OpenAI
            client = OpenAI(api_key=Config.OPENAI_API_KEY)

            with open(file_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
            mime_type = "image/jpeg"
            if filename.endswith('.png'): mime_type = "image/png"
            elif filename.endswith('.webp'): mime_type = "image/webp"
            elif filename.endswith('.gif'): mime_type = "image/gif"

            print(f"[MODERATION] Analyzing image {filename} with GPT-4 Vision...")
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a strict safety and quality content moderator. Analyze this image and classify it strictly into one of three categories: 'Safe', 'Sensitive', or 'Restricted'. \n\nRestricted: Weapons (guns, knives, explosives), violence, gore, explicit NSFW, illegal acts, OR non-relevant/noisy data, node/unrelated technical noise, or random meaningless data. \nSensitive: Edge-case content that is slightly unsafe.\nSafe: Benign, meaningful, regular content.\n\nAlso provide a confidence score (0.0 to 1.0). If Restricted/Sensitive confidence > 0.60, it will be rejected.\n\nOutput format EXACTLY like this: '[Classification]: [Confidence Score] - [Brief reason]'. Example: 'Restricted: 0.95 - Image contains a firearm.'"
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Classify this image."},
                            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}}
                        ]
                    }
                ],
                max_tokens=100
            )

            result_text = response.choices[0].message.content.strip()
            print(f"[MODERATION] GPT-4 Vision result for {filename}: {result_text}")

            try:
                # Parse format: "Restricted: 0.95 - Reason"
                parts = result_text.split(":")
                classification = parts[0].strip()
                score_and_reason = parts[1].strip().split("-", 1)
                confidence = float(score_and_reason[0].strip())
                reason = score_and_reason[1].strip() if len(score_and_reason) > 1 else result_text
            except Exception as e:
                classification = "Safe" if "Safe" in result_text else "Restricted"
                confidence = 0.9
                reason = result_text

            if classification == "Safe" or (classification != "Safe" and confidence <= 0.60):
                return ModerationResult(is_safe=True, confidence_score=1.0)
            
            # If Restricted or Sensitive, we reject
            violation_type = "RESTRICTED"
            if "Sensitive" in classification:
                violation_type = "SENSITIVE"
            elif "violence" in reason.lower() or "weapon" in reason.lower() or "gun" in reason.lower():
                violation_type = "VIOLENCE"
            elif "explicit" in reason.lower() or "nsfw" in reason.lower():
                violation_type = "EXPLICIT"
            elif "nois" in reason.lower() or "irrelevant" in reason.lower() or "random" in reason.lower():
                violation_type = "IRRELEVANT_NOISE"

            return ModerationResult(
                is_safe=False,
                violation_type=violation_type,
                violation_details=f"GPT-4 Vision detected unsafe/irrelevant content: {reason}",
                confidence_score=confidence
            )

        except Exception as e:
            print(f"[MODERATION] Error checking image with GPT-4 Vision: {e}")
            # If using strict guardrails, we fail closed on API errors (including invalid API key)
            if self.strict_mode or Config.OPENAI_API_KEY == 'your_openai_api_key_here' or not Config.OPENAI_API_KEY:
                return ModerationResult(
                    is_safe=False,
                    violation_type="API_ERROR",
                    violation_details=f"Moderation failed (API Error/Missing Key). Strict mode rejects unverified content. Error: {str(e)}",
                    confidence_score=1.0
                )
            return ModerationResult(
                is_safe=True,
                violation_details=f"Error during image moderation: {str(e)}"
            )
    
    def moderate_video(self, file_path: str) -> ModerationResult:
        """
        Moderate video content using FFmpeg/ffprobe frame extraction
        
        Args:
            file_path: Path to video file
            
        Returns:
            ModerationResult with safety status
        """
        try:
            import subprocess
            import tempfile
            import os
            try:
                from static_ffmpeg import add_paths
                add_paths()
            except ImportError:
                pass

            # 1. Get video duration using ffprobe
            duration = 0.0
            try:
                cmd = [
                    "ffprobe", 
                    "-v", "error", 
                    "-show_entries", "format=duration", 
                    "-of", "default=noprint_wrappers=1:nokey=1", 
                    file_path
                ]
                output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
                duration = float(output.decode().strip())
            except Exception as e:
                print(f"[MODERATION] ffprobe duration check failed: {e}")

            # 2. Determine seek time (middle of the video, fallback to 2 seconds or 0 if very short)
            seek_time = duration / 2.0 if duration > 0 else 2.0

            fd, temp_img_path = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)

            # 3. FFmpeg command to extract 1 frame at seek_time
            if duration > 0 and seek_time > duration:
                seek_time = duration / 2.0

            cmd = [
                "ffmpeg", "-y",
                "-ss", str(seek_time),
                "-i", file_path,
                "-vframes", "1",
                "-q:v", "2",
                temp_img_path
            ]

            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if process.returncode != 0:
                print(f"[MODERATION] FFmpeg ss-seek failed (code {process.returncode}). Retrying from start...")
                cmd = [
                    "ffmpeg", "-y",
                    "-i", file_path,
                    "-vframes", "1",
                    "-q:v", "2",
                    temp_img_path
                ]
                process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            if process.returncode != 0 or not os.path.exists(temp_img_path) or os.path.getsize(temp_img_path) == 0:
                return ModerationResult(is_safe=True, violation_details="Could not extract video frame using FFmpeg")

            # Moderate the extracted frame
            result = self.moderate_image(temp_img_path)
            
            # Clean up
            try:
                os.remove(temp_img_path)
            except:
                pass
                
            return result
            
        except Exception as e:
            print(f"[MODERATION] Error checking video: {e}")
            return ModerationResult(is_safe=True, violation_details=f"FFmpeg extraction error: {str(e)}")
    
    def moderate_file(self, file_path: str, filename: str) -> ModerationResult:
        """
        Moderate any file based on its type using TF-IDF
        
        Args:
            file_path: Path to file
            filename: Name of file (used to determine type)
            
        Returns:
            ModerationResult with safety status
        """
        # Determine file type from extension
        ext = os.path.splitext(filename)[1].lower()
        
        # Text files
        text_extensions = {'.txt', '.md', '.log', '.csv', '.json', '.xml', 
                          '.py', '.js', '.html', '.css', '.java', '.cpp', 
                          '.c', '.h', '.sql', '.sh'}
        
        # Image files
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', 
                           '.svg', '.ico', '.tiff'}
        
        # Video files
        video_extensions = {'.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', 
                           '.webm', '.m4v'}
        
        # Route to appropriate moderator
        if ext in text_extensions:
            return self.moderate_text(file_path)
        elif ext in image_extensions:
            return self.moderate_image(file_path)
        elif ext in video_extensions:
            return self.moderate_video(file_path)
        else:
            # Unknown file type - allow but log
            return ModerationResult(
                is_safe=True,
                violation_details=f"Unknown file type: {ext}"
            )


if __name__ == '__main__':
    # Quick test
    moderator = ContentModerator()
    
    # Test with bad content
    with open('test_bad.txt', 'w') as f:
        f.write("This contains explicit adult sexual content.")
    
    result = moderator.moderate_file('test_bad.txt', 'test_bad.txt')
    print(f"Result: {'SAFE' if result.is_safe else 'REJECTED'}")
    if not result.is_safe:
        print(f"Violation: {result.violation_type}")
        print(f"Confidence: {result.confidence_score:.1%}")
        print(f"Details: {result.violation_details}")
    
    os.remove('test_bad.txt')
