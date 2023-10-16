from selenium import webdriver
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import csv

base_url = "https://www.cars.com/sitemap/city-listings/"

# Ana driver ile sayfayı aç
main_driver = webdriver.Firefox()
main_driver.get(base_url)
input()
soup = BeautifulSoup(main_driver.page_source, 'html.parser')
city_links = ['https://www.cars.com'+a['href'] for a in soup.find_all('a', attrs={"data-linkname": "shopping-city"})]
main_driver.quit()

# 5 adet tarayıcı başlat
drivers = [webdriver.Firefox() for _ in range(5)]
semaphore = threading.Semaphore(5)  # Aynı anda maksimum 5 tarayıcının çalışmasını sağlar

# Zip değerini belirli bir link için al
def get_zip_from_link(link):
    semaphore.acquire()  # Tarayıcı alındığında Semaphore'u kilitler
    driver = drivers.pop()
    driver.get(link)
    time.sleep(3)  # Sayfanın tamamen yüklenmesini beklemek için

    zip_input = driver.find_element(By.ID, 'zip-input')
    zip_value = zip_input.get_attribute('value')
    drivers.append(driver)  # Tarayıcıyı geri listeye ekler
    semaphore.release()  # Tarayıcı bırakıldığında Semaphore'un kilidini açar
    return (link, zip_value)

with ThreadPoolExecutor(max_workers=5) as executor:
    results = list(executor.map(get_zip_from_link, city_links))

# Tarayıcıları kapat
for driver in drivers:
    driver.quit()

# Sonuçları CSV dosyasına kaydet
with open('results.csv', 'w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(["URL", "ZIP Value"])  # Başlık satırı
    writer.writerows(results)
