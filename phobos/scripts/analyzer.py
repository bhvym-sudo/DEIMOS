import spacy
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from datetime import datetime
import re
import json
import os


class IntelligenceAnalyzer:
    
    def __init__(self):
        try:
            self.nlp = spacy.load('en_core_web_sm')
        except:
            self.nlp = None
            print("Warning: spaCy model not loaded. Run: python -m spacy download en_core_web_sm")
        
        self.intelligence_data_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'intelligence_data_new.json'
        )
        
        self.load_intelligence_data()
        self._initialize_threat_classifier()
        self._initialize_neural_analyzer()
        self._initialize_person_profiler()
    
    def _initialize_person_profiler(self):
        """Initialize the person profiling system"""
        try:
            from scripts.person_profiler import PersonProfiler
            self.person_profiler = PersonProfiler()
            print("[PROFILER] Person profiler initialized")
        except Exception as e:
            print(f"[PROFILER] Warning: Person profiler initialization failed: {e}")
            self.person_profiler = None
    
    def _initialize_neural_analyzer(self):
        try:
            from scripts.neural_analyzer import NeuralThreatAnalyzer
            self.neural_analyzer = NeuralThreatAnalyzer()
            
            if len(self.neural_analyzer.training_data['texts']) == 0:
                print("[NEURAL] Training initial neural network model...")
                self.neural_analyzer.train_model(self.threatening_samples, self.non_threatening_samples)
            
            print("[NEURAL] Neural threat analyzer ready")
        except Exception as e:
            print(f"[NEURAL] Warning: Neural analyzer initialization failed: {e}")
            self.neural_analyzer = None
    
    def load_intelligence_data(self):
        try:
            if os.path.exists(self.intelligence_data_file):
                with open(self.intelligence_data_file, 'r') as f:
                    data = json.load(f)
                    self.threat_keywords = data.get('threat_keywords', [])
                    self.threatening_samples = data.get('threatening_samples', [])
                    self.non_threatening_samples = data.get('non_threatening_samples', [])
            else:
                self.threat_keywords = ['leak', 'exploit', 'vulnerability', 'breach', 'hack']
                self.threatening_samples = ['major security breach detected in systems']
                self.non_threatening_samples = ['new software update improves experience']
        except Exception as e:
            print(f"Error loading intelligence data: {e}")
            self.threat_keywords = ['leak', 'exploit', 'vulnerability']
            self.threatening_samples = ['security breach']
            self.non_threatening_samples = ['software update']
    
    def _initialize_threat_classifier(self):
        X_train = self.threatening_samples + self.non_threatening_samples
        y_train = [1] * len(self.threatening_samples) + [0] * len(self.non_threatening_samples)
        
        self.vectorizer = TfidfVectorizer(max_features=100, stop_words='english')
        X_train_vec = self.vectorizer.fit_transform(X_train)
        
        self.threat_classifier = MultinomialNB()
        self.threat_classifier.fit(X_train_vec, y_train)
    
    def extract_entities(self, text):
        entities = {
            'persons': [],
            'organizations': [],
            'locations': [],
            'dates': [],
            'keywords': []
        }
        
        if self.nlp and len(text) > 0:
            doc = self.nlp(text[:1000000])
            
            for ent in doc.ents:
                if ent.label_ == 'PERSON':
                    entities['persons'].append(ent.text)
                elif ent.label_ == 'ORG':
                    entities['organizations'].append(ent.text)
                elif ent.label_ in ['GPE', 'LOC']:
                    entities['locations'].append(ent.text)
                elif ent.label_ == 'DATE':
                    entities['dates'].append(ent.text)
        
        text_lower = text.lower()
        for keyword in self.threat_keywords:
            if keyword in text_lower:
                entities['keywords'].append(keyword)
        
        entities['persons'] = list(set(entities['persons']))
        entities['organizations'] = list(set(entities['organizations']))
        entities['locations'] = list(set(entities['locations']))
        entities['dates'] = list(set(entities['dates']))
        entities['keywords'] = list(set(entities['keywords']))
        
        return entities
    
    def assess_threat(self, text):
        if len(text) == 0:
            return 0.0
        
        text_sample = text[:5000]
        
        try:
            X_vec = self.vectorizer.transform([text_sample])
            threat_prob = self.threat_classifier.predict_proba(X_vec)[0][1]
        except:
            threat_prob = 0.0
        
        keyword_score = 0
        text_lower = text_sample.lower()
        for keyword in self.threat_keywords:
            if keyword in text_lower:
                keyword_score += 1
        
        keyword_score = min(keyword_score / len(self.threat_keywords), 1.0)
        
        if self.neural_analyzer:
            try:
                neural_score = self.neural_analyzer.predict_threat(text_sample)
                final_score = (threat_prob * 0.4) + (keyword_score * 0.2) + (neural_score * 0.4)
            except:
                final_score = (threat_prob * 0.7) + (keyword_score * 0.3)
        else:
            final_score = (threat_prob * 0.7) + (keyword_score * 0.3)
        
        return round(final_score, 3)
    
    def analyze_threat_triggers(self, text, threat_score):
        """
        Analyzes what caused a high threat score and returns detailed alert information
        """
        alert_info = {
            'is_high_threat': threat_score >= 0.6,
            'threat_level': self._get_threat_level(threat_score),
            'matched_keywords': [],
            'threat_sentences': [],
            'alert_reasons': []
        }
        
        if not alert_info['is_high_threat']:
            return alert_info
        
        text_sample = text[:5000]
        text_lower = text_sample.lower()
        
        # Find matched threat keywords with context
        for keyword in self.threat_keywords:
            if keyword in text_lower:
                alert_info['matched_keywords'].append(keyword)
                
                # Find sentences containing the keyword
                sentences = re.split(r'[.!?]+', text_sample)
                for sentence in sentences:
                    if keyword in sentence.lower() and len(sentence.strip()) > 10:
                        clean_sentence = sentence.strip()[:200]
                        if clean_sentence not in alert_info['threat_sentences']:
                            alert_info['threat_sentences'].append(clean_sentence)
                        if len(alert_info['threat_sentences']) >= 5:
                            break
        
        # Generate alert reasons
        if len(alert_info['matched_keywords']) > 5:
            alert_info['alert_reasons'].append(f"⚠️ Multiple threat keywords detected ({len(alert_info['matched_keywords'])} keywords)")
        elif len(alert_info['matched_keywords']) > 0:
            alert_info['alert_reasons'].append(f"⚠️ Threat keywords found: {', '.join(alert_info['matched_keywords'][:5])}")
        
        if threat_score >= 0.8:
            alert_info['alert_reasons'].append("🔴 CRITICAL threat score (>= 0.8)")
        elif threat_score >= 0.6:
            alert_info['alert_reasons'].append("🟡 HIGH threat score (>= 0.6)")
        
        # Check for suspicious patterns
        suspicious_patterns = [
            (r'\b(password|credential|login|auth)\b', 'Credential-related content'),
            (r'\b(database|sql|injection)\b', 'Database security content'),
            (r'\b(admin|root|privilege)\b', 'Privileged access content'),
            (r'\b(zero.?day|0day|cve-\d+)\b', 'Exploit/vulnerability references'),
        ]
        
        for pattern, description in suspicious_patterns:
            if re.search(pattern, text_lower):
                alert_info['alert_reasons'].append(f"⚡ {description} detected")
        
        return alert_info
    
    def _get_threat_level(self, score):
        if score >= 0.8:
            return "CRITICAL"
        elif score >= 0.6:
            return "HIGH"
        elif score >= 0.4:
            return "MEDIUM"
        else:
            return "LOW"
    
    def generate_summary(self, text, max_length=500):
        # Clean text first - remove non-printable characters
        clean_text = ''.join(char for char in text if char.isprintable() or char in '\n\r\t ')
        
        if len(clean_text) <= max_length:
            return clean_text
        
        sentences = re.split(r'[.!?]+', clean_text)
        
        summary = ''
        for sentence in sentences:
            if len(summary) + len(sentence) <= max_length:
                summary += sentence + '. '
            else:
                break
        
        return summary.strip()
    
    def generate_report(self, text, url):
        entities = self.extract_entities(text)
        threat_score = self.assess_threat(text)
        summary = self.generate_summary(text)
        alert_info = self.analyze_threat_triggers(text, threat_score)
        
        # Clean text for JSON storage - remove control characters
        clean_text = ''.join(char for char in text[:10000] if char.isprintable() or char in '\n\r\t')
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'url': url,
            'threat_score': threat_score,
            'entities': entities,
            'summary': summary,
            'text_length': len(text),
            'keyword_count': len(entities['keywords']),
            'alert_info': alert_info,
            'full_text': clean_text  # Cleaned text for profiling
        }
        
        # Process person profiling
        if self.person_profiler:
            try:
                persons_count = self.person_profiler.process_report(report)
                report['persons_profiled'] = persons_count
            except Exception as e:
                print(f"[PROFILER] Error processing report: {e}")
                report['persons_profiled'] = 0
        
        return report
    
    def update_neural_model(self, text, actual_threat_label):
        if self.neural_analyzer:
            try:
                self.neural_analyzer.update_with_feedback(text, actual_threat_label)
                return True
            except Exception as e:
                print(f"[NEURAL] Update failed: {e}")
                return False
        return False
    
    def retrain_neural_model(self):
        if self.neural_analyzer:
            try:
                return self.neural_analyzer.train_model(self.threatening_samples, self.non_threatening_samples)
            except Exception as e:
                print(f"[NEURAL] Retrain failed: {e}")
                return False
        return False
    
    def get_neural_model_info(self):
        if self.neural_analyzer:
            return self.neural_analyzer.get_model_info()
        return None
