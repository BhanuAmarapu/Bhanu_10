import os
import pickle
from config import Config

class MLModel:
    def __init__(self):
        self.model = None
        self.model_path = Config.ML_MODEL_PATH
        
    def train(self, csv_path):
        """Train the model on historical metadata."""
        import pandas as pd
        from sklearn.tree import DecisionTreeClassifier
        
        if not os.path.exists(csv_path):
            # Create a dummy dataset if it doesn't exist
            self._create_dummy_data(csv_path)
            
        df = pd.read_csv(csv_path)
        
        # Features: file_size, extension_code, name_similarity_score (simulated)
        # Target: is_duplicate (0 or 1)
        X = df[['file_size', 'extension_code', 'frequency']]
        y = df['is_duplicate']
        
        self.model = DecisionTreeClassifier()
        self.model.fit(X, y)
        
        # Save model
        with open(self.model_path, 'wb') as f:
            pickle.dump(self.model, f)
        from utils import log_action
        log_action("ML Training", f"Model trained on {csv_path} and saved to {self.model_path}")
        print("Model trained and saved.")

    def predict(self, file_metadata):
        """
        Predict if a file is likely to be a duplicate.
        file_metadata: dict with 'file_size', 'extension_code', 'frequency'
        """
        import numpy as np
        
        if self.model is None:
            if os.path.exists(self.model_path):
                with open(self.model_path, 'rb') as f:
                    self.model = pickle.load(f)
            else:
                self.train(Config.ML_DATASET)
        
        features = np.array([[file_metadata['file_size'], 
                             file_metadata['extension_code'], 
                             file_metadata.get('frequency', 1)]])
        prediction = self.model.predict(features)
        return "Duplicate Likely" if prediction[0] == 1 else "Unique"

    def _create_dummy_data(self, csv_path):
        """Create a starting dataset for training."""
        import pandas as pd
        data = {
            'file_size': [1024, 2048, 1024, 500, 5000, 1024, 8000, 500],
            'extension_code': [1, 2, 1, 3, 1, 1, 2, 3], # 1: pdf, 2: jpg, 3: txt
            'frequency': [5, 1, 10, 2, 1, 8, 1, 4],
            'is_duplicate': [1, 0, 1, 0, 0, 1, 0, 1]
        }
        df = pd.DataFrame(data)
        if not os.path.exists(os.path.dirname(csv_path)):
            os.makedirs(os.path.dirname(csv_path))
        df.to_csv(csv_path, index=False)
        print(f"Dummy dataset created at {csv_path}")

# Extension mapping helper (unchanged)
EXT_MAP = {
    'pdf': 1,
    'jpg': 2,
    'jpeg': 2,
    'png': 2,
    'txt': 3,
    'docx': 4,
    'zip': 5
}

def get_ext_code(filename):
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    return EXT_MAP.get(ext, 0)
