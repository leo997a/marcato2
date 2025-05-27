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

# إزالة التشكيل من الأسماء (مثل "í" في Díaz)
def normalize_name(name):
    return ''.join(c for c in unicodedata.normalize('NFD', name) if unicodedata.category(c) != 'Mn').lower().strip()

# قاموس لترجمة أسماء الأندية العربية إلى الإنجليزية
club_translations = {
    "النصر": "Al-Nassr",
    "الهلال": "Al-Hilal",
    "الأهلي": "Al-Ahli",
    "الاتحاد": "Al-Ittihad",
    "الشباب": "Al-Shabab",
    "الاتفاق": "Al-Ettifaq",
    "القادسية": "Al-Qadsiah",
    # أضف المزيد من الأندية حسب الحاجة
}

# ترجمة اسم النادي إذا كان بالعربية
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

# دالة الاقتراح التلقائي باستخدام Transfermarkt
def suggest_players(input_text, is_arabic=False):
    logger.info(f"Processing suggestion for input: {input_text}")
    suggestions = [input_text]  # إضافة الإدخال كخيار افتراضي
    normalized_input = normalize_name(input_text)

    # ترجمة الإدخال العربي إلى الإنجليزية إذا لزم الأمر
    if is_arabic:
        try:
            input_text_en = GoogleTranslator(source="ar", target="en").translate(input_text).lower().strip()
            normalized_input = normalize_name(input_text_en)
            suggestions.append(input_text_en)
        except Exception as e:
            logger.error(f"Translation error: {str(e)}")

    try:
        base_url = "https://www.transfermarkt.com"
        search_url = f"{base_url}/schnellsuche/ergebnis/schnellsuche?query={input_text.replace(' ', '+')}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        res = requests.get(search_url, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.content, "html.parser")
        player_links = soup.select("a.spielprofil_tooltip")
        for link in player_links[:10]:  # الحد الأقصى 10 اقتراحات
            player_name = link.text.strip()
            if player_name:
                normalized_player = normalize_name(player_name)
                similarity = fuzz.partial_ratio(normalized_input, normalized_player)
                if similarity > 70 and player_name not in suggestions:
                    suggestions.append(player_name)
    except Exception as e:
        logger.error(f"Transfermarkt search error: {str(e)}")

    logger.info(f"Suggestions: {suggestions}")
    return suggestions[:10]

# دالة جلب بيانات الشائعات من Transfermarkt
def get_transfer_data(player_name, club_name):
    try:
        base_url = "https://www.transfermarkt.com"
        # ترجمة اسم النادي إذا كان عربيًا
        club_name_en = translate_club_name(club_name)
        # إزالة التشكيل من اسم اللاعب
        search_name = normalize_name(player_name).replace(' ', '+')
        search_url = f"{base_url}/schnellsuche/ergebnis/schnellsuche?query={search_name}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        res = requests.get(search_url, headers=headers, timeout=10)
        res.raise_for_status()
        time.sleep(1)
        soup = BeautifulSoup(res.content, "html.parser")
        # تحسين البحث عن اللاعب
        player_links = soup.select("a.spielprofil_tooltip")
        player_url = None
        for link in player_links:
            if normalize_name(link.text.strip()) == normalize_name(player_name):
                player_url = base_url + link["href"]
                break
        if not player_url:
            # محاولة ثانية باستخدام الاسم الأصلي
            search_url = f"{base_url}/schnellsuche/ergebnis/schnellsuche?query={player_name.replace(' ', '+')}"
            res = requests.get(search_url, headers=headers, timeout=10)
            res.raise_for_status()
            soup = BeautifulSoup(res.content, "html.parser")
            player_links = soup.select("a.spielprofil_tooltip")
            for link in player_links:
                if normalize_name(link.text.strip()) == normalize_name(player_name):
                    player_url = base_url + link["href"]
                    break
        if not player_url:
            return None, None, [], "❌ لم يتم العثور على اللاعب."

        res = requests.get(player_url, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.content, "html.parser")
        name_tag = soup.find("h1", {"itemprop": "name"})
        market_value_tag = soup.select_one(".right-td")
        image_tag = soup.select_one(".dataBild img")
        player_info = {
            "name": name_tag.text.strip() if name_tag else player_name,
            "market_value": market_value_tag.text.strip() if market_value_tag else "غير متوفر",
            "image": image_tag["src"] if image_tag else None,
            "url": player_url
        }
        rumors = []
        max_probability = 0
        rumors_div = soup.find("div", {"id": "transfers"})
        if rumors_div:
            rows = rumors_div.select("table.transfergeruechte tbody tr")
            for row in rows:
                columns = row.find_all("td")
                if len(columns) >= 5:
                    title = columns[0].text.strip()
                    if normalize_name(club_name_en).lower() in normalize_name(title).lower():
                        percentage = 0
                        percent_span = row.select_one("div.bar-graph span")
                        if percent_span and "%" in percent_span.text:
                            try:
                                percentage = int(percent_span.text.replace("%", "").strip())
                            except:
                                percentage = 0
                        rumors.append({
                            "title": title,
                            "market_value": columns[1].text.strip(),
                            "date": columns[2].text.strip(),
                            "content": columns[4].text.strip(),
                            "link": base_url + columns[0].find("a")["href"] if columns[0].find("a") else None,
                            "percentage": percentage
                        })
                        max_probability = max(max_probability, percentage)
        transfer_info = {
            "probability": max_probability if max_probability > 0 else min(len(rumors) * 25, 100),
            "source": "Transfermarkt"
        }
        return player_info, transfer_info, rumors, None
    except requests.RequestException as e:
        return None, None, [], f"❌ خطأ في الاتصال: {str(e)}"
    except Exception as e:
        return None, None, [], f"❌ حدث خطأ غير متوقع: {str(e)}"

# تنسيق الواجهة
st.set_page_config(page_title="Mercato App", layout="wide")
st.markdown("""
    <style>
    .main {background-color: #f5f5f5; font-family: 'Arial', sans-serif;}
    .title {color: #2c3e50; font-size: 2.5em; text-align: center; margin-bottom: 20px;}
    .subheader {color: #34495e; font-size: 1.5em;}
    .error {color: #e74c3c;}
    .warning {color: #f39c12;}
    .rumor-card {background-color: white; padding: 15px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); margin-bottom: 10px;}
    </style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="title">Mercato: تحليل شائعات انتقال اللاعبين</h1>', unsafe_allow_html=True)

# إدخال اسم اللاعب
player_input = st.text_input("اسم اللاعب (عربي أو إنجليزي)", key="player", placeholder="مثل: لويس دياز أو Luis Díaz")
is_arabic_input = is_arabic(player_input)

if player_input and len(player_input) >= 2:
    suggestions = suggest_players(player_input, is_arabic_input)
    if suggestions:
        selected_player = st.selectbox("اختر اللاعب:", suggestions)
    else:
        selected_player = player_input
else:
    selected_player = player_input

club_name = st.text_input("اسم النادي (عربي أو إنجليزي)", key="club", placeholder="مثل: النصر أو Al-Nassr")

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
                st.write(f"**احتمالية الانتقال**: {transfer_info['probability']}%")
                st.write(f"[صفحة اللاعب على Transfermarkt]({player_info['url']})")
            if rumors:
                st.markdown('<h2 class="subheader">الشائعات:</h2>', unsafe_allow_html=True)
                for rumor in rumors:
                    with st.container():
                        st.markdown(
                            f"""
                            <div class="rumor-card">
                                <strong>{rumor['title']}</strong><br>
                                القيمة السوقية: {rumor['market_value']}<br>
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
                        title="نسب الشائعات"
                    )
                    st.plotly_chart(fig)
            else:
                st.markdown(f'<p class="warning">لا توجد شائعات متعلقة بنادي {club_name}.</p>', unsafe_allow_html=True)
    else:
        st.markdown('<p class="warning">يرجى إدخال اسم اللاعب والنادي.</p>', unsafe_allow_html=True)
