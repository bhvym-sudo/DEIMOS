from flask import Flask, render_template, request
import sqlite3
import os
import re

app = Flask(__name__, template_folder='../templates')

DB_PATH = 'databases/phobos_index.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def count_indexed_pages():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM pages WHERE is_active = 1")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except:
        return 0

def get_queue_size():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM crawl_queue WHERE status = 'pending'")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except:
        return 0

def perform_search(query):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        search_terms = query.lower().split()
        
        cursor.execute("""
            SELECT id, url, title, domain, content, crawled_at
            FROM pages
            WHERE is_active = 1
            AND (LOWER(title) LIKE ? OR LOWER(content) LIKE ? OR LOWER(url) LIKE ?)
            ORDER BY crawled_at DESC
            LIMIT 100
        """, (f'%{query}%', f'%{query}%', f'%{query}%'))
        
        results = []
        for row in cursor.fetchall():
            score = 0
            title_lower = (row['title'] or '').lower()
            content_lower = (row['content'] or '').lower()
            url_lower = row['url'].lower()
            
            for term in search_terms:
                if term in title_lower:
                    score += 10
                if term in url_lower:
                    score += 5
                if term in content_lower:
                    score += content_lower.count(term)
            
            snippet = row['content'][:300] if row['content'] else "No content available"
            
            results.append({
                'id': row['id'],
                'url': row['url'],
                'title': row['title'] or 'Untitled',
                'domain': row['domain'],
                'snippet': snippet,
                'crawled_at': row['crawled_at'],
                'score': score
            })
        
        results.sort(key=lambda x: x['score'], reverse=True)
        
        conn.close()
        return results[:50]
        
    except Exception as e:
        print(f"Search error: {e}")
        return []

@app.route('/')
def home():
    indexed = count_indexed_pages()
    queue = get_queue_size()
    
    return render_template('search.html', 
                         indexed_count=indexed,
                         queue_size=queue,
                         active_crawlers=20)

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    
    if not query:
        return home()
    
    results = perform_search(query)
    indexed = count_indexed_pages()
    
    return render_template('search_results.html',
                         query=query,
                         results=results,
                         result_count=len(results),
                         indexed_count=indexed)

if __name__ == '__main__':
    app.run(debug=True, port=8080)
