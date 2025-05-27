import streamlit as st
import requests
from bs4 import BeautifulSoup
import time
import plotly.express as px
from deep_translator import GoogleTranslator
from rapidfuzz import fuzz
import logging
import unicodedata

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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
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
                    if similarity > 80 and player_name not in suggestions:  # رفع العتبة إلى 80
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
            normalize_name(club_name_en.replace("Barcelona", "Barça"))
        ]
        search_queries = [player_name.replace(' ', '+'), normalize_name(player_name).replace(' ', '+')]
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
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
        res = requests.get(player_url, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.content, "html.parser")
        name_tag = soup.find("h1", {"class": "data-header__headline-wrapper"})
        market_value_tag = soup.select_one(".data-header__market-value-wrapper")
        image_tag = soup.select_one(".data-header__profile-image")
        player_info = {
            "name": name_tag.text.strip() if name_tag else player_name,
            "market_value": market_value_tag.text.strip() if market_value_tag else "غير متوفر",
            "image": image_tag["src"] if image_tag else None,
            "url": player_url
        }
        rumors = []
        club_probability = 0
        rumors_div = soup.find("div", {"id": "transfers"})
        if rumors_div:
            rows = rumors_div.select("table.transfergeruechte tbody tr")
            logger.info(f"Found {len(rows)} rumor rows")
            if not rows:
                logger.warning("No rumor rows found in transfers div")
            for row in rows:
                columns = row.find_all("td")
                if columns:  # إزالة شرط len(columns) >= 5
                    title = columns[0].text.strip()
                    logger.info(f"Rumor title: {title}, Club: {club_name_en}")
                    # مطابقة مرنة لاسم النادي
                    if any(fuzz.partial_ratio(variant, normalize_name(title)) > 60 for variant in normalized_club_variants):
                        percentage = 0
                        percent_span = row.select_one(".tm-odds-bar__percentage") or row.select_one(".percentage") or row.select_one("span[class*='percentage']")
                        if percent_span and "%" in percent_span.text:
                            try:
                                percentage = float(percent_span.text.replace("%", "").strip())
                            except:
                                percentage = 0
                        rumors.append({
                            "title": title,
                            "date": columns[2].text.strip() if len(columns) > 2 else "",
                            "content": columns[4].text.strip() if len(columns) > 4 else "",
                            "link": base_url + columns[0].find("a")["href"] if columns[0].find("a") else None,
                            "percentage": percentage
                        })
                        club_probability = percentage
                        logger.info(f"Matched rumor: {title}, Percentage: {percentage}%")
        else:
            logger.warning("Transfers div not found")
        transfer_info = {
            "probability": club_probability,
            "source": "Transfermarkt"
        }
        return player_info, transfer_info, rumors, None
    except requests.exceptions.RequestException as e:
        return None, None, [], f"❌ خطأ في الاتصال: {str(e)}"
    except Exception as e:
        return None, None, [], f"❌ حدث خطأ غير متوقع: {str(e)}"

# تنسيق الواجهة
st.set_page_config(page_title="Mercato App", layout="wide")
st.html("""
    <style>
        .main {background-color: #f0f5f5; font-family: 'Arial', sans-serif;}
        .title {color: #2c3e50; font-size: 2.5em; font-weight: bold; text-align: center; margin-bottom: 20px;}
        .subheader {color: #34495e; font-size: 1.5em; font-weight: bold;}
        .error {color: #e74c3c;}
        .warning {color: #f39c12;}
        .rumor-card {background-color: white; padding: 15px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); margin-bottom: 10px;}
    </style>
""")

st.markdown("# Mercato: تحليل شائعات انتقال اللاعبين", unsafe_allow_html=False)

# إدخال اسم اللاعب
player_input = st.text_input("اسم اللاعب (عربي أو إنجليزي)", key="player", placeholder="مثل: خوان، جوان، Joan García أو Luis Díaz")
is_arabic_input = is_arabic(player_input)

if player_input and len(player_input) >= 2:
    suggestions = suggest_players(player_input, is_arabic_input)
    if suggestions:
        selected_player = st.selectbox("اختر اللاعب:", suggestions)
    else:
        selected_player = player_input
else:
    selected_player = player_input

club_name = st.text_input("اسم النادي (عربي أو إنجليزي)", key="club", placeholder="مثل: النصر، برشلونة أو Barcelona")

if st.button("بحث", key="search"):
    if selected_player and club_name:
        with st.spinner("جاري البحث..."):
            player_info, transfer_info, rumors, error = get_transfer_data(selected_player, club_name)
        if error:
            st.markdown(f'<p class="error">{error}</p>', unsafe_allow_html=True)
        else:
            col1, col2 = st.columns([1, 2])
            with col1:
                if player_info["image"]:
                    st.image(player_info["image"], width=200)
            with col2:
                st.markdown(f'<h2 class="subheader">{player_info["name"]}</h2>', unsafe_allow_html=True)
                st.write(f"**القيمة السوقية**: {player_info['market_value']}")
                st.write(f"**احتمالية الانتقال إلى {club_name}**: {transfer_info['probability']}%")
                st.write(f"[صفحة اللاعب على Transfermarkt]({player_info['url']})")
            if rumors:
                st.markdown('<h2 class="subheader">الشائعات:</h2>', unsafe_allow_html=True)
                for rumor in rumors:
                    with st.container():
                        st.markdown(
                            f"""
                            <div class="rumor-card">
                                <strong>{rumor['title']}</strong><br>
                                التاريخ: {rumor['date']}<br>
                                التفاصيل: {rumor['content']}<br>
                                نسبة الاحتمالية: {rumor['percentage']}%{'<br><a href="' + rumor['link'] + '">الرابط</a>' if rumor['link'] else ''}
                            </div>
                            """, unsafe_allow_html=True)
                if any(r["percentage"] > 0 for r in rumors):
                    fig = px.bar(
                        x=[r["title"] for r in rumors],
                        y=[r["percentage"] for r in rumors],
                        labels={"x": "الشائعة", "y": "النسبة المئوية (%)"},
                        title=f"نسب شائعات الانتقال إلى {club_name}"
                    )
                    st.plotly_chart(fig)
            else:
                st.markdown(f'<p class="warning">لا توجد شائعات متعلقة بنادي {club_name} لهذا اللاعب.</p>', unsafe_allow_html=True)
    else:
        st.markdown('<p class="warning">يرجى إدخال اسم اللاعب والنادي.</p>', unsafe_allow_html=True)
