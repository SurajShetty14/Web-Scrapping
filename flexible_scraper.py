import argparse
import json
import os
import re
import time
from datetime import datetime

import pandas as pd
import requests
import yaml
from bs4 import BeautifulSoup

# Selenium imports
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium import webdriver

try:
    from webdriver_manager.chrome import ChromeDriverManager
    _WEBDRIVER_MANAGER_AVAILABLE = True
except Exception:
    _WEBDRIVER_MANAGER_AVAILABLE = False


class FlexibleWebScraper:
    def __init__(self, config_file=None):
        self.config = self.load_config(config_file) if config_file else {}
        self.data = []
        self.driver = None
        self.session = None
        self.save_screenshots = False

    def load_config(self, config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                if config_file.endswith('.yaml') or config_file.endswith('.yml'):
                    return yaml.safe_load(f) or {}
                return json.load(f) or {}
        except Exception as e:
            print(f"Error loading config: {e}")
            return {}

    def setup_selenium(self, headless=False, save_screenshots=True, page_load_timeout=30):
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"]) 
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--start-maximized")

        if _WEBDRIVER_MANAGER_AVAILABLE:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
        else:
            self.driver = webdriver.Chrome(options=chrome_options)

        self.driver.set_page_load_timeout(page_load_timeout)
        self.save_screenshots = save_screenshots
        if self.save_screenshots:
            os.makedirs('screenshots', exist_ok=True)

    def setup_requests_session(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def scrape_with_multiple_methods(self, url, field_config, wait_css_selectors=None):
        extracted_data = {}

        # Method 1: Selenium
        try:
            if not self.driver:
                self.setup_selenium(headless=self.config.get('selenium', {}).get('headless', False),
                                    save_screenshots=self.config.get('selenium', {}).get('save_screenshots', True))

            self.driver.get(url)

            # Optional explicit waits for specific selectors
            if wait_css_selectors:
                for selector in wait_css_selectors:
                    try:
                        WebDriverWait(self.driver, self.config.get('selenium', {}).get('wait_seconds', 15)).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                    except Exception:
                        pass
            else:
                time.sleep(self.config.get('selenium', {}).get('sleep_after_load', 3))

            if self.save_screenshots:
                ts = int(time.time())
                self.driver.save_screenshot(f'screenshots/page_{ts}.png')

            if self.config.get('debug', {}).get('save_html', False):
                with open(f'debug_html_{int(time.time())}.html', 'w', encoding='utf-8') as f:
                    f.write(self.driver.page_source)

            extracted_data = self.extract_data_selenium(field_config)
            if self.is_extraction_successful(extracted_data):
                print("✓ Selenium method successful")
                return extracted_data
        except Exception as e:
            print(f"Selenium method failed: {e}")

        # Method 2: Requests + BS4
        try:
            if not self.session:
                self.setup_requests_session()
            response = self.session.get(url, timeout=30)
            if response.status_code == 200:
                extracted_data = self.extract_data_requests(response.text, field_config)
                if self.is_extraction_successful(extracted_data):
                    print("✓ Requests method successful")
                    return extracted_data
            else:
                print(f"Requests got status {response.status_code}")
        except Exception as e:
            print(f"Requests method failed: {e}")

        # Method 3: Custom API endpoint
        if 'api_endpoint' in self.config:
            try:
                api_data = self.try_api_extraction()
                if api_data:
                    print("✓ API method successful")
                    return api_data
            except Exception as e:
                print(f"API method failed: {e}")

        return extracted_data

    def try_api_extraction(self):
        if not self.session:
            self.setup_requests_session()
        api_cfg = self.config.get('api_endpoint', {})
        url = api_cfg.get('url')
        if not url:
            return {}
        method = api_cfg.get('method', 'GET').upper()
        headers = api_cfg.get('headers', {})
        params = api_cfg.get('params', {})
        body = api_cfg.get('body', {})
        resp = self.session.request(method, url, headers=headers, params=params, json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def extract_data_selenium(self, field_config):
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        return self.extract_with_config(soup, field_config, method="selenium")

    def extract_data_requests(self, html_content, field_config):
        soup = BeautifulSoup(html_content, 'html.parser')
        return self.extract_with_config(soup, field_config, method="requests")

    def extract_with_config(self, soup, field_config, method="selenium"):
        extracted_data = {}
        for field_name, field_info in field_config.items():
            value = None

            # Strategy 1: CSS Selectors
            for selector in field_info.get('css_selectors', []):
                try:
                    el = soup.select_one(selector)
                    if el:
                        value = el.get_text(strip=True)
                        if value:
                            break
                except Exception:
                    continue

            # Strategy 2: XPath via Selenium only
            if not value and method == "selenium":
                for xpath in field_info.get('xpath', []):
                    try:
                        el = self.driver.find_element(By.XPATH, xpath)
                        if el:
                            text_val = el.text.strip()
                            if text_val:
                                value = text_val
                                break
                    except Exception:
                        continue

            # Strategy 3: Text Pattern Matching
            if not value:
                text_content = soup.get_text("\n", strip=False)
                for pattern in field_info.get('text_patterns', []):
                    try:
                        match = re.search(pattern, text_content, re.IGNORECASE | re.DOTALL)
                        if match:
                            captured = match.group(1).strip()
                            if captured:
                                value = captured
                                break
                    except Exception:
                        continue

            # Strategy 4: Attribute Extraction
            if not value:
                for attr_cfg in field_info.get('attributes', []):
                    try:
                        el = soup.select_one(attr_cfg['selector'])
                        if el:
                            attr_val = el.get(attr_cfg['attribute'])
                            if attr_val:
                                value = attr_val
                                break
                    except Exception:
                        continue

            # Transformations
            if value and 'transform' in field_info:
                value = self.apply_transform(value, field_info['transform'])

            extracted_data[field_name] = value if value else "Not Found"

        return extracted_data

    def apply_transform(self, value, transform_config):
        ttype = transform_config.get('type')
        if ttype == 'regex':
            pattern = transform_config['pattern']
            replacement = transform_config.get('replacement', '')
            try:
                return re.sub(pattern, replacement, value)
            except Exception:
                return value
        if ttype == 'strip_chars':
            chars = transform_config.get('chars', None)
            return value.strip(chars) if chars is not None else value.strip()
        if ttype == 'convert_to_number':
            try:
                numeric = re.findall(r"[-+]?[0-9]*\.?[0-9]+", value)
                return float(numeric[0]) if numeric else value
            except Exception:
                return value
        return value

    def is_extraction_successful(self, data):
        if not data:
            return False
        total_fields = len(data)
        if total_fields == 0:
            return False
        found_fields = sum(1 for v in data.values() if v not in (None, "", "Not Found"))
        return (found_fields / total_fields) >= float(self.config.get('success_threshold', 0.5))

    def save_data(self, filename_base='scraped_data'):
        if not self.data:
            print("No data to save")
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        df = pd.DataFrame(self.data)

        excel_file = f"{filename_base}_{timestamp}.xlsx"
        csv_file = f"{filename_base}_{timestamp}.csv"
        json_file = f"{filename_base}_{timestamp}.json"

        try:
            df.to_excel(excel_file, index=False, engine='openpyxl')
            print(f"Saved Excel: {excel_file}")
        except Exception as e:
            print(f"Excel save failed: {e}")

        try:
            df.to_csv(csv_file, index=False, encoding='utf-8-sig')
            print(f"Saved CSV: {csv_file}")
        except Exception as e:
            print(f"CSV save failed: {e}")

        try:
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            print(f"Saved JSON: {json_file}")
        except Exception as e:
            print(f"JSON save failed: {e}")

    def add_new_fields_dynamically(self, new_field_config):
        if hasattr(self, 'field_config'):
            self.field_config.update(new_field_config)
        return new_field_config

    def bulk_scrape_urls(self, url_list, field_config):
        for i, url in enumerate(url_list):
            print(f"Scraping URL {i+1}/{len(url_list)}: {url}")
            try:
                data = self.scrape_with_multiple_methods(url, field_config,
                                                         wait_css_selectors=self.config.get('wait_css_selectors'))
                data['source_url'] = url
                data['scraped_at'] = datetime.now().isoformat()
                self.data.append(data)
                time.sleep(self.config.get('politeness_delay_seconds', 2))
            except Exception as e:
                print(f"Failed to scrape {url}: {e}")

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
        if self.session:
            try:
                self.session.close()
            except Exception:
                pass


def create_default_config():
    return {
        'success_threshold': 0.5,
        'politeness_delay_seconds': 2,
        'selenium': {
            'headless': False,
            'save_screenshots': True,
            'sleep_after_load': 3,
            'wait_seconds': 15
        },
        'debug': {
            'save_html': False
        }
    }


def create_sample_field_config():
    return {
        'Assessment Name': {
            'css_selectors': ['.assessment-name', '[data-testid*="assessment"]', 'h1', 'h2'],
            'text_patterns': [r'Assessment Name[:\s]*([^\n]+)', r'Assessment[:\s]*([^\n]+)', r'Test Name[:\s]*([^\n]+)']
        },
        'Candidate Name': {
            'css_selectors': ['.candidate-name', '[data-testid*="candidate"]', '[data-testid*="name"]'],
            'xpath': ['//*[contains(text(), "Candidate Name")]/following::*[1]'],
            'text_patterns': [r'Candidate Name[:\s]*([^\n]+)', r'Candidate[:\s]*([^\n]+)']
        },
        'Email': {
            'css_selectors': ['[href^="mailto:"]', '.email', '[data-testid*="email"]'],
            'text_patterns': [r'E-mail[:\s]*([^\n]+)', r'Email[:\s]*([^\n]+)'],
            'attributes': [{'selector': '[href^="mailto:"]', 'attribute': 'href'}],
            'transform': {'type': 'regex', 'pattern': r'mailto:', 'replacement': ''}
        },
        'Total Assessment Time': {
            'css_selectors': ['.assessment-time', '[data-testid*="time"]'],
            'text_patterns': [r'Total Assessment Time[:\s]*([^\n]+)', r'Assessment Time[:\s]*([^\n]+)']
        },
        'Score Percentage': {
            'css_selectors': ['.score-percentage', '[data-testid*="score"]'],
            'text_patterns': [r'Score Percentage[:\s]*([^\n]+)', r'Score[:\s]*([^\n]+)'],
            'transform': {'type': 'convert_to_number'}
        },
        'Trust Score': {
            'css_selectors': ['.trust-score', '[data-testid*="trust"]'],
            'text_patterns': [r'Trust Score[:\s]*([^\n]+)'],
            'transform': {'type': 'convert_to_number'}
        },
        'Tab Switched': {
            'text_patterns': [r'Tab Switched[-:\s]*([0-9]+)'],
            'transform': {'type': 'convert_to_number'}
        },
        'Out of Frame': {
            'text_patterns': [r'Out of Frame[-:\s]*([0-9]+)'],
            'transform': {'type': 'convert_to_number'}
        },
        'Clicked Outside Window': {
            'text_patterns': [r'Clicked Outside Window[-:\s]*([0-9]+)'],
            'transform': {'type': 'convert_to_number'}
        },
        'Multiple Faces Detected': {
            'text_patterns': [r'Multiple Faces Detected[-:\s]*([0-9]+)'],
            'transform': {'type': 'convert_to_number'}
        },
        'External Monitor Detected': {
            'text_patterns': [r'External Monitor Detected[-:\s]*([A-Za-z])']
        },
        'Fullscreen Exited': {
            'text_patterns': [r'Fullscreen Exited[-:\s]*([A-Za-z])']
        },
        'Extension Detected': {
            'text_patterns': [r'Extension Detected[-:\s]*([A-Za-z])']
        },
        'IP Mismatch': {
            'text_patterns': [r'IP Mismatch[-:\s]*([0-9]+)'],
            'transform': {'type': 'convert_to_number'}
        },
        'Strong Points': {
            'text_patterns': [r'Strong Points[-:\s]*([\s\S]*?)(?:Areas Of Improvement|Overall Feedback|$)']
        },
        'Areas Of Improvement': {
            'text_patterns': [r'Areas Of Improvement[-:\s]*([\s\S]*?)(?:Strong Points|Overall Feedback|$)']
        },
        'Overall Feedback': {
            'text_patterns': [r'Overall Feedback[-:\s]*([\s\S]*?)$']
        }
    }


def parse_args():
    parser = argparse.ArgumentParser(description='Flexible web scraper for AccioMatrix and similar pages')
    parser.add_argument('-c', '--config', help='Path to YAML/JSON runtime config', default=None)
    parser.add_argument('-f', '--fields', help='Path to YAML/JSON field config. If omitted, uses sample fields.', default=None)
    parser.add_argument('-u', '--url', help='Single URL to scrape', default=None)
    parser.add_argument('-U', '--url-file', help='Text file with one URL per line', default=None)
    parser.add_argument('-o', '--out', help='Output filename base (without extension)', default='assessment_reports')
    return parser.parse_args()


def load_field_config(path):
    if not path:
        return create_sample_field_config()
    with open(path, 'r', encoding='utf-8') as f:
        if path.endswith('.yaml') or path.endswith('.yml'):
            return yaml.safe_load(f)
        return json.load(f)


def main():
    args = parse_args()
    scraper = FlexibleWebScraper(config_file=args.config)

    default_cfg = create_default_config()
    scraper.config = {**default_cfg, **(scraper.config or {})}

    field_config = load_field_config(args.fields)

    urls = []
    if args.url:
        urls.append(args.url.strip())
    if args.url_file and os.path.exists(args.url_file):
        with open(args.url_file, 'r', encoding='utf-8') as f:
            urls.extend([line.strip() for line in f if line.strip()])

    if not urls:
        print("Provide a --url or --url-file with at least one URL.")
        return

    scraper.bulk_scrape_urls(urls, field_config)
    scraper.save_data(args.out)
    scraper.close()


if __name__ == "__main__":
    main()


