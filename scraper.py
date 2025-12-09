import requests
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime

# ---------- KONFIGURACJA ----------

# ID arkusza z URL, np.:
# https://docs.google.com/spreadsheets/d/XXXXXX/edit#gid=0
SHEET_ID = "1RpGc5TAPyvwcm7wIx2pGaT6el_-250BKEuO-XZKgXms"
print("SHEET_ID =", SHEET_ID)


# Zakres: zakładka "Kraków", od kolumny A do np. AZ, wiersze 1–999
SHEET_RANGE = "Kraków!A1:AZ999"  # jak masz więcej kolumn/wierszy, możesz rozszerzyć

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
CREDS_FILE = "service_account.json"  # plik z kluczem konta serwisowego


# ---------- OBSŁUGA GOOGLE SHEETS ----------

def get_sheet_service():
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    service = build("sheets", "v4", credentials=creds)
    return service


def read_sheet(service):
    sheet = service.spreadsheets()
    result = sheet.values().get(
        spreadsheetId=SHEET_ID,
        range=SHEET_RANGE
    ).execute()
    values = result.get("values", [])
    return values


def write_cell(service, row_idx, col_idx, value):
    """
    row_idx, col_idx – indeksy 0-based względem całego arkusza
    (czyli row_idx=0 -> wiersz 1 w Google Sheets)
    """

    def col_letter(idx: int) -> str:
        """
        Zamiana indeksu 0-based na literę kolumny: 0 -> A, 25 -> Z, 26 -> AA itd.
        """
        idx += 1  # przejście na 1-based
        letters = ""
        while idx > 0:
            idx, remainder = divmod(idx - 1, 26)
            letters = chr(65 + remainder) + letters
        return letters

    col_letter_str = col_letter(col_idx)
    # +1 bo w Sheets wiersze są 1-based
    a1_notation = f"Kraków!{col_letter_str}{row_idx + 1}"

    sheet = service.spreadsheets()
    body = {"values": [[value]]}
    sheet.values().update(
        spreadsheetId=SHEET_ID,
        range=a1_notation,
        valueInputOption="RAW",
        body=body
    ).execute()


# ---------- SCRAPOWANIE ----------

def scrape_price(url: str, css_selector: str):
    """
    Pobiera stronę, znajduje element po selektorze CSS
    i wyciąga z niego pierwszą sensowną liczbę (np. "119 zł/mies" -> 119).
    """
    if not url or not css_selector:
        return None

    resp = requests.get(url, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    el = soup.select_one(css_selector)
    if el is None:
        return None

    text = el.get_text(" ", strip=True)

    # Proste wyciągnięcie liczby z tekstu
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None

    try:
        return int(digits)
    except ValueError:
        return None


def main():
    service = get_sheet_service()
    rows = read_sheet(service)

    if not rows:
        print("Brak danych w arkuszu.")
        return

    header = rows[0]
    data_rows = rows[1:]

    # mapowanie: nazwa kolumny -> indeks
    col = {name: i for i, name in enumerate(header)}

    # Dopasowanie do Twoich nagłówków:
    # - "Miesięczny"
    # - "Cennik_URL"
    # - "CSS_Miesięczny"
    # - "Last_Scraped"
    try:
        idx_miesieczny = col["Miesięczny"]
        idx_cennik_url = col["Cennik_URL"]
        idx_css_miesieczny = col["CSS_Miesięczny"]
        idx_last_scraped = col["Last_Scraped"]
    except KeyError as e:
        print("Brakuje jednej z wymaganych kolumn w nagłówku:", e)
        print("Upewnij się, że masz dokładnie takie nazwy kolumn:")
        print("Miesięczny, Cennik_URL, CSS_Miesięczny, Last_Scraped")
        return

    for i, row in enumerate(data_rows, start=1):  # start=1, bo 0 to nagłówki
        # funkcja pomocnicza: bezpiecznie pobiera wartość z wiersza
        def safe_get(idx):
            return row[idx] if idx < len(row) else ""

        url = safe_get(idx_cennik_url)
        css = safe_get(idx_css_miesieczny)

        if not url or not css:
            continue  # nic do scrapowania dla tej siłowni

        print(f"[wiersz {i+1}] Scrapuję: {url}")

        try:
            price = scrape_price(url, css)
            if price is None:
                print("  ✖ Nie udało się znaleźć ceny.")
                continue

            print(f"  ✔ Znaleziona cena miesięczna: {price} zł")

            # aktualizacja kolumny "Miesięczny"
            write_cell(service, i, idx_miesieczny, price)

            # aktualizacja kolumny "Last_Scraped"
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            write_cell(service, i, idx_last_scraped, now_str)

        except Exception as e:
            print(f"  ⚠ Błąd przy wierszu {i+1}: {e}")


if __name__ == "__main__":
    main()
