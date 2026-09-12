import sqlite3

conn = sqlite3.connect('databases/phobos_analysis.db')
cursor = conn.cursor()

print("NER Results:")
cursor.execute('SELECT page_id, url FROM ner_results LIMIT 3')
for row in cursor.fetchall():
    print(f'  Page ID: {row[0]}, URL: {row[1][:80]}')

print("\nThreat Analysis:")
cursor.execute('SELECT COUNT(*) FROM threat_analysis')
print(f'  Total records: {cursor.fetchone()[0]}')

conn.close()
