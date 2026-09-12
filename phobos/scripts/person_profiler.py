import spacy
import re
from collections import defaultdict
from datetime import datetime
import json
import os


class PersonProfiler:
    """
    Advanced person profiling system using NER and pattern matching
    Extracts person names and their activities from web content
    """
    
    def __init__(self):
        try:
            self.nlp = spacy.load('en_core_web_sm')
        except:
            self.nlp = None
            print("Warning: spaCy model not loaded")
        
        self.profiles_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'config_files',
            'profiles.json'
        )
        
        self.profiles = self.load_profiles()
    
    def load_profiles(self):
        """Load existing person profiles from JSON file"""
        try:
            if os.path.exists(self.profiles_file):
                with open(self.profiles_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                return {}
        except Exception as e:
            print(f"Error loading profiles: {e}")
            return {}
    
    def save_profiles(self):
        """Save person profiles to JSON file"""
        try:
            with open(self.profiles_file, 'w', encoding='utf-8') as f:
                json.dump(self.profiles, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving profiles: {e}")
            return False
    
    def extract_persons_advanced(self, text, url=""):
        """
        Advanced person extraction using multiple techniques:
        1. spaCy NER for PERSON entities
        2. Pattern matching for common name formats
        3. Context analysis for role identification
        """
        persons_data = []
        
        if not text or len(text) == 0:
            return persons_data
        
        # Use spaCy for NER
        if self.nlp:
            doc = self.nlp(text[:100000])  # Process up to 100k chars
            
            for ent in doc.ents:
                if ent.label_ == 'PERSON':
                    person_name = self._clean_person_name(ent.text)
                    if self._is_valid_person_name(person_name):
                        context = self._extract_context(text, ent.text)
                        
                        persons_data.append({
                            'name': person_name,
                            'context': context,
                            'source_url': url,
                            'extraction_method': 'spacy_ner'
                        })
        
        # Pattern-based extraction for names with titles
        title_pattern = r'\b(Mr|Mrs|Ms|Dr|Prof|Professor)\.\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'
        for match in re.finditer(title_pattern, text):
            person_name = match.group(2)
            if self._is_valid_person_name(person_name):
                context = self._extract_context(text, match.group(0))
                persons_data.append({
                    'name': person_name,
                    'title': match.group(1),
                    'context': context,
                    'source_url': url,
                    'extraction_method': 'pattern_title'
                })
        
        # Extract from author tags, bylines, etc.
        author_patterns = [
            r'(?:by|author|posted by|written by)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})',
            r'(?:@|u/)([A-Za-z0-9_]{3,20})',  # Social media handles
        ]
        
        for pattern in author_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                person_name = self._clean_person_name(match.group(1))
                if self._is_valid_person_name(person_name):
                    context = self._extract_context(text, match.group(0))
                    persons_data.append({
                        'name': person_name,
                        'context': context,
                        'source_url': url,
                        'extraction_method': 'pattern_author'
                    })
        
        return persons_data
    
    def _clean_person_name(self, name):
        """Clean and normalize person names"""
        # Remove extra whitespace
        name = ' '.join(name.split())
        # Remove common prefixes/suffixes
        name = re.sub(r'\b(said|says|wrote|posted|commented)\b', '', name, flags=re.IGNORECASE)
        name = name.strip(',.:;"\'')
        return name.strip()
    
    def _is_valid_person_name(self, name):
        """Validate if extracted text is likely a real person name"""
        if not name or len(name) < 3:
            return False
        
        # Must start with capital letter
        if not name[0].isupper():
            return False
        
        # Reject common false positives
        false_positives = [
            'January', 'February', 'March', 'April', 'May', 'June', 'July',
            'August', 'September', 'October', 'November', 'December',
            'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
            'Copyright', 'Terms', 'Privacy', 'About', 'Contact', 'Home',
            'News', 'Search', 'Login', 'Register', 'Subscribe'
        ]
        
        if name in false_positives:
            return False
        
        # Must contain at least one letter
        if not re.search(r'[a-zA-Z]', name):
            return False
        
        return True
    
    def _extract_context(self, text, entity_text, context_window=200):
        """Extract surrounding context for an entity"""
        try:
            # Find the entity in text
            idx = text.find(entity_text)
            if idx == -1:
                return ""
            
            # Extract context window
            start = max(0, idx - context_window)
            end = min(len(text), idx + len(entity_text) + context_window)
            
            context = text[start:end].strip()
            
            # Clean up context - remove non-printable characters
            context = ''.join(char for char in context if char.isprintable() or char in '\n\r\t ')
            context = ' '.join(context.split())
            
            return context
        except:
            return ""
    
    def analyze_person_activity(self, person_name, context, url):
        """
        Analyze what a person is doing based on context
        Returns activity type and description
        """
        context_lower = context.lower()
        
        activities = {
            'commenting': ['comment', 'replied', 'response', 'said'],
            'posting': ['posted', 'published', 'shared', 'wrote'],
            'authoring': ['author', 'by', 'written by'],
            'speaking': ['said', 'stated', 'mentioned', 'announced'],
            'researching': ['research', 'study', 'findings', 'discovered'],
            'developing': ['developed', 'created', 'built', 'designed']
        }
        
        detected_activities = []
        
        for activity_type, keywords in activities.items():
            for keyword in keywords:
                if keyword in context_lower:
                    detected_activities.append(activity_type)
                    break
        
        # Extract what they said/did
        content_patterns = [
            r'(?:said|stated|wrote|posted|commented)[:"]?\s*"([^"]{10,200})"',
            r'(?:said|stated|wrote|posted|commented)[:"]?\s*([^.!?]{10,200}[.!?])',
        ]
        
        extracted_content = ""
        for pattern in content_patterns:
            match = re.search(pattern, context, re.IGNORECASE)
            if match:
                extracted_content = match.group(1).strip()
                break
        
        return {
            'activities': detected_activities if detected_activities else ['mentioned'],
            'content': extracted_content,
            'context': context[:300]
        }
    
    def update_profile(self, person_data, url, report_timestamp):
        """
        Update or create a person's profile with new data
        """
        person_name = person_data['name']
        context = person_data.get('context', '')
        
        # Analyze activity
        activity_info = self.analyze_person_activity(person_name, context, url)
        
        # Initialize profile if doesn't exist
        if person_name not in self.profiles:
            self.profiles[person_name] = {
                'name': person_name,
                'first_seen': report_timestamp,
                'last_seen': report_timestamp,
                'total_mentions': 0,
                'urls': [],
                'activities': [],
                'keywords': [],
                'titles': []
            }
        
        profile = self.profiles[person_name]
        
        # Update profile data
        profile['last_seen'] = report_timestamp
        profile['total_mentions'] += 1
        
        # Add URL if not already present
        if url not in profile['urls']:
            profile['urls'].append(url)
        
        # Add activity record
        activity_record = {
            'timestamp': report_timestamp,
            'url': url,
            'activity_types': activity_info['activities'],
            'content': activity_info['content'],
            'context': activity_info['context'],
            'extraction_method': person_data.get('extraction_method', 'unknown')
        }
        profile['activities'].append(activity_record)
        
        # Add title if present
        if 'title' in person_data and person_data['title'] not in profile['titles']:
            profile['titles'].append(person_data['title'])
        
        # Extract and store keywords from context
        keywords = self._extract_keywords(context)
        for kw in keywords:
            if kw not in profile['keywords']:
                profile['keywords'].append(kw)
        
        return True
    
    def _extract_keywords(self, text):
        """Extract important keywords from text"""
        # Simple keyword extraction - can be enhanced
        words = re.findall(r'\b[A-Z][a-z]{3,}\b', text)
        return list(set(words))[:10]
    
    def process_report(self, report):
        """
        Process a report and extract all persons with their activities
        """
        url = report.get('url', '')
        timestamp = report.get('timestamp', datetime.now().isoformat())
        
        # Get text from summary or full content
        text = report.get('summary', '') + ' ' + report.get('full_text', '')
        
        if not text.strip():
            return 0
        
        # Extract persons
        persons_data = self.extract_persons_advanced(text, url)
        
        # Update profiles
        updated_count = 0
        for person_data in persons_data:
            if self.update_profile(person_data, url, timestamp):
                updated_count += 1
        
        # Save profiles
        if updated_count > 0:
            self.save_profiles()
        
        return updated_count
    
    def generate_person_intelligence_briefing(self, person_name):
        """
        Generate comprehensive intelligence briefing for a person
        """
        if person_name not in self.profiles:
            return None
        
        profile = self.profiles[person_name]
        
        # Analyze activity patterns
        activity_summary = self._analyze_activity_patterns(profile['activities'])
        
        # Generate briefing
        briefing = {
            'name': person_name,
            'profile_summary': {
                'total_mentions': profile['total_mentions'],
                'first_seen': profile['first_seen'],
                'last_seen': profile['last_seen'],
                'urls_count': len(profile['urls']),
                'activities_count': len(profile['activities']),
                'titles': profile.get('titles', [])
            },
            'activity_analysis': activity_summary,
            'recent_activities': profile['activities'][-10:],  # Last 10 activities
            'all_urls': profile['urls'],
            'keywords': profile['keywords'][:20],  # Top 20 keywords
            'timeline': self._create_timeline(profile['activities'])
        }
        
        return briefing
    
    def _analyze_activity_patterns(self, activities):
        """Analyze patterns in person's activities"""
        activity_types = defaultdict(int)
        content_samples = []
        
        for activity in activities:
            for act_type in activity.get('activity_types', []):
                activity_types[act_type] += 1
            
            if activity.get('content'):
                content_samples.append(activity['content'])
        
        return {
            'activity_breakdown': dict(activity_types),
            'most_common_activity': max(activity_types.items(), key=lambda x: x[1])[0] if activity_types else 'mentioned',
            'content_samples': content_samples[:5]  # Top 5 content samples
        }
    
    def _create_timeline(self, activities):
        """Create chronological timeline of activities"""
        timeline = []
        
        for activity in sorted(activities, key=lambda x: x.get('timestamp', ''), reverse=True)[:15]:
            timeline.append({
                'timestamp': activity.get('timestamp', 'Unknown'),
                'url': activity.get('url', 'Unknown'),
                'activities': ', '.join(activity.get('activity_types', [])),
                'preview': activity.get('context', '')[:150]
            })
        
        return timeline
    
    def get_all_persons(self):
        """Get list of all profiled persons"""
        return [{
            'name': name,
            'total_mentions': data['total_mentions'],
            'last_seen': data['last_seen'],
            'urls_count': len(data['urls'])
        } for name, data in self.profiles.items()]
    
    def search_persons(self, query):
        """Search for persons by name"""
        query_lower = query.lower()
        results = []
        
        for name, data in self.profiles.items():
            if query_lower in name.lower():
                results.append({
                    'name': name,
                    'total_mentions': data['total_mentions'],
                    'last_seen': data['last_seen']
                })
        
        return results
