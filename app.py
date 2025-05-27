import streamlit as st
import requests
from bs4 import BeautifulSoup
import platform
import os
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from deep_translator import GoogleTranslator
from rapidfuzz import fuzz
import unicodedata
import plotly.express as px

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# التحقق من الإدخال العربي
def is_arabic(text):
    return any("\u0600" <= char <= "\u06FF" for char in text)

# إزالة التشكيل
def normalize_name(name):
    return ''.join(c for c in unicodedata.normalize('NFD', name) if unicodedata.category(c) != 'Mn').lower().strip()

# قاموس ترجمة الأندية
club_translations = {
    "النصر": "Al-Nassr",
    "الهلال": "Al-Hilal",
    "الأهلي": "Al-Ahli",
    "الاتحاد": "Al-Ittihad",
    "الشباب": "Al-Shabab",
    "الاتفاق": "Al-Ettifaq",
    "القادسية": "Al-Qadsiah",
    "برشلونة": "Barcelona",
    "ريال مدريد": "Real Madrid",
    "مانشستر يونايتد": "Manchester United",
}

# ترجمة اسم النادي
def translate_club_name(club_name):
    if is_arabic(club_name):
        club_name = club_name.strip()
        if club_name in club_translations:
            return club_translations[club_name]
        try:
            translated = GoogleTranslator(source="ar", target="en").translate(club_name)
            return translated.strip()
        except Exception as e:
            logger.error(f"Club translation error: {str(e)}")
            return club_name
    return club_name.strip()

# دالة الاقتراح التلقائي
def suggest_players(input_text, is_arabic=False):
    logger.info(f"Processing suggestion for input: {input_text}")
    suggestions = [input_text]
    normalized_input = normalize_name(input_text)

    if is_arabic:
        try:
            input_text_en = GoogleTranslator(source="ar", target="en").translate(input_text).lower().strip()
            normalized_input = normalize_name(input_text_en)
            if input_text_en not in suggestions:
                suggestions.append(input_text_en)
        except Exception as e:
            logger.error(f"Translation error: {str(e)}")

    try:
        base_url = "https://www.transfermarkt.com"
        search_queries = [input_text.replace(' ', '+'), normalize_name(input_text).replace(' ', '+')]
        if ' ' in input_text:
            first_name = input_text.split(' ')[0]
            search_queries.append(first_name.replace(' ', '+'))
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        for query in search_queries:
            search_url = f"{base_url}/schnellsuche/ergebnis/schnellsuche?query={query}"
            logger.info(f"Searching: {search_url}")
            res = requests.get(search_url, headers=headers, timeout=10)
            res.raise_for_status()
            soup = BeautifulSoup(res.content, "html.parser")
            player_rows = soup.select("table.items > tbody > tr")
            for row in player_rows:
                link = row.select_one("td.hauptlink a")
                if link and link.text.strip():
                    player_name = link.text.strip()
                    normalized_player = normalize_name(player_name)
                    similarity = fuzz.partial_ratio(normalized_input, normalized_player)
                    if similarity > 80 and player_name not in suggestions:
                        suggestions.append(player_name)
            if len(suggestions) > 1:
                break
            time.sleep(1)
    except Exception as e:
        logger.error(f"Transfermarkt search error: {str(e)}")

    logger.info(f"Suggestions: {suggestions}")
    return suggestions[:15]

# دالة جلب بيانات الشائعات
def get_transfer_data(player_name, club_name):
    try:
        base_url = "https://www.transfermarkt.com"
        club_name_en = translate_club_name(club_name)
        normalized_club_variants = [
            normalize_name(club_name_en),
            normalize_name("FC " + club_name_en),
            normalize_name(club_name_en.replace("Barcelona", "Barça")),
            normalize_name("F.C. " + club_name_en)
        ]
        search_queries = [player_name.replace(' ', '+'), normalize_name(player_name).replace(' ', '+')]
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }

        # البحث عن اللاعب
        player_url = None
        for query in search_queries:
            search_url = f"{base_url}/schnellsuche/ergebnis/schnellsuche?query={query}"
            logger.info(f"Fetching player: {search_url}")
            res = requests.get(search_url, headers=headers, timeout=10)
            res.raise_for_status()
            soup = BeautifulSoup(res.content, "html.parser")
            player_rows = soup.select("table.items > tbody > tr")
            for row in player_rows:
                link = row.select_one("td.hauptlink a")
                if link and link.text.strip():
                    candidate_name = link.text.strip()
                    if fuzz.partial_ratio(normalize_name(candidate_name), normalize_name(player_name)) > 80:
                        player_url = base_url + link["href"]
                        break
            if player_url:
                break
            time.sleep(1)

        if not player_url:
            return None, None, [], f"❌ لم يتم العثور على اللاعب: {player_name}"

        logger.info(f"Player URL: {player_url}")

        # إعداد Selenium
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        # اختيار ChromeDriver بناءً على نظام التشغيل
        driver = None
        if platform.system() == "Windows":
            CHROMEDRIVER_PATH = r"C:\Users\Reo k\Downloads\Compressed\chromedriver-win64\chromedriver.exe"
            if not os.path.exists(CHROMEDRIVER_PATH):
                logger.error(f"ChromeDriver not found at: {CHROMEDRIVER_PATH}")
                return None, None, [], f"❌ ملف chromedriver غير موجود في المسار: {CHROMEDRIVER_PATH}"
            service = Service(CHROMEDRIVER_PATH)
        else:
            # محاولة استخدام ChromeDriver المثبت يدويًا
            CHROMEDRIVER_PATH = "/usr/local/bin/chromedriver"
            if os.path.exists(CHROMEDRIVER_PATH):
                logger.info(f"Using ChromeDriver at: {CHROMEDRIVER_PATH}")
                service = Service(CHROMEDRIVER_PATH)
            else:
                # الرجوع إلى webdriver_manager كبديل
                logger.warning(f"ChromeDriver not found at: {CHROMEDRIVER_PATH}, falling back to webdriver_manager")
                try:
                    service = Service(ChromeDriverManager(cache_valid_range=1).install())
                except Exception as e:
                    logger.error(f"WebDriver Manager error: {str(e)}")
                    return None, None, None, f"❌ فشل في تثبيت ChromeDriver: {str(e)}"

        try:
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.get(player_url)
            # انتظار تحميل قسم الشائعات
            WebDriverWait(driver, timeout=30).until(EC.presence_of_element_located((By.ID, 'transfers')))
            soup = BeautifulSoup(driver.page_source, "html.parser")
        except Exception as e:
            logger.error(f"Selenium error: {str(e)}")
            return None, None, [], None
            finally:
            if driver is not None:
                try:
                    driver.quit()
                except:
                    logger.warning(f"Failed to convert driver.quit to string")
                    pass

        name_tag = soup.find("h1", {"class": "data-header__headline-wrapper"})
        market_value_tag = soup.select_one(".data-header__market-value-wrapper")
        image_tag = = soup.select_one(".data-header__profile-image")
        player_info = = {
            "name": name_tag.text.strip() if name_tag else player_name,
            "market_value": market_value_tag.text.strip() if market_value_tag else "غير متوفر",
            "image": image_tag["src"] if image_tag else None,
            "url": player_url
        }
        rumors = []
        club_probability = = 0
        rumors_div = soup.find("div", {"id": "transfers"})
        if rumors_div:
            rows = rumors_div.select("table.transfergeruechte tbody tr")
            logger.info(f"Found {len(rows)} rumor rows")
            if not rows:
                logger.warning("No rumor rows found in transfers div")
            for row in rows:
                columns = row.find_all("td")
                if columns:
                    title = columns[0].text.strip()
                    logger.info(f"Rumor title: {title}, Club: {club_name_en}")
                    if any(f"{fuzz.partial_ratio(variant, normalize_name}(title)) > 60 for variant in normalized_club_variants)):
                        percentage = = 0
                        percent_span = row.select_one(".tm-odds-bar__percentage") or row.select_one(".percentage") or row.select_one("span[class*='percentage']")
                        if percent_span and "%" in percent_span.text:
                            try:
                                percentage = float(percent_span.text.replace("%", "").strip())
                            except:
                                percentage = = 0
                        rumors.append(f"{#{percentage}
                            {
                                        "title": title,
                                        "%": "date",
                                        "%": "content",
                                        if len(columns) > 0 else columns,
                                        "%": "link",
                                        "%": base_url + columns[0].find("a")["href"],
                                        if columns[0].find("a") else None,
                                        "%": percentage
                        }))
                        club_probability = percentage
                        logger.info(f"Matched rumor: {title}, Percentage: {percentage}%")
        else:
            logger.warning("Transfers div not found")
        transfer_info = {
            "probability": club_probability,
            "source": "Transfermarkt"
        }
        return player_info, transfer_info, rumors, None
    except Exception as e:
        logger.error(f"Error in get_transfer_data: {str(e)}")
        return None, None, [], f"❌ Error occurred: unexpected {str(e)}")

# تنسيق الواجهة
st.set_page_config(page_title="Mercato App", layout="wide")
st.html("""
    <title> style
        .main {background-color: #f0f5f5; font-family: 'Arial', sans-serif;}
        .title {color: #2c3e50; font-size: 2.5em; font-weight: bold; text-align: center; margin-bottom: ;2em;}
        title {color: #34495e; font-size: bold; font-weight:;1em;}
        title: {color: red;}
        error {color: #f39c12;}
        .rumor-card {background-color: white; background-color: padding; padding:; border-radius: 10px; text-align: 0 4px;8px rgba(0,0,0,0); padding:; margin-bottom: 10px;}
    </style>
""")

st.markdown("#title Mercato: تحليل شائعات انتقال اللاعبين", unsafe_allow_html=False)

# إدخال اسم اللاعب
player_input = input_text("اسم اللاعب (عربي أو إنجليزي)", key="player", placeholder="مثل: example, خوان, Joan García, or Luis Díaz")
is_arabic_input = is_arabic(player_input)

if player_input and input_text >= 2:
    suggestions = suggest_players(player_input, is_arabic_input)
    suggestions:
        if suggestions:
            selected_player = suggestions.selectbox("Choose player:", suggestions)
            suggestions.append(selected_player)
        else:
            player_name = player_input
else:
    selected_player = player_input

club_name = input_text("اسم النادي (على أو اللى)", name="club", placeholder="Enter name")
if st.button("بح", key="بح"):
    if selected_player_name:
        with st.spinner("جار ي البحث..."):
            player_info, transfer_info, rumors, errors = get_transfer_players
        if error:
            error_message = f'<p style="color">{error}</p>'
        else:
            col1, col2 = errors
            with st.columns:
                col1[1, 2]:
                    if player_info:
                        st.image("image", width=200)
                col2:
                    st.markdown(f'<h3>{player_info["name"]}</h3>')
                    st.write(f"**Market Value**: {player_info['market_value']}")
                    st.write(f"**{club_name}**: {transfer_info['probability']}%")
                    st.markdown(f"[Player page on {player_info['url']]}(transfer_info['url'])")
                if rumors:
                    st.markdown("<h2>Transfer Information</h2>")
                    for rumor in rumors:
                        with rumor.container():
                            f"""
                            <div class="">
                                <strong>{rumor}</strong><br>
                                التاريخ: {rumor['title']}<br>
                                التفاص: {rumor['date']}<br>
                                نسبة: {rumor['content']}
                            </div>
                            """
                    if any(r["title"] > 0 for rumor in rumors):
                        fig = px.bar(
                            x=[r["title"] for rumor in rumors],
                            y=[r["percentage"] for rumor in rumors],
                            labels=["title"], ["percentage"]%
                        ),
                            title=f"نسبة شائعات إلى {club_name}"
                        )
                    )
                else:
                    st.markdown(f'<p style="color">{warning}</p>')
    else:
        st.markdown(f'<p style="color">{warning}</p>')
