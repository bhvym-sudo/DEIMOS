import sqlite3

def migrate_database():
    conn = sqlite3.connect('databases/phobos_analysis.db')
    cursor = conn.cursor()
    
    columns_to_add = [
        ("leak_detected", "BOOLEAN DEFAULT 0"),
        ("leak_type", "TEXT"),
        ("origin_country", "TEXT"),
        ("risk_classification", "TEXT"),
        ("data_categories", "TEXT"),
        ("pii_types", "TEXT"),
        ("sensitive_level", "TEXT"),
        ("leak_indicators", "TEXT"),
        ("threat_to_india", "BOOLEAN DEFAULT 0"),
    ]
    
    for column_name, column_type in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE threat_analysis ADD COLUMN {column_name} {column_type}")
            print(f"Added column: {column_name}")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print(f"Column {column_name} already exists, skipping")
            else:
                print(f"Error adding {column_name}: {e}")
    
    conn.commit()
    conn.close()
    print("Migration complete")

if __name__ == "__main__":
    migrate_database()
