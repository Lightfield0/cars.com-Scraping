import requests
from bs4 import BeautifulSoup
import json
import time
import socket
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

class CarsScraper:
    def __init__(self, headers):
        self.results = []
        self.headers = headers
        self.base_url = "https://www.cars.com/shopping/results/"
        self.dealer_url = "https://www.cars.com/dealers/{customer_id}"
        self.zip_codes = self.load_zip_codes()

    def load_zip_codes(self):
        # ZIP kodlarını CSV dosyasından oku
        df = pd.read_csv('output.csv')
        return df['ZIP CODE'].unique().tolist()
    
    def is_connected(self):
        """Bir internet bağlantısı olup olmadığını kontrol eder."""
        try:
            # Google DNS sunucusuna ping atmaya çalışıyoruz.
            socket.create_connection(("8.8.8.8", 53))
            return True
        except OSError:
            pass
        return False

    def retry_request(self, url, headers, params, max_retries=3, retry_delay=5):
        for attempt in range(max_retries):
            try:
                # Eğer internet bağlantısı yoksa bekleyin.
                while not self.is_connected():
                    print("No internet connection. Retrying in 30 seconds...")
                    time.sleep(30)

                response = requests.request("GET", url, headers=headers, params=params, timeout=10)
                return response
            except requests.RequestException as e:
                if attempt < max_retries - 1:  # i.e. not the last attempt
                    print(f"Error occurred: {e}. Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    print(f"Error occurred: {e}. No more retries left. Returning None.")
                    return None

    def get_customer_ids(self, zip_code, page_size=100):
        customer_ids = set()
        seen_hrefs = set()
        page = 1

        while True:
            params = {
                "page": str(page),
                "page_size": str(page_size),
                "zip": str(zip_code)
            }
            print(f"Processing page {page} for zip code {zip_code}")  # Hangi sayfa ve ZIP kodunun işlendiğini yazdır

            response = self.retry_request(self.base_url, self.headers, params)
            if response is None:
                print("Failed to fetch the page after retries. Skipping to the next page.")
                continue

            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Sayfadaki href özelliklerini topla
            current_page_hrefs = set(a['href'] for a in soup.find_all('a', class_='vehicle-card-link js-gallery-click-link', href=True))

            # Eğer bu sayfadaki href'ler önceki sayfalarda görülmüşse, döngüyü durdur
            if current_page_hrefs.issubset(seen_hrefs):
                print(f'No new listings on page {page} for zip code {zip_code}. Stopping...')  # Yeni listeleme yok, durduruluyor
                break
            
            # Aksi takdirde, href'leri seen_hrefs kümesine ekle
            seen_hrefs.update(current_page_hrefs)
            
            # Müşteri ID'lerini topla (Eğer müşteri ID'lerini almak istiyorsanız)
            a = soup.find("cars-datalayer", attrs={"store": "als"})
            if a:
                data = json.loads(a.text)
                for entry in data:
                    for vehicle in entry['vehicle_array']:
                        customer_ids.add(vehicle['customer_id'])
            
            time.sleep(0.5)
            
            # Sayfa numarasını arttır
            page += 1
            
        
        print(f'Fetched {len(customer_ids)} customer IDs for zip code {zip_code}.')  # Müşteri ID'leri alındı
        return customer_ids

    def process_zip_code(self, zip_code):
        print(f'Processing zip code {zip_code}...')  # ZIP kodu işleniyor
        customer_ids = self.get_customer_ids(zip_code)
        return customer_ids  # Her ZIP kodu için elde edilen müşteri ID'lerini döndür

    def request_dealer_page(self, customer_id):
        print(f'Requesting dealer page for customer ID {customer_id}...')  # Bayi sayfası isteniyor

        url = self.dealer_url.format(customer_id=customer_id)
        response = requests.request("GET", url, headers=self.headers)

        soup = BeautifulSoup(response.content, 'html.parser')
    
        dealer_name = (found := soup.find('h1', class_='sds-heading--1 dealer-heading')) and found.text.strip()

        if not dealer_name:
            return

        # dealer_website'i çekme
        dealer_website_tag = soup.find('a', {'data-connection-intent-id': 'dealer-profile-page-website-transfer'})
        dealer_website = dealer_website_tag['href'] if dealer_website_tag else None

        # dealer_address ve dealer_direction_link'i çekme
        direction_tag = soup.find('a', {'data-connection-intent-id': 'dealer-directions-connection'})
        dealer_direction_link = direction_tag['href'] if direction_tag else None
        dealer_address = direction_tag['aria-label'] if direction_tag else None
        
        # Telefon numaralarını çekme
        result = {
                "dealer_name": dealer_name,
                "dealer_website": dealer_website,
                "dealer_direction_link": dealer_direction_link,
                "dealer_address": dealer_address,
                "URL": response.url.strip()
                }

        phones = soup.find_all("div", class_="dealer-phone")

        for phone in phones:
            title = phone.find("span", class_="phone-number-title").text.strip()
            # Eğer title boşsa "Used" olarak değiştir
            if not title:
                title = "Used"
            number = phone.find("a", class_="phone-number").text.strip()
            result[title] = number

        print(result)
        
        self.results.append(result)
        # İsteğin sonuçlarını işleme
        # ...
    def save_to_excel(self, filename="dealers.xlsx"):
        df = pd.DataFrame(self.results)
        df.to_excel(filename, index=False)

    def run(self):
        all_customer_ids = set()  # Tüm müşteri ID'lerini bu kümede topla
        print('Starting to process zip codes...')  # ZIP kodları işlenmeye başlanıyor

        with ThreadPoolExecutor() as executor:
            # Paralel olarak her ZIP kodu için get_customer_ids metodunu çalıştır
            results = executor.map(self.process_zip_code, self.zip_codes)
        
        # Sonuçları all_customer_ids kümesine ekle
        for customer_ids in results:
            all_customer_ids.update(customer_ids)
        
        # all_customer_ids kümeyi bir txt dosyasına kaydet
        with open('customer_ids.txt', 'w') as f:
            for cid in all_customer_ids:
                f.write(str(cid) + '\n')

        print('Starting to request dealer pages...')  # Bayi sayfaları istenmeye başlanıyor
        with ThreadPoolExecutor(max_workers=4) as executor:
            executor.map(self.request_dealer_page, all_customer_ids)  # Paralel olarak her müşteri ID'si için dealer sayfasını iste

        self.save_to_excel()


# Headers tanımı (Örneğin: User-Agent, vs.)
headers = {
  'authority': 'www.cars.com',
  'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
  'accept-language': 'tr-TR,tr;q=0.9',
  'cache-control': 'max-age=0',
  'cookie': 'ToyotaNewAd=false; CARS_als_loaded=true; CARS_experience_testing={"session_id":"3d53dc31-6f9c-4ea8-8ad4-bf47d09bb026","tnt_id":"3d53dc31-6f9c-4ea8-8ad4-bf47d09bb026.34_0"}; CARS_has_visited=; CARS_logged_in=false; CARS_trip_id=e34b8329-2dbb-4d56-919d-b1853d1f2d5d; bm_sz=F2CC5771C85DE8C2AA6B4A355267D36F~YAAQvoYUAg6SL/iKAQAAGOGJChWmC5UvDuqtSUW1yeAsPKywTi3rmDXbeIoBszEJ4XeMKnMAtYPjFxHh9NUR4Xi8SMC8K7aFkvKScZ9ySBdihkWpxVgxDU/G64SD2w+FmlzeGdrnSJLHxgotqxpDFJNTpBOAc4AAYDO++BBJRRzY8vYXNpW4MeaxwXfbYsllrEkYVqyUTYzNBE5qFRKRcX96lFQYHaYkCRC+hONL+igGrpgICfayqw9iIWkbY3YblEeMQQOlxneaJ1TvqDrTKIT/0wuDO4dsT28zns/ge/D0~3293762~3618116; CARS_navClick=; ak_bmsc=E7F0BE88D5FC808A0E9BAAD044830816~000000000000000000000000000000~YAAQvoYUAj2SL/iKAQAA6emJChUjSfHF3j3BLeJIrGUqIk8Qyrw7eb2negnnwOFQAC0yynm3CS/VoJlioK+REA1ei01gtjlubZfF7sDrSDiL+U/JC5ARB6bpLu5bPT/gYyoLvPr9naPkiRLiSPr3rbTCda08nTGi3DBKBqeUd7T6D9zh5SqO/yMrdR8zQSIvUNPyLFbd9fkxzGJJpxRetAUzwIjWSIcbNxaqBu3Yit+/aLzEsWf626OMLO1+f7UQRbQ/0P8iN/tgUE4YNgWD4ocscTrmmJ/cw9oA/KeeglKCOFWSSfDz3D6HjckGmqZr7liH2ymxjJoo4M2VAhyy3dSQ+j1gWJxdeXvRIIRu7fS+bxdAX2Vz7UU9fi1nKgjXhseG1sUIUHATAee/pInsEN58AWVMu7U66NUbbdLIblSM1A+TEET38yxi46RpLpmPPppCx+j8R2J7kYEZpjlAFSj1pgaLJCiIh17567r0VPzCVq+Hs/P3B1OPlP4g; s_ecid=MCMID%7C23143105766679683772866057691083138844; AMCVS_C78C1CFE532E6E2E0A490D45%40AdobeOrg=1; _cs_mk_aa=0.022461580964973082_1696688893476; AMCV_C78C1CFE532E6E2E0A490D45%40AdobeOrg=1176715910%7CMCIDTS%7C19638%7CMCMID%7C23143105766679683772866057691083138844%7CMCAID%7CNONE%7CMCOPTOUT-1696696091s%7CNONE%7CMCAAMLH-1697293691%7C6%7CMCAAMB-1697293691%7Cj8Odv6LonN4r3an7LhD3WZrU1bUpAkFkkiY1ncBR96t2PTI%7CMCSYNCSOP%7C411-19645%7CvVersion%7C5.4.0; s_lv_s=First%20Visit; s_inv=0; s_cc=true; _gid=GA1.2.849265699.1696688897; _gcl_au=1.1.2097986781.1696688897; _pin_unauth=dWlkPVltUXdNamN6TmpVdE5tVmtZaTAwTkdSaExUZ3pNVFF0WVdOak5UUXdNbVE0WW1ZMw; ToyotaNewAd=false; di_roxanne__visit_id=8057982562; di_roxanne__visitor_id=12250551822; _aeaid=55e8b292-2da5-4c84-913c-bb19c0ceac90; aelastsite=RVHvE4glMR0sC5iYWBair1aiHO0Ez37924foGSUCRDBlkWrbrSt4Qc%2BBnB7QmaV7; aelreadersettings=%7B%22c_big%22%3A0%2C%22rg%22%3A0%2C%22memph%22%3A0%2C%22contrast_setting%22%3A0%2C%22colorshift_setting%22%3A0%2C%22text_size_setting%22%3A0%2C%22space_setting%22%3A0%2C%22font_setting%22%3A0%2C%22k%22%3A0%2C%22k_disable_default%22%3A0%2C%22hlt%22%3A0%2C%22disable_animations%22%3A0%2C%22display_alt_desc%22%3A0%7D; iovoxMCM=other; iovox_sea=eyJmaXJzdF92aXNpdCI6IjIwMjMtMTAtMDdUMTQ6MzA6MDcuOTczWiIsInJlZmVyZXJfcGFnZSI6Imh0dHBzOi8vd3d3LmNhcnMuY29tL3Nob3BwaW5nL2FsYmFueS1ueS8iLCJmaXJzdF9wYWdlIjoiaHR0cHM6Ly93d3cuY2Fycy5jb20vdmVoaWNsZWRldGFpbC9jZjNiMDVkMS1hMjE1LTRiNjAtYTAzYi0yNDU1NDIxZDkzNGMvIn0=; iovox_id=e7697b26-63e4-48db-a842-dfdf013730f2; _abck=9A88A1203CBFC2CDB9A90DBBF2618196~0~YAAQvoYUAr1uMPiKAQAACxGjCgoKqTBn5aR8FXoonl/qwkwFezjC9cu7eE1aLMYdhadJ90r5/nAKzwCZctSEtYX95QnjYYaKblUB5R4l/h9f6+RTK7XS8Q2/lFeVoACxYir+5sc8v8NQBKT61fiCzaIu/iBVjx2RCup/LwQaYLDW5y3KoFkK7uxTdR3LzN7Ui/d3I77XyVY/hSSaokMU9ftdpEg+k84+PZ9JWj1PJuhS+P5o/kO8mSyvbHtQUgoivAu6XNn6VBPt+tKtORZBffb73aS47L36Ht7wsX6LfbVnr5KOGkWGz49jVGssFNg9vYVSPTMm2OrAnu1W+bRPUI7G9yEAQTcyFPk8cX5JL+kLm7sE5c+dxv64djNetyaRsuyZ5LSSJ3877TXlF37ghh/LobaGr7c=~-1~-1~-1; s_sq=%5B%5BB%5D%5D; _gat_gtag_UA_50492232_1=1; CARS_marketing_source=SFMyNTY.g2gDdAAAAARkAApfX3N0cnVjdF9fZAAjRWxpeGlyLkNhcnNXZWIuUGx1Zy5NYXJrZXRpbmdTb3VyY2VkAAhhZmZfY29kZW0AAAAGc2VvYWZmZAAMY2xpY2tfc291cmNldAAAAABkAAN1dG10AAAAC2QACl9fc3RydWN0X19kACVFbGl4aXIuQ2Fyc1dlYi5TaXRlQWN0aXZpdHkuVVRNUGFyYW1zZAAMdXRtX2NhbXBhaWduZAADbmlsZAAPdXRtX2NhbXBhaWduX2lkZAADbmlsZAALdXRtX2NvbnRlbnRkAANuaWxkABV1dG1fZmlyc3Rfc2Vzc2lvbl9oaXRkAAVmYWxzZWQACnV0bV9tZWRpdW1kAANuaWxkAAx1dG1fbW9kaWZpZWRkAAR0cnVlZAAOdXRtX3NldF9tZXRob2RtAAAAC3JlZmVyZXJfdXJsZAAKdXRtX3NvdXJjZWQAA25pbGQACHV0bV90ZXJtZAADbmlsZAALdXRtX3RydXN0ZWRkAAR0cnVlbgYAfkOkCosBYgABUYA.aG3_Y2mc29_YmtzeWsGdCvPXW-oC-hOpFw2O_r-69oQ; CARS_search_session=SFMyNTY.g2gDdAAAAAVkAApfX3N0cnVjdF9fZAAhRWxpeGlyLkNhcnNXZWIuUGx1Zy5TZWFyY2hTZXNzaW9uZAASc2VhcmNoX2luc3RhbmNlX2lkbQAAACQ4Y2ZiOWFhNS0wYmM0LTQwMGQtOWRhNS1iNDgzZmI0NmQ1M2NkABJzZWFyY2hfbGlzdGluZ19pZHNkAANuaWxkAA1zZWFyY2hfcGFyYW1zZAADbmlsZAAOc2VhcmNoX3ppcGNvZGVtAAAABTEyMjA2bgYAfUOkCosBYgABUYA.rhE1p9xZ_mITkZZiRJJhTJQ4XgeezKHRvGXVtSlZu40; _cars_web_key=SFMyNTY.g3QAAAANbQAAAAxDQVJTX3RyaXBfaWRtAAAAJGUzNGI4MzI5LTJkYmItNGQ1Ni05MTlkLWIxODUzZDFmMmQ1ZG0AAAALX2NzcmZfdG9rZW5tAAAAGDlfNERjNzhJYlB0Rk05NlMtYkc1Nl9UQm0AAAAQYWxzX3ByaXZhdGVfZGF0YW0AAAC1UVRFeU9FZERUUS5DcVF6ay1GZ3NrNFgwVmJ5eEhVZ3FHbm43ZGRyYzFyaTVucjlQaGV6cXhvY1FIeWFLcDNWQzJUS05Zcy5XWnlpMjVZVkhlM2w3TUFlLjlIc3RzX3hqRWY5RmNaVDk3RTRWalBSbGhzRzdOclZsUGxvNTRVei1nYjU3YkJFMktac2NEV0ZON3lVQ0lwZDJ2Rm5POFEubU9DYkw3bzdndVR0X0syWmNZR2hKd20AAAARZmFjZWJvb2tfZXZlbnRfaWRtAAAAVGRISnBjRjlwWkQxbE16UmlPRE15T1MweVpHSmlMVFJrTlRZdE9URTVaQzFpTVRnMU0yUXhaakprTldRbWRITTlNVFk1TmpZNU1EWXhPVEkyTWc9PW0AAAAYZmFjZWJvb2tfZXZlbnRfaW50ZW50X2lkZAADbmlsbQAAAA9ncmFwaHFsX2FwaV9rZXltAAAAIDVycm1uV1ZsMU1EelBjRW5EdkVwM1B1MTAxSUdYRUdvbQAAAA1pc19zZWFyY2hfYm90ZAAFZmFsc2VtAAAAEGxhc3Rfdmlld2VkX3BhZ2VtAAAAES9kZWFsZXJzL3Jldmlld3MvbQAAAA9sb2NhbGVfbWFwcGluZ3N0AAAAAW0AAAANMTc4LjIzMy43Ni41MHQAAAAIZAAKX19zdHJ1Y3RfX2QAFUVsaXhpci5DYXJzV2ViLkxvY2FsZWQAD2NpdHlfc3RhdGVfc2x1Z20AAAAJYWxiYW55LW55ZAAaZGVzaWduYXRlZF9tYXJrZXRfYXJlYV9rZXltAAAACmFsYmFueXRyb3lkAAhsYXRpdHVkZUZARVZUYKpkw2QACmxvY2FsX3pvbmVtAAAAB3Vuem9uZWRkAAlsb25naXR1ZGVGwFJyFPi1iONkAAttYXJrZXRfbmFtZW0AAAAGYWxiYW55ZAAIemlwX2NvZGVtAAAABTEyMjA2bQAAAA5zZWFyY2hfemlwY29kZW0AAAAFMTIyMDZtAAAAEHRvdGFsX3BhZ2Vfdmlld3NhCm0AAAANd2ViX3BhZ2VfdHlwZW0AAAAWZGVhbGVycy9kZWFsZXItZGV0YWlsc20AAAASd2ViX3BhZ2VfdHlwZV9mcm9tbQAAAAhob21lcGFnZQ.nvHHdC7NacptxfF_c5V0T7dzpLgEo_6nslJ8p9qXaak; bm_sv=2C280EFBF8D926AE462A76F83DEA5AA6~YAAQvoYUAnuAMPiKAQAALEWkChXCp4+yh3LfI5kwGkGnfhDrKiijJJ9bOk6zRqaCrcqrHrIJUvfQI1K974MTvwv1NkQ2spiVem5G4H4R2uEs29ogepo5i9Bu0G7v0AFVsKFnOlgjaawa03fpC1b8qzc+vgPIbnWRXGsXnOdJXek65hNHysf+sFyNguZtryXgHO1zjTwGPsX11PowBZXeYqR0NKltEJDG9OIwgnEo8v5YJ2gaPSVakD7ZpaZ+U+8=~1; _ga=GA1.1.1704964458.1696688897; _uetsid=bf8b9a60651d11ee8a3211461756d986; _uetvid=bf8baa30651d11ee8cbea3e331cc35c4; _tq_id.TV-09274518-1.6c07=8508f3f072268ee7.1696688900.0.1696690620..; QSI_HistorySession=https%3A%2F%2Fwww.cars.com%2Fvehicledetail%2F2c4e260f-99b7-45c9-9717-abf38d63d7ff%2F~1696689479141%7Chttps%3A%2F%2Fwww.cars.com%2Fdealers%2F187317%2Fdestination-kia%2F%23Reviews~1696690593284%7Chttps%3A%2F%2Fwww.cars.com%2Fdealers%2F~1696690600438%7Chttps%3A%2F%2Fwww.cars.com%2Fdealers%2F187317%2Fdestination-kia%2F%23Reviews~1696690602829%7Chttps%3A%2F%2Fwww.cars.com%2F~1696690619648%7Chttps%3A%2F%2Fwww.cars.com%2Fdealers%2Freviews%2F~1696690620770; smtrrmkr=638322874255987464%5E018b0a8a-05ee-442f-9f6a-bc1ad33a3e3d%5E018b0a8a-05ee-4010-a77c-adff1d21cba3%5E0%5E178.233.76.50; s_lv=1696690624430; s_tslv=1696690624430; _ga_LGBH9NL64W=GS1.1.1696688896.1.1.1696690635.26.0.0; _ga_0SVYF8BFF1=GS1.1.1696688896.1.1.1696690635.0.0.0; s_tp=30139; s_ppv=shopping%2Fsearch-results%2C2%2C2%2C746; _dd_s=rum=0&expire=1696691555863; _abck=9A88A1203CBFC2CDB9A90DBBF2618196~-1~YAAQvoYUAiwGMfiKAQAAx/iyCgqXgdhAPbTq7XBz+Lweg9RSrJhXChjuRXZGRgNNJsY638C05NP9ELq0sIMXCMLTNgTPQZVDbCYgrequQJ57laxyskFaX+b2NwIblzAZabi8v3BgpB/TUKrV0txsCBOdIKxf+UEo5DHIUxTgjs+8/TaaG7P4KyXOjaZALxno43VHnO0nvtaYFMDd3mU64t1SdbJ/6PW3lRkXSfP56mp61lItC6CJQ45lk5Q2KFubAhxQ/a1bssQNOzWYvpmre3QzkTo55m0LXjUDGfEmEAnGlz1MrUN8EIa52T5GDENP7NZAicLxOA663F+teiFEhReOGozRtU2381Oz6YSXsB8WExA1dfdjhU7FMfwFDKtKqesZ+tbVH5GMIHyRBNvO3w3YSEmGxPQ=~0~-1~-1; ak_bmsc=E7F0BE88D5FC808A0E9BAAD044830816~000000000000000000000000000000~YAAQvoYUAi0GMfiKAQAAx/iyChU6Iu7n0LhYYHyUVvuZH/yD3s4lo0jqiWveTRhf6mB6GwulAdkuVwrpuyU5altoapZENi3jRRZtHAJspUG/LQAJCf6RI6toDsNti2u7Nm24vonQGqZ5DRu77ItWGsN6TWp538kct6CkFGt2Dwcq4V0hKo501KeM56tFUMEYvNeNWs//iUo52rIPpGHbz1KfLVTBPA65SwvHyrTWlUnCxZoIktRVbB2N8Kl5Gj8yFkwWRVNRXEIg+uoQUZG34O5LWLxMV5QUc6ZHzONlwKpNGtEcAV8hzc5vJoWSQqJTG1hvmxQiaUrj8wKsF4gWrQpyo+ybCX7+jJFQzwkfNcIrkZDl4pdTFC8IQKVu0bkFoiKJKW/gV+2KMOpChd6Br8HGUgwemIg3rzwuGZkcf9IOCaG4X8tnKzPtP2ISIW8c2/Wye+Dm0jJ9A0PAqX4cKtxgE65FMvBDKiqvNOejDC35gSODv3RP/uXObmYm2ixnHdgIbzvTe93/8U83Iuo7YP2E9Wk=; bm_mi=4DB48FCEA082564929365C96D90117DC~YAAQvoYUAl0BMfiKAQAA1WmyChWRt6VneA24WKBATqTcgeR1c+MjhcRB/PM4S5SRsRsRHUFZaOf+avOgYoQQSjvveCQAiWkr+Vybb8iSWO8jOyHjAZWa8jg/W813XBASRYgcwWfvbtzwXescWAT4uG2zCy6EWVmZ8f6tny/NpzqGn35VPmnRBrVPLwUPr+VG6NVoGr9avKZr1ZSlS7np9GpG5WktvVbc1dfpI8LG3bN5/ej6Scz4yLfLnriGS231JwId9TX9ZoRZUWU2J/TkCxC1LwtbG2P42qIH44/C75ZdX++MveGFIDJZO6jVR9FdzsCgPklFsbZsA1E=~1; bm_sv=2C280EFBF8D926AE462A76F83DEA5AA6~YAAQvoYUAi4GMfiKAQAAx/iyChU8DMxbL4kPIeroqvx9c1HkhIhOGbQ9q0CFOO2JWbt4gl9MknpZSkQHgyt5CkAItLu+6SoJJJNX38US2dxedDzjEFCPmtoUlG34UZ6T/YSkUL02/NifWUo2KhFwq+AP4I02GZhztgUJ/KdnazYofBXW55PDnmYhAHetRNelepWF0tlc3A/SIYbvtxezuoLiueQADTbLMHhhnePZJKYkNsbrG66kyKTmHIIqtoI=~1; bm_sz=36F39175F590614E19CD893EB952708F~YAAQvoYUAoYAMfiKAQAAOD6yChWucbcHGhchyHemC0EWM1YY/DhpMFArXtuxvWuX5glXKeZr4X9PM4tsbVEC8c97FhN/TgfUCOBTiXqiddTTew3Sipn0/bCR1BlurOUgmyRrqlmzwf2uERhEJMVtrr63/10F30D8mh2B2V8vMFPaXla7dxT8nM2yms7mD7MIexy82aBxwP93kxX2C74vIYBhECOJYuo/w/wdx0VhYta6on7uMhGC7rDHO0+OzNCwKLm+lnqfUs7I5f2TiE302GGbWhXCtfHC/z5MZAIk9NZm~4342835~3683894; CARS_logged_in=false; CARS_marketing_source=SFMyNTY.g2gDdAAAAARkAApfX3N0cnVjdF9fZAAjRWxpeGlyLkNhcnNXZWIuUGx1Zy5NYXJrZXRpbmdTb3VyY2VkAAhhZmZfY29kZW0AAAAGc2VvYWZmZAAMY2xpY2tfc291cmNldAAAAABkAAN1dG10AAAAC2QACl9fc3RydWN0X19kACVFbGl4aXIuQ2Fyc1dlYi5TaXRlQWN0aXZpdHkuVVRNUGFyYW1zZAAMdXRtX2NhbXBhaWduZAADbmlsZAAPdXRtX2NhbXBhaWduX2lkZAADbmlsZAALdXRtX2NvbnRlbnRkAANuaWxkABV1dG1fZmlyc3Rfc2Vzc2lvbl9oaXRkAAVmYWxzZWQACnV0bV9tZWRpdW1kAANuaWxkAAx1dG1fbW9kaWZpZWRkAAR0cnVlZAAOdXRtX3NldF9tZXRob2RtAAAAC3JlZmVyZXJfdXJsZAAKdXRtX3NvdXJjZWQAA25pbGQACHV0bV90ZXJtZAADbmlsZAALdXRtX3RydXN0ZWRkAAR0cnVlbgYASfCyCosBYgABUYA.LfRqyl6qj4-emTLjTdmMZw6hsATpoh8pq1fMG8Cra34; CARS_trip_id=e34b8329-2dbb-4d56-919d-b1853d1f2d5d; _cars_web_key=SFMyNTY.g3QAAAANbQAAAAxDQVJTX3RyaXBfaWRtAAAAJGUzNGI4MzI5LTJkYmItNGQ1Ni05MTlkLWIxODUzZDFmMmQ1ZG0AAAALX2NzcmZfdG9rZW5tAAAAGDlfNERjNzhJYlB0Rk05NlMtYkc1Nl9UQm0AAAAQYWxzX3ByaXZhdGVfZGF0YW0AAAC1UVRFeU9FZERUUS5DcVF6ay1GZ3NrNFgwVmJ5eEhVZ3FHbm43ZGRyYzFyaTVucjlQaGV6cXhvY1FIeWFLcDNWQzJUS05Zcy5XWnlpMjVZVkhlM2w3TUFlLjlIc3RzX3hqRWY5RmNaVDk3RTRWalBSbGhzRzdOclZsUGxvNTRVei1nYjU3YkJFMktac2NEV0ZON3lVQ0lwZDJ2Rm5POFEubU9DYkw3bzdndVR0X0syWmNZR2hKd20AAAARZmFjZWJvb2tfZXZlbnRfaWRtAAAAVGRISnBjRjlwWkQxbE16UmlPRE15T1MweVpHSmlMVFJrTlRZdE9URTVaQzFpTVRnMU0yUXhaakprTldRbWRITTlNVFk1TmpZNU1UVTRNVEF3TVE9PW0AAAAYZmFjZWJvb2tfZXZlbnRfaW50ZW50X2lkZAADbmlsbQAAAA9ncmFwaHFsX2FwaV9rZXltAAAAIDVycm1uV1ZsMU1EelBjRW5EdkVwM1B1MTAxSUdYRUdvbQAAAA1pc19zZWFyY2hfYm90ZAAFZmFsc2VtAAAAEGxhc3Rfdmlld2VkX3BhZ2VtAAAAEi9zaG9wcGluZy9yZXN1bHRzL20AAAAPbG9jYWxlX21hcHBpbmdzdAAAAAFtAAAADTE3OC4yMzMuNzYuNTB0AAAACGQACl9fc3RydWN0X19kABVFbGl4aXIuQ2Fyc1dlYi5Mb2NhbGVkAA9jaXR5X3N0YXRlX3NsdWdtAAAACWFsYmFueS1ueWQAGmRlc2lnbmF0ZWRfbWFya2V0X2FyZWFfa2V5bQAAAAphbGJhbnl0cm95ZAAIbGF0aXR1ZGVGQEVWVGCqZMNkAApsb2NhbF96b25lbQAAAAd1bnpvbmVkZAAJbG9uZ2l0dWRlRsBSchT4tYjjZAALbWFya2V0X25hbWVtAAAABmFsYmFueWQACHppcF9jb2RlbQAAAAUxMjIwNm0AAAAOc2VhcmNoX3ppcGNvZGVtAAAABTEyMjA2bQAAABB0b3RhbF9wYWdlX3ZpZXdzYQttAAAADXdlYl9wYWdlX3R5cGVtAAAAF3Nob3BwaW5nL3NlYXJjaC1yZXN1bHRzbQAAABJ3ZWJfcGFnZV90eXBlX2Zyb21tAAAAFmRlYWxlcnMvZGVhbGVyLWRldGFpbHM.q35LEd4bukElSMyhnvFvEA0rws7y8dKVWxpcXHiR6Gs',
  'sec-ch-ua': '"Chromium";v="116", "Not)A;Brand";v="24", "Opera GX";v="102"',
  'sec-ch-ua-mobile': '?0',
  'sec-ch-ua-platform': '"Windows"',
  'sec-fetch-dest': 'document',
  'sec-fetch-mode': 'navigate',
  'sec-fetch-site': 'same-origin',
  'sec-fetch-user': '?1',
  'upgrade-insecure-requests': '1',
  'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36 OPR/102.0.0.0'
}


# Scraper örneğini oluştur ve çalıştır
scraper = CarsScraper(headers)
scraper.run()
