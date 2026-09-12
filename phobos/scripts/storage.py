import json
from pathlib import Path
from datetime import datetime
import hashlib


class DataStorage:
    
    def __init__(self, reports_dir='reports'):
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(exist_ok=True)
    
    def save_report(self, report_data):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        
        url = report_data.get('url', '')
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        
        filename = f"report_{timestamp}_{url_hash}.json"
        filepath = self.reports_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=4, ensure_ascii=False, default=str)
        
        return str(filepath)
    
    def save_data(self, data, filename=None):
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            filename = f"data_{timestamp}.json"
        
        filepath = self.reports_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False, default=str)
        
        return str(filepath)
    
    def load_report(self, filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return data
    
    def list_reports(self):
        reports = list(self.reports_dir.glob('report_*.json'))
        return [str(r) for r in reports]
    
    def generate_overall_report(self):
        all_reports = []
        
        for report_path in self.list_reports():
            try:
                report = self.load_report(report_path)
                all_reports.append(report)
            except json.JSONDecodeError as e:
                print(f"[WARNING] Skipping corrupted report {report_path}: {e}")
                continue
            except Exception as e:
                print(f"[WARNING] Error loading report {report_path}: {e}")
                continue
        
        if not all_reports:
            return {
                'total_pages': 0,
                'message': 'No reports available'
            }
        
        threat_scores = [r.get('threat_score', 0) for r in all_reports]
        
        high_threats = [r for r in all_reports if r.get('threat_score', 0) >= 0.5]
        medium_threats = [r for r in all_reports if 0.3 <= r.get('threat_score', 0) < 0.5]
        low_threats = [r for r in all_reports if r.get('threat_score', 0) < 0.3]
        
        all_entities = {
            'persons': [],
            'organizations': [],
            'locations': [],
            'keywords': []
        }
        
        for report in all_reports:
            entities = report.get('entities', {})
            all_entities['persons'].extend(entities.get('persons', []))
            all_entities['organizations'].extend(entities.get('organizations', []))
            all_entities['locations'].extend(entities.get('locations', []))
            all_entities['keywords'].extend(entities.get('keywords', []))
        
        for key in all_entities:
            all_entities[key] = list(set(all_entities[key]))
        
        entity_counts = {
            'persons': len(all_entities['persons']),
            'organizations': len(all_entities['organizations']),
            'locations': len(all_entities['locations']),
            'keywords': len(all_entities['keywords'])
        }
        
        overall_report = {
            'report_metadata': {
                'generated_at': datetime.now().isoformat(),
                'total_pages_analyzed': len(all_reports)
            },
            'threat_analysis': {
                'statistics': {
                    'average_threat_score': round(sum(threat_scores) / len(threat_scores), 3),
                    'max_threat_score': round(max(threat_scores), 3),
                    'min_threat_score': round(min(threat_scores), 3)
                },
                'categorization': {
                    'high_threat_count': len(high_threats),
                    'medium_threat_count': len(medium_threats),
                    'low_threat_count': len(low_threats)
                },
                'high_threats': [
                    {
                        'url': r.get('url'),
                        'threat_score': r.get('threat_score'),
                        'keywords': r.get('entities', {}).get('keywords', []),
                        'timestamp': r.get('timestamp')
                    } for r in sorted(high_threats, key=lambda x: x.get('threat_score', 0), reverse=True)
                ],
                'medium_threats': [
                    {
                        'url': r.get('url'),
                        'threat_score': r.get('threat_score'),
                        'keywords': r.get('entities', {}).get('keywords', []),
                        'timestamp': r.get('timestamp')
                    } for r in sorted(medium_threats, key=lambda x: x.get('threat_score', 0), reverse=True)
                ],
                'low_threats': [
                    {
                        'url': r.get('url'),
                        'threat_score': r.get('threat_score'),
                        'timestamp': r.get('timestamp')
                    } for r in sorted(low_threats, key=lambda x: x.get('threat_score', 0), reverse=True)
                ]
            },
            'entity_analysis': {
                'summary': entity_counts,
                'top_persons': all_entities['persons'][:20],
                'top_organizations': all_entities['organizations'][:20],
                'top_locations': all_entities['locations'][:20],
                'threat_keywords_found': all_entities['keywords']
            },
            'page_details': [
                {
                    'url': r.get('url'),
                    'threat_score': r.get('threat_score'),
                    'threat_level': 'HIGH' if r.get('threat_score', 0) >= 0.5 else 'MEDIUM' if r.get('threat_score', 0) >= 0.3 else 'LOW',
                    'entities': r.get('entities', {}),
                    'summary': r.get('summary', ''),
                    'text_length': r.get('text_length', 0),
                    'timestamp': r.get('timestamp')
                } for r in sorted(all_reports, key=lambda x: x.get('threat_score', 0), reverse=True)
            ]
        }
        
        return overall_report
