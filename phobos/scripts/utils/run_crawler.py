"""
Subprocess script to run the crawler independently.
This allows the Scrapy reactor to run in its own main thread.
"""
import sys
import json
import os

def main():
    config_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config_files', 'crawler_config.json')
    
    if not os.path.exists(config_file):
        print("[ERROR] Configuration file not found")
        sys.exit(1)
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    # Import crawler modules
    from scripts.crawler import start_simple_crawler
    from scripts.parser import HTMLParser
    from scripts.analyzer import IntelligenceAnalyzer
    from scripts.storage import DataStorage
    
    print("[INIT] Initializing crawler modules...")
    
    # Initialize modules
    parser = HTMLParser()
    print("[OK] HTML Parser initialized")
    
    analyzer = IntelligenceAnalyzer()
    print("[OK] Intelligence Analyzer initialized")
    
    storage = DataStorage(reports_dir='reports')
    print("[OK] Data Storage initialized")
    
    seed_urls = config.get('seed_urls', [])
    use_tor = config.get('use_tor', False)
    
    print(f"[INFO] Starting crawl with {len(seed_urls)} seed URL(s)")
    if use_tor:
        print("[INFO] Tor mode ENABLED - Dark Web crawling")
    else:
        print("[INFO] Tor mode DISABLED - Surface Web crawling")
    
    # Start crawler
    try:
        start_simple_crawler(
            seed_urls=seed_urls,
            analyzer=analyzer,
            parser=parser,
            storage=storage,
            use_tor=use_tor
        )
        
        print("[COMPLETE] Crawling finished successfully")
        
        # Generate overall report
        overall_report = storage.generate_overall_report()
        
        if overall_report.get('total_pages_analyzed', 0) > 0:
            metadata = overall_report['report_metadata']
            threat_stats = overall_report['threat_analysis']['statistics']
            categorization = overall_report['threat_analysis']['categorization']
            
            print("[REPORT] Generating final statistics...")
            print(f"[STATS] Pages Analyzed: {metadata['total_pages_analyzed']}")
            print(f"[STATS] Average Threat Score: \033[96m{threat_stats['average_threat_score']}\033[0m")
            print(f"[STATS] High Threats: {categorization['high_threat_count']}")
            print(f"[STATS] Medium Threats: {categorization['medium_threat_count']}")
            print(f"[STATS] Low Threats: {categorization['low_threat_count']}")
            
            overall_path = storage.save_data(overall_report, 'overall_report.json')
            print(f"[SAVE] Report saved to: {overall_path}")
        
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        import traceback
        print(f"[TRACE] {traceback.format_exc()}")
        sys.exit(1)

if __name__ == '__main__':
    main()
