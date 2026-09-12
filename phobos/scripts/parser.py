from bs4 import BeautifulSoup
import re


class HTMLParser:
    
    def __init__(self):
        pass
    
    def extract_text(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        
        for script in soup(['script', 'style', 'meta', 'noscript', 'iframe']):
            script.decompose()
        
        text = soup.get_text(separator=' ', strip=True)
        
        text = re.sub(r'\s+', ' ', text)
        
        text = text.strip()
        
        return text
    
    def extract_metadata(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        
        metadata = {}
        
        title_tag = soup.find('title')
        metadata['title'] = title_tag.get_text(strip=True) if title_tag else ''
        
        meta_description = soup.find('meta', attrs={'name': 'description'})
        metadata['description'] = meta_description.get('content', '') if meta_description else ''
        
        return metadata
