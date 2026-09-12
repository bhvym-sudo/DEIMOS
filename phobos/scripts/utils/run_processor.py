import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from analysis.processor import NERProcessor
import time

def main():
    print("[PHOBOS-PROCESSOR] Starting NER and Threat Analysis...")
    
    processors = [
        NERProcessor('databases/crawler.db', 'crawler'),
        NERProcessor('databases/phobos_search.db', 'phobos-search'),
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
            if not did_work:
                print("[IDLE] Both engine databases are fully analyzed. Waiting for new data...")
                time.sleep(10)
                
        except KeyboardInterrupt:
            print("\n[STOP] Processor stopped by user")
            break
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(5)
    
    for processor in processors:
        processor.close()
    print("[PHOBOS-PROCESSOR] Shutdown complete")

if __name__ == "__main__":
    main()
