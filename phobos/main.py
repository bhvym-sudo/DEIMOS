from scripts.crawler import start_simple_crawler
from scripts.parser import HTMLParser
from scripts.analyzer import IntelligenceAnalyzer
from scripts.storage import DataStorage


def main():
    
    seed_urls = [
        'https://news.ycombinator.com'
    ]
    
    print("=" * 70)
    print("PHOBOS - Simple Intelligence Gathering Crawler")
    print("=" * 70)
    
    print("\nInitializing modules...")
    
    parser = HTMLParser()
    print("HTML Parser initialized")
    
    analyzer = IntelligenceAnalyzer()
    print("Intelligence Analyzer initialized")
    
    storage = DataStorage(reports_dir='reports')
    print("Data Storage initialized")
    
    print(f"\nCrawl Configuration:")
    print(f"  - Depth Limit: 2 levels")
    print(f"  - Concurrent Requests: 8")
    print(f"  - Download Delay: 1 second")
    
    print(f"\nSeed URLs ({len(seed_urls)}):")
    for i, url in enumerate(seed_urls, 1):
        print(f"  {i}. {url}")
    
    print("\n" + "=" * 70)
    print("Starting crawler...")
    print("=" * 70 + "\n")
    
    try:
        start_simple_crawler(
            seed_urls=seed_urls,
            analyzer=analyzer,
            parser=parser,
            storage=storage
        )
        
        print("\n" + "=" * 70)
        print("Crawling completed!")
        print("=" * 70)
        
        print("\nGenerating overall report...")
        overall_report = storage.generate_overall_report()
        
        if overall_report.get('total_pages_analyzed', 0) > 0:
            overall_path = storage.save_data(overall_report, 'overall_report.json')
            print(f"✓ Overall report saved: {overall_path}")
            
            metadata = overall_report['report_metadata']
            threat_stats = overall_report['threat_analysis']['statistics']
            categorization = overall_report['threat_analysis']['categorization']
            entity_summary = overall_report['entity_analysis']['summary']
            
            print(f"\n{'=' * 70}")
            print("CRAWL SUMMARY")
            print(f"{'=' * 70}")
            
            print(f"\nPages Analyzed: {metadata['total_pages_analyzed']}")
            
            print(f"\nThreat Statistics:")
            print(f"  Average Score: \033[96m{threat_stats['average_threat_score']}\033[0m")
            print(f"  Max Score:     \033[96m{threat_stats['max_threat_score']}\033[0m")
            print(f"  Min Score:     \033[96m{threat_stats['min_threat_score']}\033[0m")
            
            print(f"\nThreat Distribution:")
            print(f"  High (≥0.5):     {categorization['high_threat_count']} pages")
            print(f"  Medium (0.3-0.5): {categorization['medium_threat_count']} pages")
            print(f"  Low (<0.3):      {categorization['low_threat_count']} pages")
            
            print(f"\nEntities Discovered:")
            print(f"  Persons:       {entity_summary['persons']}")
            print(f"  Organizations: {entity_summary['organizations']}")
            print(f"  Locations:     {entity_summary['locations']}")
            print(f"  Keywords:      {entity_summary['keywords']}")
            
            if categorization['high_threat_count'] > 0:
                print(f"\n{'-' * 70}")
                print("HIGH THREAT PAGES:")
                print(f"{'-' * 70}")
                for i, threat in enumerate(overall_report['threat_analysis']['high_threats'][:5], 1):
                    print(f"\n{i}. {threat['url']}")
                    print(f"   Score: \033[96m{threat['threat_score']}\033[0m")
                    if threat['keywords']:
                        print(f"   Keywords: {', '.join(threat['keywords'])}")
            
            print(f"\n{'=' * 70}")
        else:
            print("\nNo pages were analyzed.")
        
    except KeyboardInterrupt:
        print("\n\nCrawler stopped by user.")
    except Exception as e:
        print(f"\n\nError: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
