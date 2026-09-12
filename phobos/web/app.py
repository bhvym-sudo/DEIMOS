from flask import Flask, render_template, jsonify, request
import json
import os
import sqlite3
import re

app = Flask(__name__, template_folder='../templates')

DB_PATH = 'databases/phobos_analysis.db'

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def load_all_reports():
    """Load all threat analysis reports from database"""
    reports = []
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                t.id,
                t.page_id,
                t.url,
                t.threat_score,
                t.threat_level,
                t.matched_keywords,
                t.threat_sentences,
                t.alert_reasons,
                t.analyzed_at,
                n.persons,
                n.organizations,
                n.locations,
                n.dates,
                n.money
            FROM threat_analysis t
            LEFT JOIN ner_results n ON t.ner_id = n.id
            ORDER BY t.analyzed_at DESC
        """)
        
        rows = cursor.fetchall()
        
        for row in rows:
            report = {
                'id': row['id'],
                'page_id': row['page_id'],
                'url': row['url'],
                'threat_score': row['threat_score'],
                'alert_info': {
                    'threat_level': row['threat_level'],
                    'matched_keywords': json.loads(row['matched_keywords']) if row['matched_keywords'] else [],
                    'threat_sentences': json.loads(row['threat_sentences']) if row['threat_sentences'] else [],
                    'alert_reasons': json.loads(row['alert_reasons']) if row['alert_reasons'] else []
                },
                'entities': {
                    'persons': json.loads(row['persons']) if row['persons'] else [],
                    'organizations': json.loads(row['organizations']) if row['organizations'] else [],
                    'locations': json.loads(row['locations']) if row['locations'] else [],
                    'dates': json.loads(row['dates']) if row['dates'] else [],
                    'money': json.loads(row['money']) if row['money'] else []
                },
                'timestamp': row['analyzed_at'],
                'filename': f"report_{row['page_id']}.json"
            }
            reports.append(report)
        
        conn.close()
        
    except Exception as e:
        print(f"Error loading reports from database: {e}")
    
    return reports

def search_reports(reports, query):
    """Search through reports with relevance scoring"""
    if not query or not query.strip():
        return reports
    
    query_lower = query.lower().strip()
    query_terms = re.findall(r'\w+', query_lower)
    
    scored_reports = []
    
    for report in reports:
        score = 0
        
        # Search in URL (weight: 5)
        url = report.get('url', '').lower()
        if query_lower in url:
            score += 5
        for term in query_terms:
            if term in url:
                score += 2
        
        # Search in summary (weight: 3)
        summary = report.get('summary', '').lower()
        if query_lower in summary:
            score += 3
        for term in query_terms:
            if term in summary:
                score += 1
        
        # Search in full text (weight: 2)
        full_text = report.get('full_text', '').lower()
        if query_lower in full_text:
            score += 2
        for term in query_terms:
            score += full_text.count(term) * 0.5
        
        # Search in entities (weight: 4)
        entities = report.get('entities', {})
        for entity_type in ['persons', 'organizations', 'locations', 'dates']:
            entity_list = entities.get(entity_type, [])
            for entity in entity_list:
                entity_lower = str(entity).lower()
                if query_lower in entity_lower:
                    score += 4
                for term in query_terms:
                    if term in entity_lower:
                        score += 2
        
        # Search in matched keywords (weight: 5)
        keywords = report.get('alert_info', {}).get('matched_keywords', [])
        for keyword in keywords:
            keyword_lower = str(keyword).lower()
            if query_lower in keyword_lower:
                score += 5
            for term in query_terms:
                if term in keyword_lower:
                    score += 3
        
        # Search in threat level (weight: 3)
        threat_level = report.get('alert_info', {}).get('threat_level', '').lower()
        if query_lower == threat_level:
            score += 3
        
        # Search in threat sentences (weight: 4)
        threat_sentences = report.get('alert_info', {}).get('threat_sentences', [])
        for sentence in threat_sentences:
            sentence_lower = str(sentence).lower()
            if query_lower in sentence_lower:
                score += 4
            for term in query_terms:
                if term in sentence_lower:
                    score += 1
        
        if score > 0:
            report['search_score'] = score
            scored_reports.append(report)
    
    # Sort by relevance score (highest first)
    scored_reports.sort(key=lambda x: x.get('search_score', 0), reverse=True)
    return scored_reports

@app.route('/')
def index():
    """Display all reports in Google-style search results format"""
    query = request.args.get('q', '').strip()
    all_reports = load_all_reports()
    
    if query:
        reports = search_reports(all_reports, query)
    else:
        reports = all_reports
    
    return render_template('index.html', reports=reports, total=len(all_reports), query=query)

@app.route('/report/<int:report_id>')
def get_report_details(report_id):
    """Get detailed report data as JSON from database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                t.id,
                t.page_id,
                t.url,
                t.threat_score,
                t.threat_level,
                t.matched_keywords,
                t.threat_sentences,
                t.alert_reasons,
                t.analyzed_at,
                n.persons,
                n.organizations,
                n.locations,
                n.dates,
                n.money
            FROM threat_analysis t
            LEFT JOIN ner_results n ON t.ner_id = n.id
            WHERE t.id = ?
        """, (report_id,))
        
        row = cursor.fetchone()
        
        if row:
            report = {
                'id': row['id'],
                'page_id': row['page_id'],
                'url': row['url'],
                'threat_score': row['threat_score'],
                'alert_info': {
                    'threat_level': row['threat_level'],
                    'matched_keywords': json.loads(row['matched_keywords']) if row['matched_keywords'] else [],
                    'threat_sentences': json.loads(row['threat_sentences']) if row['threat_sentences'] else [],
                    'alert_reasons': json.loads(row['alert_reasons']) if row['alert_reasons'] else []
                },
                'entities': {
                    'persons': json.loads(row['persons']) if row['persons'] else [],
                    'organizations': json.loads(row['organizations']) if row['organizations'] else [],
                    'locations': json.loads(row['locations']) if row['locations'] else [],
                    'dates': json.loads(row['dates']) if row['dates'] else [],
                    'money': json.loads(row['money']) if row['money'] else []
                },
                'timestamp': row['analyzed_at']
            }
            conn.close()
            return jsonify(report)
        
        conn.close()
        return jsonify({'error': 'Report not found'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=7788)
