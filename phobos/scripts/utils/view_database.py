"""
Display content from PHOBOS-search SQLite database
"""
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = 'PHOBOS-search/phobos_index.db'

def connect_db():
    """Connect to the database"""
    if not Path(DB_PATH).exists():
        print(f"❌ Database not found at {DB_PATH}")
        print("Run the Go crawler first: cd PHOBOS-search && go run .")
        return None
    return sqlite3.connect(DB_PATH)

def show_statistics(conn):
    """Display database statistics"""
    print("\n" + "="*60)
    print("📊 DATABASE STATISTICS")
    print("="*60)
    
    cursor = conn.cursor()
    
    # Total pages
    total = cursor.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    print(f"Total Pages Indexed: {total}")
    
    # Active pages
    active = cursor.execute("SELECT COUNT(*) FROM pages WHERE is_active = 1").fetchone()[0]
    print(f"Active Pages: {active}")
    
    # Total tokens
    tokens = cursor.execute("SELECT COUNT(*) FROM tokens").fetchone()[0]
    print(f"Unique Tokens: {tokens:,}")
    
    # Total links
    links = cursor.execute("SELECT COUNT(*) FROM links").fetchone()[0]
    print(f"Links Tracked: {links:,}")
    
    # Recent crawls
    recent = cursor.execute("""
        SELECT COUNT(*) FROM pages 
        WHERE datetime(crawled_at) > datetime('now', '-1 day')
    """).fetchone()[0]
    print(f"Crawled in Last 24h: {recent}")

def show_recent_pages(conn, limit=10):
    """Display recent crawled pages"""
    print("\n" + "="*60)
    print(f"📄 RECENT PAGES (Last {limit})")
    print("="*60)
    
    cursor = conn.cursor()
    pages = cursor.execute("""
        SELECT url, title, content_length, crawled_at, status_code
        FROM pages 
        WHERE is_active = 1
        ORDER BY crawled_at DESC 
        LIMIT ?
    """, (limit,)).fetchall()
    
    for i, (url, title, length, crawled, status) in enumerate(pages, 1):
        print(f"\n{i}. {url}")
        print(f"   Title: {title[:70] if title else 'No title'}...")
        print(f"   Size: {length} chars | Status: {status} | Crawled: {crawled}")

def show_page_content(conn, page_id=None):
    """Display full content of a specific page"""
    cursor = conn.cursor()
    
    if page_id is None:
        # Get the most recent page
        page = cursor.execute("""
            SELECT id, url, title, content, html_content, crawled_at
            FROM pages 
            WHERE is_active = 1 AND content IS NOT NULL
            ORDER BY crawled_at DESC 
            LIMIT 1
        """).fetchone()
    else:
        page = cursor.execute("""
            SELECT id, url, title, content, html_content, crawled_at
            FROM pages 
            WHERE id = ?
        """, (page_id,)).fetchone()
    
    if not page:
        print("No page found")
        return
    
    page_id, url, title, content, html, crawled = page
    
    print("\n" + "="*60)
    print(f"📖 PAGE DETAILS (ID: {page_id})")
    print("="*60)
    print(f"URL: {url}")
    print(f"Title: {title}")
    print(f"Crawled: {crawled}")
    print(f"\nContent Preview (first 500 chars):")
    print("-" * 60)
    print(content[:500] if content else "No content")
    print("-" * 60)
    
    if html:
        print(f"\nHTML Length: {len(html)} bytes")
        print(f"HTML Preview (first 300 chars):")
        print("-" * 60)
        print(html[:300])
        print("-" * 60)

def show_entities(conn, limit=5):
    """Show pages with their content for entity extraction"""
    print("\n" + "="*60)
    print(f"🔍 PAGES FOR ENTITY EXTRACTION (Sample {limit})")
    print("="*60)
    
    cursor = conn.cursor()
    pages = cursor.execute("""
        SELECT id, url, content, html_content
        FROM pages 
        WHERE is_active = 1 AND content IS NOT NULL
        ORDER BY RANDOM()
        LIMIT ?
    """, (limit,)).fetchall()
    
    for i, (page_id, url, content, html) in enumerate(pages, 1):
        print(f"\n{i}. ID: {page_id}")
        print(f"   URL: {url}")
        print(f"   Content Length: {len(content)} chars")
        print(f"   HTML Length: {len(html) if html else 0} bytes")
        print(f"   Content Preview: {content[:150]}...")

def show_search_example(conn, query="weapon"):
    """Show example search through database"""
    print("\n" + "="*60)
    print(f"🔎 SEARCH EXAMPLE: '{query}'")
    print("="*60)
    
    cursor = conn.cursor()
    results = cursor.execute("""
        SELECT id, url, title, content
        FROM pages 
        WHERE content LIKE ?
        LIMIT 10
    """, (f'%{query}%',)).fetchall()
    
    print(f"Found {len(results)} results:")
    for i, (page_id, url, title, content) in enumerate(results, 1):
        # Find the context around the match
        content_lower = content.lower()
        pos = content_lower.find(query.lower())
        if pos > 0:
            start = max(0, pos - 50)
            end = min(len(content), pos + 50)
            snippet = content[start:end]
            print(f"\n{i}. {url}")
            print(f"   ...{snippet}...")

def interactive_menu(conn):
    """Interactive menu for exploring database"""
    while True:
        print("\n" + "="*60)
        print("🔧 PHOBOS DATABASE VIEWER")
        print("="*60)
        print("1. Show Statistics")
        print("2. Show Recent Pages")
        print("3. Show Random Page Content")
        print("4. Show Pages for Entity Extraction")
        print("5. Search Pages")
        print("6. Exit")
        print("="*60)
        
        choice = input("\nEnter choice (1-6): ").strip()
        
        if choice == '1':
            show_statistics(conn)
        elif choice == '2':
            limit = input("How many pages? (default 10): ").strip()
            limit = int(limit) if limit else 10
            show_recent_pages(conn, limit)
        elif choice == '3':
            show_page_content(conn)
        elif choice == '4':
            limit = input("How many samples? (default 5): ").strip()
            limit = int(limit) if limit else 5
            show_entities(conn, limit)
        elif choice == '5':
            query = input("Search for: ").strip()
            if query:
                show_search_example(conn, query)
        elif choice == '6':
            print("\n👋 Goodbye!")
            break
        else:
            print("Invalid choice!")

if __name__ == '__main__':
    conn = connect_db()
    if conn:
        try:
            interactive_menu(conn)
        finally:
            conn.close()
