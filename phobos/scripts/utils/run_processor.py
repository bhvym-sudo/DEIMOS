import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from analysis.processor import NERProcessor
from scripts.profile_analyzer import ProfileAnalyzer
import time

def main():
    print("[PHOBOS-PROCESSOR] Starting NER and Threat Analysis...")
    
    profile_analyzer = ProfileAnalyzer('databases/profiles.db')
    processors = [
        NERProcessor('databases/crawler.db', 'crawler', profile_analyzer),
        NERProcessor('databases/phobos_search.db', 'phobos-search', profile_analyzer),
        NERProcessor('databases/workspace.db', 'workspace-crawler', profile_analyzer),
    ]
    
    while True:
        try:
            did_work = False
            for processor in processors:
                stats = processor.get_statistics()
                print(f"[{processor.engine.upper()}] pages={stats['total_pages_in_go']} analyzed={stats['ner_processed']} pending={stats['pending']} threats={stats['threats_found']}")
                if stats['pending'] > 0:
                    did_work = True
                    print(f"[PROCESS] {processor.engine}: processing {min(100, stats['pending'])} pages...")
                    processor.process_batch(limit=100, save_json_threshold=0.4)
                scanned, profiles = profile_analyzer.process_database(processor.engine, processor.database_path)
                if scanned:
                    did_work = True
                    print(f"[PROFILE-SCAN] {processor.engine}: scanned={scanned} profiles={profiles}")
            if not did_work:
                print("[IDLE] All engine databases are fully analyzed. Waiting for new data...")
                time.sleep(10)
                
        except KeyboardInterrupt:
            print("\n[STOP] Processor stopped by user")
            break
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(5)
    
    for processor in processors:
        processor.close()
    profile_analyzer.close()
    print("[PHOBOS-PROCESSOR] Shutdown complete")

if __name__ == "__main__":
    main()
