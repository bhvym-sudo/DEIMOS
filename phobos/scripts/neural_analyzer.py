import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neural_network import MLPClassifier
from sklearn.model_selection import train_test_split
import pickle
import os
import json
from datetime import datetime


class NeuralThreatAnalyzer:
    
    def __init__(self, model_dir='models'):
        self.model_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), model_dir)
        os.makedirs(self.model_dir, exist_ok=True)
        
        self.vectorizer_path = os.path.join(self.model_dir, 'vectorizer.pkl')
        self.classifier_path = os.path.join(self.model_dir, 'neural_classifier.pkl')
        self.training_data_path = os.path.join(self.model_dir, 'training_data.pkl')
        self.metrics_path = os.path.join(self.model_dir, 'model_metrics.json')
        
        self.load_or_initialize_model()
    
    def load_or_initialize_model(self):
        if os.path.exists(self.vectorizer_path) and os.path.exists(self.classifier_path):
            with open(self.vectorizer_path, 'rb') as f:
                self.vectorizer = pickle.load(f)
            with open(self.classifier_path, 'rb') as f:
                self.classifier = pickle.load(f)
            print("[NEURAL] Loaded existing neural network model")
        else:
            self.vectorizer = TfidfVectorizer(max_features=500, stop_words='english', ngram_range=(1, 2))
            self.classifier = MLPClassifier(
                hidden_layer_sizes=(128, 64, 32),
                activation='relu',
                solver='adam',
                alpha=0.0001,
                batch_size=32,
                learning_rate='adaptive',
                learning_rate_init=0.001,
                max_iter=500,
                random_state=42,
                early_stopping=True,
                validation_fraction=0.1,
                n_iter_no_change=10
            )
            print("[NEURAL] Initialized new neural network model")
        
        if os.path.exists(self.training_data_path):
            with open(self.training_data_path, 'rb') as f:
                self.training_data = pickle.load(f)
            print(f"[NEURAL] Loaded {len(self.training_data['texts'])} historical training samples")
        else:
            self.training_data = {'texts': [], 'labels': [], 'metadata': []}
    
    def add_training_sample(self, text, label, metadata=None):
        self.training_data['texts'].append(text)
        self.training_data['labels'].append(label)
        self.training_data['metadata'].append(metadata or {})
    
    def train_model(self, threatening_samples, non_threatening_samples):
        all_texts = []
        all_labels = []
        
        for sample in threatening_samples:
            all_texts.append(sample)
            all_labels.append(1)
            self.add_training_sample(sample, 1, {'source': 'initial_threat'})
        
        for sample in non_threatening_samples:
            all_texts.append(sample)
            all_labels.append(0)
            self.add_training_sample(sample, 0, {'source': 'initial_safe'})
        
        for text, label in zip(self.training_data['texts'], self.training_data['labels']):
            all_texts.append(text)
            all_labels.append(label)
        
        if len(all_texts) < 10:
            print("[NEURAL] Not enough training data")
            return False
        
        X = self.vectorizer.fit_transform(all_texts)
        y = np.array(all_labels)
        
        if len(set(y)) < 2:
            print("[NEURAL] Need both threat and non-threat samples")
            return False
        
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
        
        self.classifier.fit(X_train.toarray(), y_train)
        
        train_score = self.classifier.score(X_train.toarray(), y_train)
        test_score = self.classifier.score(X_test.toarray(), y_test)
        
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'train_accuracy': float(train_score),
            'test_accuracy': float(test_score),
            'total_samples': len(all_texts),
            'threat_samples': int(np.sum(y)),
            'safe_samples': int(len(y) - np.sum(y)),
            'iterations': int(self.classifier.n_iter_)
        }
        
        with open(self.metrics_path, 'w') as f:
            json.dump(metrics, f, indent=2)
        
        self.save_model()
        
        print(f"[NEURAL] Model trained - Train Acc: {train_score:.3f}, Test Acc: {test_score:.3f}")
        return True
    
    def predict_threat(self, text):
        if len(text) == 0:
            return 0.0
        
        try:
            X = self.vectorizer.transform([text[:5000]])
            proba = self.classifier.predict_proba(X.toarray())[0]
            return float(proba[1])
        except:
            return 0.0
    
    def update_with_feedback(self, text, actual_label):
        self.add_training_sample(text, actual_label, {
            'source': 'user_feedback',
            'timestamp': datetime.now().isoformat()
        })
        
        if len(self.training_data['texts']) % 10 == 0:
            self.incremental_train()
    
    def incremental_train(self):
        if len(self.training_data['texts']) < 5:
            return False
        
        recent_texts = self.training_data['texts'][-100:]
        recent_labels = self.training_data['labels'][-100:]
        
        X = self.vectorizer.transform(recent_texts)
        y = np.array(recent_labels)
        
        if len(set(y)) >= 2:
            self.classifier.partial_fit(X.toarray(), y)
            self.save_model()
            print(f"[NEURAL] Incremental training completed with {len(recent_texts)} samples")
            return True
        return False
    
    def save_model(self):
        with open(self.vectorizer_path, 'wb') as f:
            pickle.dump(self.vectorizer, f)
        with open(self.classifier_path, 'wb') as f:
            pickle.dump(self.classifier, f)
        with open(self.training_data_path, 'wb') as f:
            pickle.dump(self.training_data, f)
    
    def get_model_info(self):
        if os.path.exists(self.metrics_path):
            with open(self.metrics_path, 'r') as f:
                metrics = json.load(f)
        else:
            metrics = {
                'timestamp': 'N/A',
                'train_accuracy': 0.0,
                'test_accuracy': 0.0,
                'total_samples': 0,
                'threat_samples': 0,
                'safe_samples': 0,
                'iterations': 0
            }
        
        metrics['historical_samples'] = len(self.training_data['texts'])
        return metrics
