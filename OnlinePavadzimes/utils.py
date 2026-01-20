from num2words import num2words
import requests
from bs4 import BeautifulSoup
import re

def money_to_words_lv(amount):
    """
    Converts amount to Latvian words string.
    Example: 4505.00 -> "Četri tūkstoši pieci simti pieci eiro 00 centi"
    """
    try:
        euros = int(amount)
        cents = int(round((amount - euros) * 100))
        
        words = num2words(euros, lang='lv')
        # num2words output is lowercase usually.
        # Format: "{words} eiro {cents:02d} centi"
        
        # Capitalize first letter
        words = words.capitalize()
        
        return f"{words} eiro {cents:02d} centi"
    except Exception as e:
        return f"Kļūda aprēķinā: {e}"

def scrape_lursoft(url):
    """
    Attempts to scrape Company Name, Reg No, and Address from a Lursoft URL.
    Returns a dict or None.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        data = {}
        
        # 1. Company Name
        # Often in <h1 itemprop="name"> or just <h1>
        h1 = soup.find('h1')
        if h1:
            data['name'] = h1.get_text(strip=True)
        else:
             # Fallback: Check title
            if soup.title:
                data['name'] = soup.title.get_text(strip=True).split('-')[0].strip()

        # 2. Reg No
        # Search for text "Reģistrācijas numurs"
        reg_label = soup.find(string=re.compile(r"Reģistrācijas numurs", re.I))
        if reg_label:
            parent = reg_label.parent
            # Check for value in next sibling td
            if parent.name == 'td':
                next_td = parent.find_next_sibling('td')
                if next_td:
                    data['reg_no'] = next_td.get_text(strip=True)
            elif parent.name in ['div', 'span', 'p', 'b', 'strong']:
                 # Try to extract numbers from the text if it's "Reģistrācijas numurs: 4000..."
                 full_text = parent.get_text(strip=True)
                 match = re.search(r"Reģistrācijas numurs\s*:?\s*(\d+)", full_text, re.I)
                 if match:
                     data['reg_no'] = match.group(1)
                 else:
                     # Check next sibling
                     next_el = parent.find_next_sibling()
                     if next_el:
                         data['reg_no'] = next_el.get_text(strip=True)

        # 3. Address
        addr_label = soup.find(string=re.compile(r"Juridiskā adrese|Adrese", re.I))
        if addr_label:
            parent = addr_label.parent
            if parent.name == 'td':
                next_td = parent.find_next_sibling('td')
                if next_td:
                    data['address'] = next_td.get_text(strip=True)
            else:
                 # Try to clean up text
                 next_el = parent.find_next_sibling()
                 if next_el:
                     data['address'] = next_el.get_text(strip=True)
                 else:
                     # Maybe in the same tag?
                     full_text = parent.get_text(strip=True)
                     # Try to split by colon
                     parts = full_text.split(':', 1)
                     if len(parts) > 1:
                         data['address'] = parts[1].strip()

        return data
    except Exception as e:
        print(f"Scraping error: {e}")
        return None
