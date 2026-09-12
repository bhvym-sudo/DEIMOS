import re
import spacy
from typing import Dict, List, Tuple

class LeakDetector:
    def __init__(self):
        self.nlp = spacy.load('en_core_web_sm')
        
        self.database_patterns = [
            r'\b\w+\.sql\b',
            r'\b\w+\.csv\b',
            r'\b\w+\.db\b',
            r'\b\w+\.sqlite\b',
            r'\b\w+dump\b',
            r'\bbackup\b',
            r'\bleaked?\b',
            r'\bbreach\b',
            r'\bdatabase\s+dump\b',
            r'\bdata\s+leak\b',
            r'\bstolen\s+data\b',
            r'\bcredentials\b',
            r'\bpassword\s+list\b',
            r'\buser\s+database\b',
        ]
        
        self.pii_patterns = {
            'aadhaar': r'\b\d{4}\s?\d{4}\s?\d{4}\b',
            'pan': r'\b[A-Z]{5}\d{4}[A-Z]\b',
            'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            'phone': r'\b(?:\+91|0)?[6-9]\d{9}\b',
            'credit_card': r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
        }
        
        self.country_indicators = {
            'india': ['india', 'indian', 'bharat', '.in', '.gov.in', 'aadhaar', 'pan card', 'delhi', 'mumbai', 'bangalore', 'chennai', 'kolkata'],
            'pakistan': ['pakistan', 'pakistani', '.pk', '.gov.pk', 'islamabad', 'karachi', 'lahore', 'rawalpindi'],
            'bangladesh': ['bangladesh', 'bangladeshi', '.bd', '.gov.bd', 'dhaka', 'chittagong'],
        }
        
        self.sensitive_keywords = [
            'government', 'military', 'defense', 'defence', 'army', 'navy', 'air force',
            'ministry', 'cabinet', 'parliament', 'classified', 'secret', 'confidential',
            'intelligence', 'agency', 'police', 'law enforcement', 'border', 'security',
            'banking', 'financial', 'credit', 'debit', 'account', 'transaction',
            'citizen', 'voter', 'census', 'registry', 'passport', 'visa',
        ]
    
    def detect_leak(self, text: str, url: str) -> Dict:
        text_lower = text.lower()
        
        has_database_indicators = any(re.search(pattern, text_lower, re.IGNORECASE) for pattern in self.database_patterns)
        
        if not has_database_indicators:
            return {'is_leak': False}
        
        origin_country = self.identify_country(text_lower, url)
        data_categories = self.identify_data_categories(text_lower)
        pii_types = self.detect_pii_types(text)
        sensitive_level = self.calculate_sensitivity(text_lower)
        
        risk_classification = self.classify_risk(origin_country, sensitive_level, data_categories)
        
        leak_indicators = []
        for pattern in self.database_patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            leak_indicators.extend(matches[:5])
        
        return {
            'is_leak': True,
            'origin_country': origin_country,
            'leak_type': 'database',
            'data_categories': data_categories,
            'pii_types': pii_types,
            'sensitive_level': sensitive_level,
            'risk_classification': risk_classification,
            'leak_indicators': list(set(leak_indicators)),
            'threat_to_india': risk_classification in ['CRITICAL_THREAT', 'HIGH_THREAT'],
        }
    
    def identify_country(self, text: str, url: str) -> str:
        combined = (text + ' ' + url).lower()
        
        scores = {}
        for country, indicators in self.country_indicators.items():
            score = sum(1 for indicator in indicators if indicator in combined)
            if score > 0:
                scores[country] = score
        
        if scores:
            return max(scores.items(), key=lambda x: x[1])[0]
        return 'unknown'
    
    def identify_data_categories(self, text: str) -> List[str]:
        categories = []
        
        if any(kw in text for kw in ['credential', 'password', 'username', 'login']):
            categories.append('credentials')
        if any(kw in text for kw in ['email', 'phone', 'address', 'aadhaar', 'pan', 'passport']):
            categories.append('pii')
        if any(kw in text for kw in ['bank', 'account', 'credit', 'debit', 'transaction', 'payment']):
            categories.append('financial')
        if any(kw in text for kw in ['government', 'ministry', 'official', 'classified']):
            categories.append('government')
        if any(kw in text for kw in ['military', 'defense', 'army', 'navy', 'security']):
            categories.append('military')
        if any(kw in text for kw in ['voter', 'citizen', 'census', 'registry']):
            categories.append('civic')
        
        return categories if categories else ['general']
    
    def detect_pii_types(self, text: str) -> List[str]:
        detected = []
        for pii_type, pattern in self.pii_patterns.items():
            if re.search(pattern, text):
                detected.append(pii_type)
        return detected
    
    def calculate_sensitivity(self, text: str) -> str:
        sensitive_count = sum(1 for kw in self.sensitive_keywords if kw in text)
        
        if sensitive_count >= 5:
            return 'critical'
        elif sensitive_count >= 3:
            return 'high'
        elif sensitive_count >= 1:
            return 'medium'
        return 'low'
    
    def classify_risk(self, country: str, sensitivity: str, categories: List[str]) -> str:
        has_gov_military = bool(set(categories) & {'government', 'military'})
        has_sensitive_pii = bool(set(categories) & {'pii', 'financial', 'civic'})
        
        if country == 'india':
            if has_gov_military or (sensitivity in ['critical', 'high'] and has_sensitive_pii):
                return 'CRITICAL_THREAT'
            elif has_sensitive_pii or sensitivity == 'high':
                return 'HIGH_THREAT'
            else:
                return 'MEDIUM_THREAT'
        
        elif country in ['pakistan', 'bangladesh']:
            if has_gov_military or sensitivity == 'critical':
                return 'STRATEGIC_ADVANTAGE'
            elif has_sensitive_pii or sensitivity == 'high':
                return 'INTELLIGENCE_VALUE'
            else:
                return 'MONITOR'
        
        else:
            if sensitivity in ['critical', 'high']:
                return 'INTERNATIONAL_CONCERN'
            return 'LOW_PRIORITY'
