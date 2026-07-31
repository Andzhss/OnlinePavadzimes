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
    Nolasa uzņēmuma nosaukumu, Reģ. Nr. un Adresi no Lursoft lapas.
    Atbalsta lv, ru, en valodu versijas.
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
        
        # 1. Nosaukums — vienmēr <h1>
        h1 = soup.find('h1')
        if h1:
            data['name'] = h1.get_text(strip=True)
        elif soup.title:
            data['name'] = soup.title.get_text(strip=True).split('-')[0].strip()

        # 2. Reģ. Nr. un Adrese — meklējam tabulas rindās (<tr>)
        #    Atbalstām visu trīs valodu apzīmējumus
        reg_label_patterns = [
            r'Reģistrācijas\s*numurs',   # LV
            r'Регистрационный\s*номер',   # RU
            r'Registration\s*number',     # EN
        ]
        addr_label_patterns = [
            r'Juridiskā\s*adrese',        # LV
            r'Юридический\s*адрес',        # RU
            r'Legal\s*address',           # EN
        ]

        all_rows = soup.find_all('tr')
        for row in all_rows:
            cells = row.find_all('td')
            if len(cells) < 2:
                continue
            label = cells[0].get_text(strip=True)
            value = cells[1].get_text(' ', strip=True)  # atdalām inline elementus ar atstarpi

            # --- Reģistrācijas numurs ---
            if 'reg_no' not in data:
                for pat in reg_label_patterns:
                    if re.search(pat, label, re.I):
                        match = re.search(r'(\d{11})', value)
                        if match:
                            data['reg_no'] = match.group(1)
                        break

            # --- Juridiskā adrese ---
            if 'address' not in data:
                for pat in addr_label_patterns:
                    if re.search(pat, label, re.I):
                        # Noņemam "Juridiskā adrese:" / "Юридический адрес:" sākumu, ja tas tur ir
                        addr = re.sub(
                            r'^(Juridiskā\s*adrese|Юридический\s*адрес|Legal\s*address)\s*:\s*',
                            '', value, flags=re.I
                        )
                        # Nogriežam visu, kas sākas ar "Iepriekšējās" / "Предыдущие" / "Previous" / "Adresē reģistrēti" utt.
                        addr = re.split(
                            r'(Iepriekšējās|Предыдущие|Previous|Adresē\s*reģistrēti|Зарегистрированы|Pasta\s*adrese|Почтовый\s*адрес|Postal\s*address)',
                            addr, flags=re.I
                        )[0]
                        addr = addr.strip().strip(',').strip()
                        if addr and len(addr) > 3:
                            data['address'] = addr
                        break

        return data if data.get('name') else None

    except Exception as e:
        print(f"Scraping error: {e}")
        return None
