from num2words import num2words
import requests
from bs4 import BeautifulSoup
import re

def money_to_words_lv(amount):
    """
    Konvertē summu uz vārdiem latviešu valodā.
    Piemērs: 4505.00 -> "Četri tūkstoši pieci simti pieci eiro 00 centi"
    """
    try:
        euros = int(amount)
        cents = int(round((amount - euros) * 100))
        
        words = num2words(euros, lang='lv')
        
        # Pirmā burta lielais sākums
        words = words.capitalize()
        
        return f"{words} eiro {cents:02d} centi"
    except Exception as e:
        return f"Kļūda aprēķinā: {e}"

def scrape_lursoft(url):
    """
    Mēģina nolasīt Uzņēmuma nosaukumu, Reģ. Nr. un Adresi no Lursoft URL.
    Atgriež vārdnīcu (dict) vai None.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        data = {}
        
        # 1. Nosaukums (Company Name)
        h1 = soup.find('h1')
        if h1:
            data['name'] = h1.get_text(strip=True)
        else:
             # Fallback: Check title
            if soup.title:
                data['name'] = soup.title.get_text(strip=True).split('-')[0].strip()

        # 2. Reģistrācijas numurs (Reg No)
        # Meklējam tekstu "Reģistrācijas numurs"
        reg_label = soup.find(string=re.compile(r"Reģistrācijas numurs", re.I))
        
        if reg_label:
            parent = reg_label.parent
            reg_text_candidates = []
            
            # Pārbaudām nākamo elementu (ja tā ir tabulas šūna)
            next_td = parent.find_next_sibling('td')
            if next_td:
                reg_text_candidates.append(next_td.get_text(strip=True))
            
            # Pārbaudām nākamo elementu (ja tas ir vienkārši nākamais tags)
            next_el = parent.find_next_sibling()
            if next_el:
                reg_text_candidates.append(next_el.get_text(strip=True))
                
            # Pārbaudām arī pašu elementu (ja numurs ir vienā virknē ar nosaukumu)
            reg_text_candidates.append(parent.get_text(strip=True))
            
            # Meklējam precīzi 11 ciparus jebkurā no atrastajiem tekstiem
            for text in reg_text_candidates:
                # \d{11} nozīmē "tieši 11 cipari"
                match = re.search(r"(\d{11})", text)
                if match:
                    data['reg_no'] = match.group(1)
                    break

        # 3. Adrese (Address)
        addr_label = soup.find(string=re.compile(r"Juridiskā adrese|Adrese", re.I))
        if addr_label:
            parent = addr_label.parent
            raw_address = ""
            
            next_td = parent.find_next_sibling('td')
            if next_td:
                raw_address = next_td.get_text(strip=True)
            else:
                 next_el = parent.find_next_sibling()
                 if next_el:
                     raw_address = next_el.get_text(strip=True)
                 else:
                     # Ja ir vienā tagā, mēģinām atdalīt ar kolu
                     full_text = parent.get_text(strip=True)
                     parts = full_text.split(':', 1)
                     if len(parts) > 1:
                         raw_address = parts[1].strip()
                     else:
                         raw_address = full_text

            # Tīrīšana: noņemam "Juridiskā adrese" vai "Adrese" no teksta sākuma, ja tas tur palicis
            clean_address = re.sub(r"^(Juridiskā adrese|Adrese)\s*:?\s*", "", raw_address, flags=re.I)
            if clean_address:
                data['address'] = clean_address.strip()

        return data
    except Exception as e:
        print(f"Scraping error: {e}")
        return None
