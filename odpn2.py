from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import requests
import time
import json
import csv
from urllib.parse import urlparse
from pathlib import Path
from typing import Dict, List, Optional

class SiteWrap:
    def __init__(self, host: str, rozdzial_szkola: int = 0, options: tuple = ()):
        self.host = host
        self.szkola_rozdzial = rozdzial_szkola
        
        # Nowoczesna konfiguracja Chrome z CDP
        chrome_options = Options()
        chrome_options.add_experimental_option('detach', True)
        chrome_options.add_argument('--enable-logging')
        chrome_options.add_argument('--log-level=0')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        
        # Włączenie logowania performance dla przechwytywania requestów
        chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        
        # Dodanie dodatkowych opcji
        for option in options:
            chrome_options.add_argument(f"--{option}")
        
        # Użycie Selenium Manager (automatycznie zarządza sterownikami)
        service = Service()
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Włączenie Network domain w CDP
        self.driver.execute_cdp_cmd("Network.enable", {})
        self.driver.execute_cdp_cmd("Page.enable", {})
        
        # Przechowywanie przechwyconych requestów
        self.captured_requests = []
        self.cookies = {}
        
        # Inicjalizacja połączenia
        self._initialize_connection()
        self.wait_time = 20

    def _initialize_connection(self):
        """Inicjalizacja połączenia z retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self.driver.get(f"https://{self.host}")
                WebDriverWait(self.driver, 10).until(
                    lambda driver: driver.execute_script("return document.readyState") == "complete"
                )
                self.host = urlparse(self.driver.current_url).netloc.split(':')[0]
                print(f"Połączono z: {self.host}")
                break
            except Exception as e:
                print(f'Próba {attempt + 1}/{max_retries} nieudana: {e}')
                if attempt == max_retries - 1:
                    raise
                time.sleep(2)

    def capture_response(self, file_name: str = "zrzut"):
        """Przechwytywanie odpowiedzi używając performance logs zamiast selenium-wire"""
        try:
            # Pobranie logów performance z Chrome
            logs = self.driver.get_log("performance")
            captured_data = []
            
            for log_entry in logs:
                try:
                    message = log_entry.get('message')
                    if not message:
                        continue
                    
                    # Parsowanie wiadomości JSON
                    log_data = json.loads(message)
                    log_message = log_data.get('message', {})
                    
                    # Sprawdzenie czy to żądanie POST do GridGetData
                    if (log_message.get('method') == 'Network.requestWillBeSent' and 
                        'GridGetData' in log_message.get('params', {}).get('request', {}).get('url', '')):
                        
                        request_data = log_message['params']['request']
                        
                        # Sprawdzenie czy to żądanie POST z danymi
                        if (request_data.get('method') == 'POST' and 
                            request_data.get('postData')):
                            
                            try:
                                # Parsowanie danych POST
                                post_data = json.loads(request_data['postData'])
                                
                                if 'data' in post_data:
                                    self._extract_ids(post_data['data'])
                                    self._extract_field_names(post_data['data'].get('v_store_fields', []))
                                    
                                    captured_data.append({
                                        'url': request_data['url'],
                                        'method': request_data['method'],
                                        'headers': request_data.get('headers', {}),
                                        'postData': post_data,
                                        'timestamp': log_entry.get('timestamp')
                                    })
                                    
                                    print("Przechwycono dane:")
                                    print(f"Pola: {self.fields_name}")
                                    print(f"IDs: szkid={self.ID_szkid}, rok={self.ID_rok}, "
                                          f"miesiac={self.ID_miesiac}, rozdzial={self.ID_rozdzial}, "
                                          f"dokument={self.ID_Dokumentu}, wydruk={self.IDWydruk}")
                                    break
                                    
                            except json.JSONDecodeError as e:
                                print(f"Błąd parsowania JSON postData: {e}")
                                continue
                                
                except (json.JSONDecodeError, KeyError) as e:
                    continue
            
            # Zapis do pliku JSON
            output_file = Path(f"{file_name}.json")
            with output_file.open("w", encoding='utf-8') as f:
                json.dump(captured_data, f, indent=2, ensure_ascii=False)
                
            print(f"Zapisano {len(captured_data)} przechwyconych żądań do {output_file}")
            
        except Exception as e:
            print(f"Błąd podczas przechwytywania: {e}")

    def _extract_ids(self, data: dict):
        """Wyodrębnij ID z danych"""
        self.ID_szkid = data.get('szkid')
        self.ID_rok = data.get('rok')
        self.ID_miesiac = data.get('miesiac')
        self.ID_rozdzial = data.get('rozdzial')
        self.ID_Dokumentu = data.get('IdDokumentu')
        self.IDWydruk = data.get('wydrukId')

    def _extract_field_names(self, v_store_fields: list):
        """Wyodrębnij nazwy pól"""
        self.fields_name = [
            field['name'] for field in v_store_fields 
            if field.get('allowBlank') is False
        ]

    def login(self, loginwd: str = "", passwd: str = ""):
        """Login do systemu"""
        try:
            # Oczekiwanie na pole loginu
            lname = WebDriverWait(self.driver, self.wait_time).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[name=Login]"))
            )
            
            if loginwd:
                lname.clear()
                lname.send_keys(loginwd)
            
            # Znalezienie pola hasła
            lpass = self.driver.find_element(By.ID, "Haslo")
            if passwd:
                lpass.clear()
                lpass.send_keys(passwd)
            
            # Automatyczne logowanie jeśli podano dane
            if loginwd and passwd:
                login_button = self.driver.find_element(By.ID, "ButtonLogowanie")
                login_button.click()
                
                # Oczekiwanie na załadowanie menu
                WebDriverWait(self.driver, self.wait_time).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#ext-gen43"))
                )
                print("Zalogowano pomyślnie")
            else:
                # Oczekiwanie na ręczne logowanie
                print("Oczekiwanie na ręczne logowanie...")
                WebDriverWait(self.driver, float('inf')).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#ext-gen43"))
                )
                print("Zalogowano ręcznie")
                
        except Exception as e:
            print(f"Błąd podczas logowania: {e}")
            raise

    def get_headers(self):
        """Pobranie cookies z przeglądarki zamiast z selenium-wire"""
        try:
            # Pobranie cookies bezpośrednio z przeglądarki
            browser_cookies = self.driver.get_cookies()
            self.cookies = {cookie['name']: cookie['value'] for cookie in browser_cookies}
            
            # Dodatkowo, możemy pobrać cookies z performance logs
            logs = self.driver.get_log("performance")
            for log_entry in logs:
                try:
                    message = json.loads(log_entry.get('message', '{}'))
                    log_message = message.get('message', {})
                    
                    if log_message.get('method') == 'Network.requestWillBeSent':
                        headers = log_message.get('params', {}).get('request', {}).get('headers', {})
                        cookie_header = headers.get('Cookie')
                        
                        if cookie_header:
                            # Parsowanie cookie header
                            for cookie_pair in cookie_header.split('; '):
                                if '=' in cookie_pair:
                                    key, value = cookie_pair.split('=', 1)
                                    self.cookies[key] = value
                            break
                            
                except (json.JSONDecodeError, KeyError):
                    continue
            
            print(f"Pobrano {len(self.cookies)} cookies")
            
        except Exception as e:
            print(f"Błąd podczas pobierania headers: {e}")

    def select_bills(self):
        """Nawigacja do formularza rozliczenia"""
        try:
            # Kliknięcie głównego menu
            menu_exe = WebDriverWait(self.driver, self.wait_time).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#ext-gen43"))
            )
            menu_exe.click()
            
            # Wybór rozdziału jeśli określony
            if self.szkola_rozdzial != 0:
                rozdzial_selector = f"#ext-gen90-gp-Rozdzial-{self.szkola_rozdzial}-bd"
                rozdzial_element = WebDriverWait(self.driver, self.wait_time).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, rozdzial_selector))
                )
                pencil_icon = rozdzial_element.find_element(By.CLASS_NAME, "pencil")
                pencil_icon.click()
            
            # Wybór dokumentu
            wait_time = self.wait_time if self.szkola_rozdzial != 0 else float('inf')
            document_element = WebDriverWait(self.driver, wait_time).until(
                EC.element_to_be_clickable((By.XPATH, "//li[.//span[contains(@class, 'x-tab-strip-text') and normalize-space(text())='Wydatki']]"))
            )
            document_element.click()
            
            # Kliknięcie przycisku dodawania
            add_button = WebDriverWait(self.driver, self.wait_time).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".add"))
            )
            add_button.click()
            
            print("Nawigacja do formularza zakończona pomyślnie")
            
        except Exception as e:
            print(f"Błąd podczas nawigacji: {e}")
            raise

    def parse_file(self, name: Optional[str] = None, encoding: str = "utf-8"):
        """Parsowanie pliku CSV z wydatkami"""
        url = f'https://{self.host}/ODPN/Szkoly/RozliczenieDotacji/Kontrolki/Taby/Dokument/Dokument.asmx/SubmitForm'
        file_name = name or f"wydatki_{self.ID_rozdzial}.csv"
        
        numery_pol = {
            '1.': (1, -1), '2.': (2, -2), '3.1.': (4, -3),
            '3.2.': (5, -4), '3.3.': (6, -5), '3.4.': (7, -6), '3.5.': (8, -7)
        }
        
        niepowodzenia = []
        file_path = Path(file_name)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Plik {file_name} nie istnieje")
        
        print(f"Przetwarzanie pliku: {file_path}")
        
        with file_path.open('r', encoding=encoding) as plik_dane:
            csv_reader = csv.reader(plik_dane, delimiter=';')
            
            for row_num, dane in enumerate(csv_reader, 1):
                try:
                    if len(dane) < 8:
                        niepowodzenia.append((row_num, "Za mało kolumn w wierszu"))
                        continue
                    
                    # Przetwarzanie danych z wiersza
                    dane_post = self._process_row_data(dane, numery_pol, row_num)
                    if dane_post is None:
                        niepowodzenia.append((row_num, f"Nieznany rodzaj wydatku: {dane[1]}"))
                        continue
                    
                    # Wysłanie żądania
                    print(f"Wysyłam żądanie dla wiersza {row_num}... ", end='')
                    success = self._send_request(url, dane_post)
                    
                    if success:
                        print("✓ Sukces")
                    else:
                        print("✗ Błąd")
                        niepowodzenia.append((row_num, "Błąd wysyłania żądania"))
                    
                    time.sleep(1)  # Rate limiting
                    
                except Exception as e:
                    print(f"✗ Błąd: {e}")
                    niepowodzenia.append((row_num, f"Błąd przetwarzania: {str(e)}"))
        
        self._report_errors(niepowodzenia)
        self._finalize_form()

    def _process_row_data(self, dane: List[str], numery_pol: Dict, row_num: int) -> Optional[Dict]:
        """Przetworzenie danych z wiersza CSV"""
        try:
            poz_z_tabeli = dane[1].strip()
            
            if poz_z_tabeli not in numery_pol:
                return None
            
            nr_pozycji = numery_pol[poz_z_tabeli]
            
            # Walidacja i konwersja danych
            pelna_kwota = self._parse_amount(dane[3])
            kwota_dotacji = self._parse_amount(dane[7])
            kwota_orzeczenia = self._parse_amount(dane[8])
            
            dane_post = {
                "Id": str(nr_pozycji[1]),
                "ID_szkid": self.ID_szkid,
                "ID_rok": self.ID_rok,
                "ID_miesiac": self.ID_miesiac,
                "ID_rozdzial": self.ID_rozdzial,
                "NumerPola": str(nr_pozycji[0]),
                "ID_Dokumentu": self.ID_Dokumentu,
                "ID_Wydruk": self.IDWydruk,
            }
            
            # Dodanie danych do pól według kolejności
            if len(self.fields_name) >= 7:
                dane_post[self.fields_name[0]] = dane[2].strip()  # rodzaj_i_nr_dowodu
                dane_post[self.fields_name[1]] = pelna_kwota       # pelna_kwota_zobowiazania
                dane_post[self.fields_name[2]] = f"{dane[4].strip()}T00:00:00"  # data_wystawienia
                dane_post[self.fields_name[3]] = dane[5].strip()   # przedmiot_zakupu
                dane_post[self.fields_name[4]] = f"{dane[6].strip()}T00:00:00"  # data_platnosci
                dane_post[self.fields_name[5]] = kwota_dotacji     # kwota_z_dotacji
                dane_post[self.fields_name[6]] = kwota_orzeczenia  # kwota_orzeczenia
            
            return dane_post
            
        except (IndexError, ValueError) as e:
            raise ValueError(f"Błąd przetwarzania danych w wierszu {row_num}: {e}")

    def _parse_amount(self, amount_str: str) -> float:
        """Bezpieczne parsowanie kwot"""
        cleaned = amount_str.replace(',', '.').replace(' ', '').strip()
        return round(float(cleaned), 2)

    def _send_request(self, url: str, data: Dict) -> bool:
        """Wysłanie żądania POST"""
        try:
            response = requests.post(
                url=url,
                json={"data": data},
                cookies=self.cookies,
                timeout=30,
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
            response.raise_for_status()
            return True
            
        except requests.RequestException as e:
            print(f"Błąd żądania: {e}")
            return False

    def _report_errors(self, niepowodzenia: List):
        """Raportowanie błędów"""
        if niepowodzenia:
            print(f"\nLista błędów ({len(niepowodzenia)}):")
            for row_num, error in niepowodzenia:
                print(f"Wiersz {row_num}: {error}")
        else:
            print("\nWszystkie wiersze przetworzone pomyślnie!")

    def _finalize_form(self):
        """Finalizacja formularza"""
        try:
            # Ukrycie maski
            mask_elements = self.driver.find_elements(By.CLASS_NAME, "ext-el-mask")
            for mask in mask_elements:
                self.driver.execute_script("arguments[0].style.display = 'none';", mask)
            
            # Kliknięcie linku powrotu
            return_element = WebDriverWait(self.driver, self.wait_time).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#ext-gen61"))
            )
            
            link_element = return_element.find_element(By.CLASS_NAME, "vlibrary-topLink")
            link_element.click()
            
            print("Formularz sfinalizowany pomyślnie")
            
        except Exception as e:
            print(f"Błąd podczas finalizacji: {e}")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if hasattr(self, 'driver'):
            self.driver.quit()
            print("Przeglądarka zamknięta")

# Użycie
if __name__ == "__main__":
    # Przykład użycia z context managerem
    with SiteWrap("czestochowa.odpn.pl") as site:
        site.login("", "")  # Podaj login i hasło lub zostaw puste dla ręcznego logowania
        site.get_headers()
        site.select_bills()
        site.capture_response("all")
        site.parse_file()
    
    # Lub tradycyjne użycie
    # site = SiteWrap("czestochowa.odpn.pl")
    # try:
    #     site.login("", "")
    #     site.get_headers()
    #     site.select_bills()
    #     site.capture_response("all")
    #     site.parse_file()
    # finally:
    #     site.driver.quit()
