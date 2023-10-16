import pandas as pd
import requests
from bs4 import BeautifulSoup

base_url="https://www.bluediamond.com.tr/urunlerimiz.php?grupID=&urunlist=&satan=&stok=1&indirim=&yeniler=&filtre=&fiyat1=0&fiyat2=1000000&grupID=&kategoriID=100&altkategoriID=&koleksiyonID=&orderby=&orderbytype=desc&type"
ürün_linkleri=[]

for i in range(0,10):
    url=f'{base_url}=&sayfax={i}'
    r = requests.get(url)
    soup = BeautifulSoup(r.content, 'html.parser')
    
    ürün_elementleri=soup.find_all('p',attrs={'class':'detail'})
    for ürün_elementi in ürün_elementleri:
        ürün_elementi = ürün_elementi.find('a')

        ürün_linkleri.append("https://www.bluediamond.com.tr"+ürün_elementi.get("href"))


ürünler=[]

for ürün_linki in ürün_linkleri:
    print(ürün_linki)
    r = requests.get(ürün_linki)
    soup = BeautifulSoup(r.content, 'html.parser')
    isim_element=soup.find('h1',class_='product_name hidden-xs').text.strip()
    fiyat_element=soup.find('span',class_='price').text.strip()
    ürünkodu_elementi=soup.find('span',class_='product_code hidden-xs').text.strip
    resim_elementi=soup.find('img',class_='img-responsive')['src']

    ürün={
        "ÜRÜN ADI":isim_element,
        "FİYATI":fiyat_element,
        "ÜRÜN KODU":ürünkodu_elementi,
        "ÜRÜN FOTOĞRAF LİNKİ":resim_elementi
    }
    ürünler.append(ürün)

df = pd.DataFrame(ürünler)

df.to_excel('bluediamond.xlsx',index=False)