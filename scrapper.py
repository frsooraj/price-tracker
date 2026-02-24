import requests
from bs4 import BeautifulSoup

def get_price(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        page = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(page.content, "html.parser")
        # Extracting based on your Page 7 flow
        name = soup.find("span", id="productTitle").text.strip()
        price_text = soup.find("span", class_="a-price-whole").text.replace(',', '')
        return name, float(price_text)
    except Exception as e:
        print(f"Scraping error: {e}")
        return None, None