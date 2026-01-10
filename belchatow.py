from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException
import requests
import time
import json
import csv
from urllib.parse import urlparse
from pathlib import Path
from typing import Dict, List, Optional
import re

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
        
        for option in options:
            chrome_options.add_argument(f"--{option}")
        
        service = Service()
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        
        self.driver.execute_cdp_cmd("Network.enable", {})
        self.driver.execute_cdp_cmd("Page.enable", {})
        
        self.captured_requests = []
        self.cookies = {}
        
        self.wait_time = 20
        # Mapowanie miesięcy
        self.miesiace_map = {
            '01': 'Styczeń', '02': 'Luty', '03': 'Marzec', '04': 'Kwiecień',
            '05': 'Maj', '06': 'Czerwiec', '07': 'Lipiec', '08': 'Sierpień',
            '09': 'Wrzesień', '10': 'Październik', '11': 'Listopad', '12': 'Grudzień'
        }

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
        """Przechwytywanie odpowiedzi używając performance logs"""
        try:
            logs = self.driver.get_log("performance")
            captured_data = []

            REQUIRED_FIELDS = {'szkid', 'rok', 'miesiac', 'rozdzial', 'IdDokumentu', 'wydrukId'}
            
            for log_entry in logs:
                try:
                    message = log_entry.get('message')
                    if not message:
                        continue
                    
                    log_data = json.loads(message)
                    log_message = log_data.get('message', {})
                    
                    if (log_message.get('method') == 'Network.requestWillBeSent' and 
                        'GridGetData' in log_message.get('params', {}).get('request', {}).get('url', '')):
                        
                        request_data = log_message['params']['request']
                        
                        if (request_data.get('method') == 'POST' and 
                            request_data.get('postData')):
                            
                            try:
                                post_data = json.loads(request_data['postData'])

                                continueSearch = False
                                for field in REQUIRED_FIELDS:
                                    if post_data['data'].get(field) is None:
                                        continueSearch = True
                                        break

                                if continueSearch:
                                    continue
                                
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
                                
                except (json.JSONDecodeError, KeyError):
                    continue
            
            output_file = Path(f"{file_name}.json")
            with output_file.open("w", encoding='utf-8') as f:
                json.dump(captured_data, f, indent=2, ensure_ascii=False)
                
            print(f"Zapisano {len(captured_data)} przechwyconych żądań do {output_file}")
            
        except Exception as e:
            print(f"Błąd podczas przechwytywania: {e}")

    def _extract_ids(self, data: dict):
        self.ID_szkid = data.get('szkid')
        self.ID_rok = data.get('rok')
        self.ID_miesiac = data.get('miesiac')
        self.ID_rozdzial = data.get('rozdzial')
        self.ID_Dokumentu = data.get('IdDokumentu')
        self.IDWydruk = data.get('wydrukId')

    def _extract_field_names(self, v_store_fields: list):
        self.fields_name = [
            field['name'] for field in v_store_fields 
            if field.get('allowBlank') is False
        ]

    def login(self, loginwd: str = "", passwd: str = ""):
        """Login do systemu"""
        try:
            lname = WebDriverWait(self.driver, self.wait_time).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[name=Login]"))
            )
            
            if loginwd:
                lname.clear()
                lname.send_keys(loginwd)
            
            lpass = self.driver.find_element(By.ID, "Haslo")
            if passwd:
                lpass.clear()
                lpass.send_keys(passwd)
            
            if loginwd and passwd:
                login_button = self.driver.find_element(By.ID, "ButtonLogowanie")
                login_button.click()
                
                WebDriverWait(self.driver, self.wait_time).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#ext-gen43"))
                )
                print("Zalogowano pomyślnie")
            else:
                print("Oczekiwanie na ręczne logowanie...")
                WebDriverWait(self.driver, float('inf')).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#ext-gen43"))
                )
                print("Zalogowano ręcznie")
                
        except Exception as e:
            print(f"Błąd podczas logowania: {e}")
            raise

    def select_school(self, szk_id: int):
        """Zmiana placówki przez POST request"""
        print('Zmieniam placówkę...')
        try:
            url = f"https://{self.host}/Common/ZmianaPlacowki/ZmianaPlacowki_Resp.aspx"
            payload = {
                'task': 'ZmianaPlacowki',
                'szk_id': szk_id
            }
            response = requests.post(
                url=url,
                data=payload,
                cookies=self.cookies,
                timeout=10,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
            print(response)
            response.raise_for_status()
            print(f"✓ Zmiana placówki na ID={szk_id} - status: {response.status_code}")
            # Odśwież stronę po zmianie
            self.driver.refresh()
            WebDriverWait(self.driver, 10).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            # Ponowne zamknięcie powiadomienia po zmianie
            self.close_notification_if_present()
            return True
        
        except Exception as e:
            print(f"✗ Błąd zmiany placówki ID={szk_id}: {e}")
            return False


    def close_notification_if_present(self):
        """Zamknięcie powiadomienia o nowych wiadomościach (opcjonalne)"""
        try:
            short_wait = WebDriverWait(self.driver, 3)
            short_wait.until(
                EC.visibility_of_element_located(
                    (By.XPATH, "//span[contains(@class,'ext-mb-text') and contains(., 'Masz nowe wiadomości')]")
                )
            )
            ok_button = short_wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//div[contains(@class,'x-window') and .//span[contains(@class,'ext-mb-text') and contains(., 'Masz nowe wiadomości')]]//button[normalize-space(text())='OK']")
                )
            )
            ok_button.click()
            print("✓ Zamknięto powiadomienie")
            time.sleep(1)
            return True
        except TimeoutException:
            return False
        

    def get_headers(self):
        """Pobranie cookies z przeglądarki"""
        try:
            browser_cookies = self.driver.get_cookies()
            self.cookies = {cookie['name']: cookie['value'] for cookie in browser_cookies}
            print(f"Pobrano {len(self.cookies)} cookies")
        except Exception as e:
            print(f"Błąd podczas pobierania headers: {e}")

    def select_bills(self, rozdzial = None, school_name: int = None):
        """Nawigacja do formularza rozliczenia z wyborem szkoły"""
        try:
            self.close_notification_if_present()
            print(school_name)
            #Wybór szkoły jeśli podana
            if school_name:
                print('Próba zmiany placówki')
                success = self.select_school(school_name)
                if not success:
                    print("Kontynuuję bez zmiany szkoły")
                self.close_notification_if_present()    
            #Menu Rozliczenie dotacji
            menu_exe = WebDriverWait(self.driver, self.wait_time).until(
                EC.element_to_be_clickable((By.XPATH, "//em[contains(@class, 'x-unselectable')]//button[contains(text(), 'Rozliczenie dotacji')]"))
            )
            menu_exe.click()
            WebDriverWait(self.driver, self.wait_time).until(
                EC.presence_of_element_located((By.CLASS_NAME, "x-grid3-scroller"))
            )
            print("Czekam na bazę")
            #Czekanie na załadowanie menu rozwijalnego
            bazowy_title = WebDriverWait(self.driver, self.wait_time).until(
                EC.element_to_be_clickable((By.XPATH, f"//div[contains(@class, 'x-grid-group-title') and normalize-space(text()='{rozdzial}')]"))
            )
            # Scroll + kliknięcie na title (nie na body!)
            self.driver.execute_script("arguments[0].scrollIntoView(true);", bazowy_title)
            time.sleep(0.5)
            print("Czekam na miesiące", bazowy_title.text.strip()) 
            # Czekaj na rozwinięcie (pojawi się x-grid-group-body)
            WebDriverWait(self.driver, self.wait_time).until(
                EC.presence_of_element_located((By.XPATH, f"//div[contains(@class, 'x-grid-group-body') and ancestor::div[contains(@class, 'x-grid-group') and .//div[contains(text(), '{rozdzial}')]]]"))
            )
            
            print(f"✓ Wybrano rozdział '{rozdzial}'")
            
        except Exception as e:
            print(f"✗ Błąd nawigacji: {e}")
            raise


    def switch_to_month_and_documents(self, miesiac_num: str, rozdzial = None):
        """Przełączenie na konkretny miesiąc i zakładkę Dokumenty"""
        try:
            miesiac_tekst = self.miesiace_map.get(miesiac_num, f"{miesiac_num} ??")
            print(f"Przełączam na miesiąc: {miesiac_tekst} ({miesiac_num})")

            if rozdzial is not None:
                try:
                    selected_row = self.driver.find_element(By.XPATH, "//div[contains(@class, 'x-grid3-row-selected')]")
                    # Szukamy najbliższego rodzica z id zawierającym 'Rozdzial-'
                    current_group = selected_row.find_element(By.XPATH, "./ancestor::div[contains(@id, 'Rozdzial-')]")
                    group_id = current_group.get_attribute("id")  # np. ext-gen94-gp-Rozdzial-Egzaminy
                    print(f"Aktywny rozdział: {group_id}")
                except:
                    group_id = f"Rozdzial-{rozdzial}"  # np. Rozdzial-80116
                    print(f"Brak zaznaczenia, używam: {group_id}")

                
                # Znajdź wiersz z miesiącem (pomijamy "Raport półroczny/roczny")
                month_xpath = (
                    f"//div[contains(@id, '{group_id}')]"  # Konkretna grupa (Egzaminy/80116/80151)
                    f"//div[contains(@class, 'x-grid3-col-1') and normalize-space(text())='{miesiac_tekst}']"
                )

            
            month_row = WebDriverWait(self.driver, self.wait_time).until(
                EC.element_to_be_clickable((
                    By.XPATH, month_xpath
                    #f"//div[contains(@class, 'x-grid3-row')]//div[contains(@class, 'x-grid3-cell-inner') and normalize-space(text())='{miesiac_tekst}' "
                    #f"and not(ancestor-or-self::*[contains(text(), 'Raport')])]"
                ))
            )
            
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", month_row)
            time.sleep(0.3)
            #month_row.click()
            month_row.click()
            # Oczekiwanie na zaznaczenie
            WebDriverWait(self.driver, self.wait_time).until(
                EC.presence_of_element_located((
                    By.XPATH, 
                    f"//div[contains(@class, 'x-grid3-row-selected')]//div[normalize-space(text())='{miesiac_tekst}']"
                ))
            )
            # Kliknięcie zakładki Dokumenty
            document_tab = WebDriverWait(self.driver, self.wait_time).until(
                EC.element_to_be_clickable((By.XPATH, "//li[.//span[contains(@class, 'x-tab-strip-text') and normalize-space(text())='Dokumenty']]"))
            )
            document_tab.click()
            
            print(f"Przełączono na {miesiac_tekst} → Dokumenty")
            
        except Exception as e:
            print(f"Błąd przełączania na miesiąc {miesiac_tekst}: {e}")
            raise

    def parse_file(self, wydatki_file_name: Optional[str] = None, szkolaID = None, rozdzial = None, encoding: str = "utf-8"):
        """Parsowanie pliku CSV z wydatkami - NOWA LOGIKA DLA MIESIĘCY"""
        url = f'https://{self.host}/ODPN/Szkoly/RozliczenieDotacji/Kontrolki/Taby/Dokument/Dokument.asmx/SubmitForm'
        numery_pol_egzamin = {
            '1. Wydatki na wynagrodzenia osoby fizycznej prowadzącej podmiot dotowany za pełnienie funkcji dyrektora  - podanie kwot w poszczególnych miesiącach': (17000, -1),
            '2. Wydatki na wynagrodzenia kadry pedagogicznej ': (17001, -2),
            '3. Wydatki na wynagrodzenia administracji i obsługi': (17002, -3),
            '4. Wydatki na pochodne od wynagrodzeń ': (17003, -4),
            '5. Wydatki na zakup pomocy naukowych i dydaktycznych': (17004, -5),
            '6. Wydatki na zakup artykułów administracyjno-biurowych': (17005, -6),
            '7. Wydatki na wynajem pomieszczeń': (17006, -7),
            '8. Wydatki na zakup wyposażenia': (14, -8),
            '9. Wydatki na zakup usług': (17007, -9),
            '10. Opłaty za media (energia elektryczna, gaz, wod-kan., energia cieplna, itp.)': (17008, -10),
            '11. Pozostałe wydatki -wymienić jakie': (15, -11),
            '12.Zakup środków trwałych oraz wartości niematerialnych i prawnych, których mowa w art. 35 ust 1 pkt 2 ustawy o finansowaniu zadań oświatowych, a niewymienionych w zestawieniu powyżej': (238, -12),
        }
        numery_pol_oswiata = {
            '1. Wydatki na wynagrodzenia osoby fizycznej prowadzącej podmiot dotowany za pełnienie funkcji dyrektora  - podanie kwot w poszczególnych miesiącach': (13, -1),
            '2. Wydatki na wynagrodzenia kadry pedagogicznej ': (17000, -2),
            '3. Wydatki na wynagrodzenia administracji i obsługi': (17001, -3),
            '4. Wydatki na pochodne od wynagrodzeń ': (17002, -4),
            '5. Wydatki na zakup pomocy naukowych i dydaktycznych': (17003, -5),
            '6. Wydatki na zakup artykułów administracyjno-biurowych': (17004, -6),
            '7. Wydatki na wynajem pomieszczeń': (17005, -7),
            '8. Wydatki na zakup wyposażenia': (17006, -8),
            '9. Wydatki na zakup usług': (14, -9),
            '10. Opłaty za media (energia elektryczna, gaz, wod-kan., energia cieplna, itp.)': (17007, -10),
            '11. Pozostałe wydatki -wymienić jakie': (17008, -11),
            '12.Zakup środków trwałych oraz wartości niematerialnych i prawnych, których mowa w art. 35 ust 1 pkt 2 ustawy o finansowaniu zadań oświatowych, a niewymienionych w zestawieniu powyżej': (15, -12),
        }
        niepowodzenia = []
        file_path = Path(wydatki_file_name or f"wydatki_{self.ID_rozdzial}.csv")
        
        if not file_path.exists():
            raise FileNotFoundError(f"Plik {file_path} nie istnieje")
        
        print(f"Przetwarzanie pliku: {file_path}")
        
        # Grupowanie wierszy po miesiącach
        miesiace_data = {}
        with file_path.open('r', encoding=encoding) as plik_dane:
            csv_reader = csv.reader(plik_dane, delimiter=';')
            for row_num, dane in enumerate(csv_reader, 1):
                try:
                    if len(dane) < 10:  # Oczekujemy kolumny kategorii na końcu
                        niepowodzenia.append((row_num, "Za mało kolumn (potrzebna kolumna kategorii na końcu)"))
                        continue
                    miesiac_num = dane[9].strip().split('/')[0]
                    if len(miesiac_num) == 1:
                        miesiac_num = '0' + miesiac_num
                    
                    if miesiac_num not in miesiace_data:
                        miesiace_data[miesiac_num] = []
                    miesiace_data[miesiac_num].append((row_num, dane))
                except Exception as e:
                    niepowodzenia.append((row_num, f"Błąd parsowania wiersza: {e}"))
        
        # Przetwarzanie po miesiącach
        for miesiac_num, rows in miesiace_data.items():
            print(f"\n=== PRZETWARZAM MIESIĄC {self.miesiace_map[miesiac_num]} ({miesiac_num}) ===")
            
            try:
                # Przełącz na miesiąc + Dokumenty + capture
                self.switch_to_month_and_documents(miesiac_num, rozdzial)
                self.capture_response(f"capture_{miesiac_num}")
                
                # Przetwarzaj wiersze tego miesiąca
                for row_num, dane in rows:
                    try:
                        kategoria = dane[0]
                        numery_pol = numery_pol_oswiata
                        if self.ID_rozdzial == "Egzaminy":
                            numery_pol = numery_pol_egzamin
                        if not any(kategoria.lower() in key.lower() for key in numery_pol):
                        #if dane[1].lower() not in numery_pol:
                            niepowodzenia.append((row_num, f"Nieznana kategoria: '{kategoria}'"))
                            continue
                        dane_post = None
                        for key, value in numery_pol.items():
                            if kategoria.lower() in key.lower():
                                dane_post = self._process_row_data(dane, numery_pol[key], row_num)
                                break
                        
                        #dane_post = self._process_row_data(dane, numery_pol[kategoria], row_num)
                        if dane_post is None:
                            continue
                        
                        print(f"Wiersz {row_num} ({kategoria})... ", end='')
                        success = self._send_request(url, dane_post)
                        if success:
                            print("✓")
                        else:
                            print("✗")
                            niepowodzenia.append((row_num, "Błąd wysyłania")) 
                        time.sleep(1)
                    except Exception as e:
                        print(f"✗ {e}")
                        niepowodzenia.append((row_num, str(e)))
                        
            except Exception as e:
                print(f"✗ Błąd przetwarzania miesiąca {miesiac_num}: {e}")
                niepowodzenia.extend([(r[0], f"Błąd miesiąca {miesiac_num}: {e}") for r in rows])
        
        self._report_errors(niepowodzenia)
        self._finalize_form()

    def _process_row_data(self, dane: List[str], nr_pozycji: tuple, row_num: int) -> Optional[Dict]:
        """Przetworzenie danych z wiersza CSV - DOKŁADNE MAPOWANIE"""
        try:
            print(f"DEBUG CSV row {row_num}: {dane}")
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
            # DOKŁADNE mapowanie pól wg kolejności z capture:
            if len(self.fields_name) > 7:  # _5 = RODZAJ WYDATKU
                dane_post[self.fields_name[0]] = dane[3].strip()  
                # _62 = DATA WYSTAWIONA
                dane_post[self.fields_name[1]] = f"{dane[2].strip()}T00:00:00"
                # _63 = REFERENCJA
                dane_post[self.fields_name[2]] = dane[3].strip()
                # _64 = DATA ZAPŁATY
                dane_post[self.fields_name[3]] = f"{dane[4].strip()}T00:00:00" 
                # _67 = RODZAJ/NR DOWODU ZAPŁATY - NIE MA
                #dane_post[self.fields_name[4]] = dane[6].strip()  
                # _82 = FORMA ZAPŁATY
                dane_post[self.fields_name[4]] = "przelew"
                # _65 = KOSZT CAŁKOWITY
                dane_post[self.fields_name[5]] = self._parse_amount(dane[5])
                # _6_w = DOTACJA NIEPELNOSPRAWNY
                if dane[6] != "":
                    dane_post[self.fields_name[6]] = self._parse_amount(dane[6])
                else:
                    dane_post[self.fields_name[6]] = self._parse_amount('0')
                # _7_wn = DOTACJA NIEPELNOSPRAWNY
                if dane[7] != "":
                    dane_post[self.fields_name[7]] = self._parse_amount(dane[7])
                else:
                    dane_post[self.fields_name[7]] = self._parse_amount('0')
            if len(self.fields_name) > 8:
                # _81_wn2 = KSZTALCENIE SPECJALNE
                dane_post[self.fields_name[8]] = self._parse_amount('0')
                
            print(f"DEBUG FINAL dane_post: {json.dumps(dane_post, indent=2)}")
            return dane_post
        except (IndexError, ValueError) as e:
            print(f"✗ Błąd wiersza {row_num}: {e}")
            return None

    def _parse_amount(self, amount_str: str) -> float:
        cleaned = amount_str.replace(',', '.').replace(' ', '').strip()
        return round(float(cleaned), 2)

    def _send_request(self, url: str, data: Dict) -> bool:
        try:
            print(f"DEBUG POST data: {json.dumps(data, indent=2)}")
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

            print(f"Response status: {response.status_code}")
            if not response.ok:
                print(f"Response body: {response.text[:500]}")
            
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            print(f"Błąd żądania: {e}")
            return False

    def _report_errors(self, niepowodzenia: List):
        if niepowodzenia:
            print(f"\nLista błędów ({len(niepowodzenia)}):")
            for row_num, error in niepowodzenia:
                print(f"Wiersz {row_num}: {error}")
        else:
            print("\nWszystkie wiersze OK!")

    def _finalize_form(self):
        try:
            mask_elements = self.driver.find_elements(By.CLASS_NAME, "ext-el-mask")
            for mask in mask_elements:
                self.driver.execute_script("arguments[0].style.display = 'none';", mask)
            
            return_element = WebDriverWait(self.driver, self.wait_time).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#ext-gen61"))
            )
            link_element = return_element.find_element(By.CLASS_NAME, "vlibrary-topLink")
            link_element.click()
            print("Finalizacja OK")
        except Exception as e:
            print(f"Błąd finalizacji: {e}")

    def __enter__(self):
        self._initialize_connection()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, 'driver'):
            self.driver.quit()
            print("Przeglądarka zamknięta")

if __name__ == "__main__":
    
    config = None
    try:
        config_path = Path("SzkolaDane.json")
        with config_path.open('r', encoding='utf-8') as f:
            config = json.load(f)
    except:
        print('Nie otworzono wskazanego pliku')
    print(config)
    with SiteWrap("powiat-belchatowski.odpn.pl") as site:
        site.login(config.get('login') if config else "", config.get('haslo') if config else "")  # ręczne logowanie
        site.get_headers()
        site.select_bills(config.get('rozdzial'), config.get('szkolaID') if config else 0)  #podany numer to numer placówki
        site.parse_file(f"belchatow_test2.csv", config.get('szkolaID'), config.get('rozdzial'))  #sztywna nazwa pliku do parsowania
