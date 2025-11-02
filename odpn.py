from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import requests
import time
from urllib.parse import urlparse

class SiteWrap:
    def __init__(self, host, rozdzialSzkola=0, options = ()):
        self.host=host
        self.szkolaRozdzial=rozdzialSzkola
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_experimental_option('detach',True)
        chrome_options.add_argument('--enable-logging')
        chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})     

        for i in options:
            chrome_options.add_argument("--" + i)
        #chrome_options.add_argument("--kiosk")
        #chrome_options.add_argument("--headless=new")
        #chrome_options.add_argument("--disable-gpu")
        #chrome_options.add_argument("--disable-extensions")
        #chrome_options.add_argument("--no-sandbox")
        #self.driver = webdriver.Chrome(options=chrome_options)
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_cdp_cmd("Network.enable", {})

        self.responses = []

        while True:
            try:
                #DO ZROBIENIA - sprawdzanie aktualnego adresu WWW celem załadowania
                #dowolnej strony ODPN
                self.driver.get(f"https://{self.host}")
                if self.driver.execute_script("return document.readyState") == "complete":                    
                    self.host= urlparse(self.driver.current_url).netloc.split(':')[0]
                    break
                print('DBG',self.driver.current_url)
                #else:
                 #   time.sleep(2)
            except:
                print('err',self.driver.current_url)
                time.sleep(2)
        self.waitTime = 20

    def capture_response(self, file_name="zrzut"):
        logs = self.driver.get_log("performance")
        f = open(f"{file_name}.txt", "w")
        for l in logs:
            for k in l.keys():
                #print(k)
                if k=='message':
                    if l[k].find(f'https://{self.host}/ODPN/Szkoly/RozliczenieDotacji/Kontrolki/Taby/Dokument/Dokument.asmx/GridGetData') == -1 or l[k].find('Network.requestWillBeSent') == -1:
                        continue
                    d = eval(l[k].replace('false','False').replace('true','True'))
                    d = eval(d['message']['params']['request']['postData'])
                    #print(d['data'])
                    self.ID_szkid = d['data']['szkid']
                    self.ID_rok = d['data']['rok']
                    self.ID_miesiac = d['data']['miesiac']
                    self.ID_rozdzial = d['data']['rozdzial']
                    self.ID_Dokumentu = d['data']['IdDokumentu']
                    self.IDWydruk = d['data']['wydrukId']
                    self.fieldsName = []
                    for row in d['data']['v_store_fields']:
                        if 'allowBlank' in row.keys():
                            if row['allowBlank']==False:
                                self.fieldsName.append(row['name'])
                    print(self.fieldsName)
                    print(self.ID_szkid,self.ID_rok,
                          self.ID_miesiac,self.ID_rozdzial,self.ID_Dokumentu,self.IDWydruk)
                    break
                    f.write(f"{self.d['data']}\n")
        f.close()

    def login(self, loginwd="", passwd=""):
        try:
            lname = WebDriverWait(self.driver,self.waitTime).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[name=Login]")))
            if loginwd!="":
                lname.send_keys(loginwd)
            lpass = self.driver.find_element(by=By.ID, value="Haslo")
            if passwd!="":
                lpass.send_keys(passwd)
            if loginwd!="" and passwd!="":
                self.driver.find_element(by=By.ID, value="ButtonLogowanie").click()
            else:
                menuExe = WebDriverWait(self.driver,float('inf')).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#ext-gen43")))
        finally:
            pass

    def getHeaders(self):
        #for h in self.driver.requests:
        #    print(h.headers['cookie'])
        self.cookies = dict()
        for c in self.driver.requests[-1].headers['cookie'].split('; '):
            tmp=c.split('=')
            self.cookies[tmp[0]]=''
            index=1
            while(True):
                self.cookies[tmp[0]] +=tmp[index]
                index+=1
                if index == len(tmp):
                    break
                self.cookies[tmp[0]] +='='                
        #print(self.cookies)

    def selectBills(self):
        menuExe = WebDriverWait(self.driver,self.waitTime).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#ext-gen43")))
        menuExe.click()
        if self.szkolaRozdzial != 0:
            menuExe = WebDriverWait(self.driver,self.waitTime).until(EC.presence_of_element_located((By.CSS_SELECTOR, f"#ext-gen90-gp-Rozdzial-{self.szkolaRozdzial}-bd")))
            menuExe = menuExe.find_element(By.CLASS_NAME, "pencil")
            menuExe.click()        
        #menuExe = WebDriverWait(self.driver,self.waitTime).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#ext-gen159")))
        #menuExe = WebDriverWait(self.driver,self.waitTime if self.szkolaRozdzial !=0 else float('inf')).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#ext-comp-1049__dokumentId_15")))
        menuExe = WebDriverWait(self.driver,self.waitTime if self.szkolaRozdzial !=0 else float('inf')).until(EC.presence_of_element_located((By.XPATH, "//li[.//span[contains(@class, 'x-tab-strip-text') and normalize-space(text())='Wydatki']]")))
        menuExe.click()
        menuExe = WebDriverWait(self.driver,self.waitTime).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".add")))
        menuExe.click()


    def parseFile(self, name=None,code="utf8"):
        url = f'https://{self.host}/ODPN/Szkoly/RozliczenieDotacji/Kontrolki/Taby/Dokument/Dokument.asmx/SubmitForm'
        name = f"wydatki_{self.ID_rozdzial}.csv" if name == None else name
        numery_pol = {  # (x, y): x - NumerPola, y - Id
            '1.': (1, -1),
            '2.': (2, -2),
            '3.1.': (4, -3),
            '3.2.': (5, -4),
            '3.3.': (6, -5),
            '3.4.': (7, -6),
            '3.5.': (8, -7)
        }

        niepowodzenia = []
        plik_dane = open(name, 'r', encoding=code)

        for wiersz in plik_dane:
            time.sleep(1)
            #wiersz=wiersz.strip().replace(',',';')
            dane = wiersz.strip().split(';')

            poz_z_tabeli_rodzaj_wydatku = dane[1]
            rodzaj_i_nr_dowodu_poniesienia_wydatku = dane[2]
            pelna_kwota_zobowiazania = round(float(dane[3].replace(',', '.').replace(' ', '')), 2)
            data_wystawienia_rachunku = dane[4] + "T00:00:00"
            przedmiot_zakupu = dane[5]
            data_dokonania_platnosci = dane[6] + "T00:00:00"
            kwota_sfinansowana_z_dotacji = round(float(dane[7].replace(',', '.').replace(' ', '')), 2)
            kwota_wydatku_orzeczenia = round(float(dane[8].replace(',', '.').replace(' ', '')), 2)

            miesiac = str(int(dane[6].split('-')[1]))
            if poz_z_tabeli_rodzaj_wydatku in numery_pol:
                nr_pozycji = numery_pol[poz_z_tabeli_rodzaj_wydatku]
                dane_post = {
                    "Id": str(nr_pozycji[1]),
                    "ID_szkid": self.ID_szkid,  
                    "ID_rok": self.ID_rok,
                    "ID_miesiac": self.ID_miesiac, 
                    "ID_rozdzial": self.ID_rozdzial,
                    "NumerPola": str(nr_pozycji[0]),
                    "ID_Dokumentu": self.ID_Dokumentu,
                    "ID_Wydruk": self.IDWydruk,
                    self.fieldsName[0]: rodzaj_i_nr_dowodu_poniesienia_wydatku,
                    self.fieldsName[1]: pelna_kwota_zobowiazania,
                    self.fieldsName[2]: data_wystawienia_rachunku,
                    self.fieldsName[3]: przedmiot_zakupu,
                    self.fieldsName[4]: data_dokonania_platnosci,
                    self.fieldsName[5]: kwota_sfinansowana_z_dotacji,
                    self.fieldsName[6]: kwota_wydatku_orzeczenia
                }
            else:
                print("nieznany rodzaj wydatku.")
                niepowodzenia.append((dane[0], f'nieznany rodzaj wydatku - {dane[0]=} {rodzaj_i_nr_dowodu_poniesienia_wydatku}'))
                continue

            print("wysyłam żądanie... ", end='')
            print({"data": dane_post}, self.cookies)
            r = requests.post(url=url, json={"data": dane_post}, cookies=self.cookies)

        print("Lista błędów:")
        for blad in niepowodzenia:
            print(f"{blad[0]} -- {blad[1]}")
        menuExe = WebDriverWait(self.driver,self.waitTime).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#ext-gen61")))
        self.driver.execute_script("arguments[0].style.display = 'none';",
                                   self.driver.find_element(by=By.CLASS_NAME, value="ext-el-mask") )
        menuExe = menuExe.find_element(By.CLASS_NAME, "vlibrary-topLink")
        menuExe.click()
#https://czestochowa.odpn.pl/ODPN/Szkoly/RozliczenieDotacji/Kontrolki/Taby/Dokument/Dokument.asmx/GridGetData

#1
        #ext-gen90-gp-Rozdzial-80120-bd
#("headless=new","disable-gpu", "disable-extensions", "no-sandbox")
site = SiteWrap("czestochowa.odpn.pl")
site.login("","")
site.getHeaders()
site.selectBills()
site.capture_response("all")
site.parseFile()
