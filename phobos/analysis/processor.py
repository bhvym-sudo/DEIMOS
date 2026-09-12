import sqlite3
import spacy
import json
from pathlib import Path
from datetime import datetime
from scripts.analyzer import IntelligenceAnalyzer
from analysis.leak_detector import LeakDetector

class NERProcessor:
    def __init__(self, database_path='databases/crawler.db', engine='crawler'):
        self.database_path = database_path
        self.engine = engine
        self.go_db = sqlite3.connect(database_path, timeout=30)
        self.analysis_db = self._init_analysis_db(database_path)
        self.go_db.execute("PRAGMA busy_timeout=30000")
        self.analysis_db.execute("PRAGMA busy_timeout=30000")
        self.nlp = spacy.load("en_core_web_sm")
        self.analyzer = IntelligenceAnalyzer()
        self.leak_detector = LeakDetector()
    
    def _init_analysis_db(self, database_path):
        conn = sqlite3.connect(database_path, timeout=30)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ner_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_id INTEGER UNIQUE,
                url TEXT,
                persons TEXT,
                organizations TEXT,
                locations TEXT,
                dates TEXT,
                money TEXT,
                processed_at TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS threat_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_id INTEGER,
                ner_id INTEGER,
                url TEXT,
                threat_score REAL,
                threat_level TEXT,
                matched_keywords TEXT,
                threat_sentences TEXT,
                alert_reasons TEXT,
                json_report_path TEXT,
                analyzed_at TIMESTAMP,
                leak_detected BOOLEAN DEFAULT 0,
                leak_type TEXT,
                origin_country TEXT,
                risk_classification TEXT,
                data_categories TEXT,
                pii_types TEXT,
                sensitive_level TEXT,
                leak_indicators TEXT,
                threat_to_india BOOLEAN DEFAULT 0,
                FOREIGN KEY(ner_id) REFERENCES ner_results(id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processing_status (
                page_id INTEGER PRIMARY KEY,
                url TEXT,
                ner_done BOOLEAN DEFAULT 0,
                threat_analysis_done BOOLEAN DEFAULT 0,
                last_processed TIMESTAMP
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ner_page_id ON ner_results(page_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_threat_page_id ON threat_analysis(page_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_threat_level ON threat_analysis(threat_level)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_threat_score ON threat_analysis(threat_score)")
        
        conn.commit()
        return conn
    
    def get_unprocessed_pages(self, limit=100):
        cursor = self.go_db.cursor()
        
        processed_ids = [row[0] for row in self.analysis_db.execute(
            "SELECT page_id FROM processing_status WHERE ner_done = 1"
        ).fetchall()]
        
        if processed_ids:
            placeholders = ','.join('?' * len(processed_ids))
            query = f"""
                SELECT id, url, html_content, content, crawled_at
                FROM pages 
                WHERE is_active = 1 
                AND html_content IS NOT NULL
                AND id NOT IN ({placeholders})
                ORDER BY crawled_at DESC
                LIMIT ?
            """
            pages = cursor.execute(query, (*processed_ids, limit)).fetchall()
        else:
            pages = cursor.execute("""
                SELECT id, url, html_content, content, crawled_at
                FROM pages 
                WHERE is_active = 1 
                AND html_content IS NOT NULL
                ORDER BY crawled_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
        
        return pages
    
    def extract_entities(self, text):
        doc = self.nlp(text[:1000000])
        
        entities = {
            'persons': list(set([ent.text for ent in doc.ents if ent.label_ == 'PERSON'])),
            'organizations': list(set([ent.text for ent in doc.ents if ent.label_ == 'ORG'])),
            'locations': list(set([ent.text for ent in doc.ents if ent.label_ in ['GPE', 'LOC']])),
            'dates': list(set([ent.text for ent in doc.ents if ent.label_ == 'DATE'])),
            'money': list(set([ent.text for ent in doc.ents if ent.label_ == 'MONEY']))
        }
        
        return entities
    
    def save_ner_results(self, page_id, url, entities):
        cursor = self.analysis_db.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO ner_results 
            (page_id, url, persons, organizations, locations, dates, money, processed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            page_id, url,
            json.dumps(entities['persons']),
            json.dumps(entities['organizations']),
            json.dumps(entities['locations']),
            json.dumps(entities['dates']),
            json.dumps(entities['money']),
            datetime.now().isoformat()
        ))
        
        self.analysis_db.commit()
        return cursor.lastrowid
    
    def analyze_threat(self, text, entities):
        analysis = self.analyzer.generate_report(text, '')
        analysis['entities'] = entities
        analysis['timestamp'] = datetime.now().isoformat()
        return analysis
    
    def save_threat_analysis(self, page_id, ner_id, url, analysis, leak_info, save_json=False):
        cursor = self.analysis_db.cursor()
        
        json_path = None
        
        if save_json and analysis.get('threat_score', 0) > 0.4:
            json_path = f"reports/report_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{page_id}.json"
            Path('reports').mkdir(exist_ok=True)
            
            analysis['full_text'] = analysis.get('full_text', '')
            analysis['url'] = url
            analysis['page_id'] = page_id
            analysis['leak_info'] = leak_info
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(analysis, f, indent=4, ensure_ascii=False, default=str)
        
        cursor.execute("""
            INSERT INTO threat_analysis 
            (page_id, ner_id, url, threat_score, threat_level, matched_keywords, 
             threat_sentences, alert_reasons, json_report_path, analyzed_at,
             leak_detected, leak_type, origin_country, risk_classification,
             data_categories, pii_types, sensitive_level, leak_indicators, threat_to_india)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            page_id, ner_id, url,
            analysis.get('threat_score', 0),
            analysis.get('alert_info', {}).get('threat_level', 'LOW'),
            json.dumps(analysis.get('alert_info', {}).get('matched_keywords', []), default=str),
            json.dumps(analysis.get('alert_info', {}).get('threat_sentences', []), default=str),
            json.dumps(analysis.get('alert_info', {}).get('alert_reasons', []), default=str),
            json_path,
            datetime.now().isoformat(),
            leak_info.get('is_leak', False),
            leak_info.get('leak_type'),
            leak_info.get('origin_country'),
            leak_info.get('risk_classification'),
            json.dumps(leak_info.get('data_categories', [])),
            json.dumps(leak_info.get('pii_types', [])),
            leak_info.get('sensitive_level'),
            json.dumps(leak_info.get('leak_indicators', [])),
            leak_info.get('threat_to_india', False)
        ))
        
        self.analysis_db.commit()
        self.go_db.execute(
            "UPDATE pages SET threat_score = ?, threat_level = ?, analyzed_at = ? WHERE id = ?",
            (analysis.get('threat_score', 0), analysis.get('alert_info', {}).get('threat_level', 'LOW'), datetime.now().isoformat(), page_id)
        )
        self.go_db.commit()
    
    def update_processing_status(self, page_id, url):
        cursor = self.analysis_db.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO processing_status 
            (page_id, url, ner_done, threat_analysis_done, last_processed)
            VALUES (?, ?, 1, 1, ?)
        """, (page_id, url, datetime.now().isoformat()))
        self.analysis_db.commit()
    
    def process_batch(self, limit=100, save_json_threshold=0.4):
        pages = self.get_unprocessed_pages(limit)
        
        print(f"Processing {len(pages)} pages...")
        
        for i, (page_id, url, html, text, crawled_at) in enumerate(pages, 1):
            try:
                print(f"[{i}/{len(pages)}] Processing: {url[:60]}...")
                
                entities = self.extract_entities(text)
                ner_id = self.save_ner_results(page_id, url, entities)
                
                analysis = self.analyze_threat(text, entities)
                analysis['full_text'] = text
                analysis['text_length'] = len(text)
                
                leak_info = self.leak_detector.detect_leak(text, url)
                if leak_info.get('is_leak'):
                    print(f"  [LEAK DETECTED] {leak_info.get('risk_classification')} - {leak_info.get('origin_country')}")
                
                save_json = analysis.get('threat_score', 0) >= save_json_threshold or leak_info.get('threat_to_india', False)
                self.save_threat_analysis(page_id, ner_id, url, analysis, leak_info, save_json)
                
                self.update_processing_status(page_id, url)
                
                if save_json:
                    print(f"  ⚠️  HIGH THREAT ({analysis['threat_score']:.2f}) - JSON saved")
                else:
                    print(f"  ✓ Analyzed (score: {analysis['threat_score']:.2f})")
                
            except Exception as e:
                print(f"  ❌ Error: {e}")
                continue
        
        print(f"\n✓ Batch complete: {len(pages)} pages processed")
    
    def get_statistics(self):
        go_total = self.go_db.execute("SELECT COUNT(*) FROM pages WHERE is_active = 1").fetchone()[0]
        ner_done = self.analysis_db.execute("SELECT COUNT(*) FROM ner_results").fetchone()[0]
        threats = self.analysis_db.execute("SELECT COUNT(*) FROM threat_analysis WHERE threat_score > 0.4").fetchone()[0]
        json_saved = self.analysis_db.execute("SELECT COUNT(*) FROM threat_analysis WHERE json_report_path IS NOT NULL").fetchone()[0]
        
        return {
            'total_pages_in_go': go_total,
            'ner_processed': ner_done,
            'threats_found': threats,
            'json_reports_saved': json_saved,
            'pending': go_total - ner_done
        }
    
    def close(self):
        self.go_db.close()
        self.analysis_db.close()
