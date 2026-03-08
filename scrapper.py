import requests
from bs4 import BeautifulSoup

def get_price(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-IN,en;q=0.9"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, "html.parser")

        # TITLE
        title_tag = soup.find("span", id="productTitle")
        if title_tag:
            title = title_tag.get_text(strip=True)
        else:
            return None, None

        # PRICE (try multiple selectors)
        price = None

        # Most common format
        price_tag = soup.find("span", class_="a-price-whole")
        if price_tag:
            price = price_tag.get_text().replace(",", "").strip()

        # Fallback: priceblock
        if not price:
            price_tag = soup.find("span", id="priceblock_ourprice")
            if price_tag:
                price = price_tag.get_text().replace("₹", "").replace(",", "").strip()

        # Fallback: deal price
        if not price:
            price_tag = soup.find("span", id="priceblock_dealprice")
            if price_tag:
                price = price_tag.get_text().replace("₹", "").replace(",", "").strip()

        if not price:
            return None, None

        # Convert to integer
        price_int = int(float(price))
        return title, price_int

    except Exception as e:
        print("Scraper error:", e)
        return None, None