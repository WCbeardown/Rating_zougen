import streamlit as st
import re
import pandas as pd
import requests
from bs4 import BeautifulSoup
import datetime
from urllib.parse import urljoin

st.title("羽曳野大会レーティング増減計算アプリ")
st.caption(
    "注意事項（言い訳）：\n"
    "Googleの文字認識の精度によるので、写真の解像度と文字認識の程度によっては全然異なる結果になることがあります。\n"
    "苦情は受け付けませんので、悪しからず。\n"
    "レイティングの結果が出てから使ってください。"
)
# --- 1. ユーザー入力エリア ---
st.header("ステップ1: 大会データを貼り付け")
text_input = st.text_area(
    "レイティングの参加者全体が移っている写真を用意する。\n"
    "Googleアプリを起動して、カメラマーク「Googleレンズ」を選択\n"
    "シャッターの横にある画像選択マークを選んで、先ほどの写真を選択\n"
    "「テキストを選択」を選んで、選択されたテキストを「コピー」\n"
    "このページに戻ってきて、以下の枠に「ペースト」してください。",
    height=400
)

# --- 2. 羽曳野レーティング回数入力 ---
st.header("ステップ2: 羽曳野レーティングの回数")
kaisu_input = st.number_input(
    "第何回の大会かを入力してください（例: 293）",
    min_value=1,
    value=293,
    step=1
)

# --- 3. ボタン押下で処理 ---
if st.button("増減表示"):
    if not text_input.strip():
        st.warning("大会データが入力されていません")
    else:
        st.info("大会データ解析中…")

        # ----- 第1セル処理（大会データ抽出） -----
        text = text_input.replace('\u3000', ' ').replace('\ufeff', '').replace('\xa0', ' ')
        lines_raw = [ln.strip() for ln in text.splitlines()]
        lines = [ln for ln in lines_raw if ln != ""]

        def is_heading(s):
            headers = ['参加者', '第', '大会', 'グループ', 'ブロック', 'コート',
                       '会員番号', '氏名', 'R', 'Z=', '* =', '上位希望者', '回', '合番号']
            for h in headers:
                if h in s:
                    return True
            if re.fullmatch(r"[\|\(\)\-\*]+", s):
                return True
            if re.search(r'\d{4}/\d{1,2}/\d{1,2}', s) or ('年' in s and '月' in s):
                return True
            return False

        def is_name_candidate(s):
            if is_heading(s): return False
            if re.search(r'\d{2,4}年', s) or '月' in s: return False
            digits = sum(ch.isdigit() for ch in s)
            if len(s) > 0 and (digits / len(s)) > 0.5:
                return False
            if re.search(r'[\u3040-\u30ff\u4e00-\u9fffA-Za-z]', s):
                return True
            return False

        member_id_regex = re.compile(r'\d{6,8}')
        rating_regex = re.compile(r'(?<!\d)(\d{4})(?!\d)')

        records = []
        seen_ids = set()
        N = len(lines)
        i = 0
        while i < N:
            line = lines[i]
            ids_in_line = member_id_regex.findall(line)
            if ids_in_line:
                search_pos = 0
                for member_id in ids_in_line:
                    pos = line.find(member_id, search_pos)
                    search_pos = pos + len(member_id)
                    name = None
                    rating_before = None
                    remainder = line[pos+len(member_id):].strip()

                    if remainder:
                        m_r = rating_regex.search(remainder)
                        if m_r:
                            rating_before = int(m_r.group(1))
                            name_candidate = remainder[:m_r.start()].strip()
                            if name_candidate and is_name_candidate(name_candidate):
                                name = name_candidate
                        else:
                            if is_name_candidate(remainder):
                                name = remainder

                    if not name:
                        for j in range(i+1, min(i+6, N)):
                            s = lines[j]
                            if is_heading(s): continue
                            m = rating_regex.search(s)
                            if m:
                                if re.fullmatch(r'\d{4}', s):
                                    rating_before = int(s)
                                    continue
                                else:
                                    name_candidate = s[:m.start()].strip()
                                    if name_candidate and is_name_candidate(name_candidate):
                                        name = name_candidate
                                        rating_before = int(m.group(1))
                                        break
                            if is_name_candidate(s):
                                name = s
                                m2 = rating_regex.search(s)
                                if m2:
                                    rating_before = int(m2.group(1))
                                    name = s[:m2.start()].strip()
                                break

                    if rating_before is None:
                        for j in range(i, min(i+8, N)):
                            s = lines[j]
                            m = rating_regex.search(s)
                            if m:
                                rating_before = int(m.group(1))
                                break
                            if '初' in s:
                                rating_before = None
                                break

                    if name:
                        m = member_id_regex.search(name)
                        if m:
                            name = name[:m.start()].strip()
                        name = re.sub(r'\b\d+\b$', '', name).strip()
                        name = rating_regex.sub('', name).strip()
                        name = re.sub(r'\s+', ' ', name).strip()
                        if name == '': name = None

                    if member_id in seen_ids:
                        continue
                    seen_ids.add(member_id)
                    records.append({'会員番号': member_id, '氏名': name, '大会前レーティング': rating_before})
            i += 1

        df_before = pd.DataFrame(records)

        # ----- 第2セル処理（羽曳野レーティング読み込み） -----
        import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

def get_habikino_sheet_url(kaisu):
    """羽曳野レイティングの sheet001.htm のURLを返す"""
    base_url = "https://www.cbii.kutc.kansai-u.ac.jp/tt_rating/habikino.html"

    headers = {"User-Agent": "Mozilla/5.0"}  # ブラウザっぽくする
    max_retry = 3

    # リトライ付きで取得
    for attempt in range(max_retry):
        try:
            res = requests.get(base_url, headers=headers, timeout=10)
            res.raise_for_status()
            break
        except requests.exceptions.RequestException as e:
            print(f"接続失敗: {e}, {attempt+1}/{max_retry} 回目")
            time.sleep(3)
    else:
        print("3回試しましたが接続できませんでした")
        return None

    res.encoding = "shift_jis"
    soup = BeautifulSoup(res.text, "html.parser")

    for a in soup.find_all("a"):
        text = a.get_text()
        if f"{kaisu}" in text:
            href = a["href"].replace("./", "")
            href = urljoin(base_url, href)

            # .htm ページから <frame> を探す
            for attempt in range(max_retry):
                try:
                    sub = requests.get(href, headers=headers, timeout=10)
                    sub.raise_for_status()
                    break
                except requests.exceptions.RequestException as e:
                    print(f"フレームページ接続失敗: {e}, {attempt+1}/{max_retry} 回目")
                    time.sleep(3)
            else:
                print(f"{kaisu}回のフレームページに接続できませんでした")
                return None

            sub.encoding = "shift_jis"
            sub_soup = BeautifulSoup(sub.text, "html.parser")
            frame = sub_soup.find("frame") or sub_soup.find("iframe")
            if frame and frame.get("src"):
                return urljoin(href, frame["src"])
            return href
    return None


def load_habikino(kaisu):
            url = get_habikino_sheet_url(kaisu)
            if not url:
                st.error(f"第{kaisu}回が見つかりません")
                return None
            data = pd.read_html(url, encoding="shift_jis")
            df = data[0]
            title = df.iat[1, 1]
            if "ダイ" in title:
                title = title.split("ダイ")[1]
            else:
                title = title.split("第")[1]
            kaisu = int(title.split("回")[0])
            if "カイ" in title:
                place = title.split("カイ")[1].split("レイティング")[0]
                hiduke = title.split("カイ")[1].split("レイティング")[1].split("（")[1].split("）")[0].split(".")
            else:
                place = title.split("回")[1].split("レイティング")[0]
                hiduke = title.split("回")[1].split("レイティング")[1].split("（")[1].split("）")[0].split(".")
            hiduke = [int(x) for x in hiduke]
            kaisaibi = datetime.date(hiduke[0], hiduke[1], hiduke[2])
            df = df.dropna(how="all")
            dft = df.transpose()
            dft = dft.dropna(thresh=3)
            df = dft.transpose()
            df = df.drop(df.index[0:1]).reset_index(drop=True)

            membership = []
            rating = []
            for i in range(len(df.columns)):
                temp = df.iloc[:, i].dropna().tolist()
                try:
                    temp = [int(x) for x in temp]
                except ValueError:
                    temp = temp[1:]
                    temp = [int(x) for x in temp]
                if i % 2:
                    rating.extend(temp)
                else:
                    membership.extend(temp)

            rating_data = pd.DataFrame({
                "場所": [place]*len(membership),
                "回": [kaisu]*len(membership),
                "日付": [kaisaibi]*len(membership),
                "会員番号": membership,
                "大会後レーティング": rating,
            })
            return rating_data

df_after = load_habikino(kaisu_input)
if df_after is None:
            st.stop()

        # ----- 第3セル処理（増減計算） -----
def normalize_member_id(x):
            x_str = str(x)
            if len(x_str) == 8:
                x_str = x_str[1:]
            return int(x_str)

df_before["会員番号"] = df_before["会員番号"].apply(normalize_member_id)
df_after["会員番号"] = df_after["会員番号"].apply(normalize_member_id)

df_merge = pd.merge(
            df_before[["会員番号", "氏名", "大会前レーティング"]],
            df_after[["会員番号", "大会後レーティング"]],
            on="会員番号",
            how="outer"
        )
df_merge["増減"] = df_merge["大会後レーティング"] - df_merge["大会前レーティング"]
df_merge["氏名"] = df_merge["氏名"].fillna("")
df_merge = df_merge.sort_values("会員番号").reset_index(drop=True)

st.subheader("大会レーティング増減結果")
st.dataframe(df_merge)
