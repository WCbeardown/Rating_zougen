# main.py
import streamlit as st
import re
import pandas as pd
import requests
from bs4 import BeautifulSoup
import datetime
from urllib.parse import urljoin
import time

st.set_page_config(page_title="羽曳野大会レーティング増減計算", layout="wide")
st.title("羽曳野大会レーティング増減計算アプリ")
st.caption(
    "注意事項（言い訳）：Googleの文字認識の精度によるので、写真の解像度と文字認識の程度によっては全然異なる結果になることがあります。苦情は受け付けませんので、悪しからず。レイティングの結果が出てから使ってください。"
)

# ---------- 説明（左: 文、右: 図） ----------
st.header("使い方（左：説明 / 右：図）")
steps = [
    ("用意する写真", "大会参加者全体が映った写真を準備してください。大会番号（第＊回）も写っていること。これがないと始まりません。", "image1.jpg"),
    ("Googleアプリを開く", "Googleアプリを起動し、検索バーの右のカメラアイコン（Googleレンズ）をタップ。", "image2.jpg"),
    ("画像選択", "シャッター横の画像選択マークから、用意した写真を選択します。", "image3.jpg"),
    ("テキスト選択", "抽出されたテキストで「テキストを選択」を押して必要な範囲を選択。", "image4.jpg"),
    ("コピー", "選択したテキストをコピーします（すべてコピー推奨）。", "image5.jpg"),
    ("ペースト", "このページに戻り、下の枠に貼り付けて「増減表示」ボタンを押してください。", "image6.jpg"),
]
for title, desc, img in steps:
    col_l, col_r = st.columns([2, 1])
    with col_l:
        st.subheader(title)
        st.write(desc)
    with col_r:
        try:
            st.image(img, use_container_width=True)
        except Exception:
            st.write("(画像ファイルが見つかりません)")

st.divider()

# ---------- 入力欄 ----------
st.header("OCRで取得したテキストを貼り付け")
text_input = st.text_area(
    "ここにコピーしたテキストを貼り付けてください（例：第294回羽曳野RS大会 ...）。",
    height=360
)

# ---------- ヘルパー関数 ----------
def extract_tournament_number(text: str):
    """例: '第294回羽曳野RS大会' から 294 を取り出す（int）。"""
    if not text:
        return None
    m = re.search(r"第\s*(\d+)\s*回\s*羽曳野RS大会", text)
    if m:
        return int(m.group(1))
    # 漢数字や別表記が必要ならここで拡張
    return None

def normalize_member_id(x):
    """会員番号を整数に（8桁なら先頭1文字を削る例）"""
    x_str = str(x).strip()
    # 空文字等はそのままNaN扱いさせる
    if x_str == "" or x_str.lower() == "nan":
        return None
    if len(x_str) == 8:
        x_str = x_str[1:]
    # 数字以外混入する可能性を除去
    x_str = re.sub(r"\D", "", x_str)
    if x_str == "":
        return None
    return int(x_str)

def is_heading(s: str):
    headers = ['参加者', '第', '大会', 'グループ', 'ブロック', 'コート',
               '会員番号', '氏名', 'R', 'Z=', '* =', '上位希望者', '回', '合番号']
    if any(h in s for h in headers):
        return True
    if re.fullmatch(r"[\|\(\)\-\*]+", s):
        return True
    if re.search(r'\d{4}/\d{1,2}/\d{1,2}', s) or ('年' in s and '月' in s):
        return True
    return False

def is_name_candidate(s: str):
    if is_heading(s):
        return False
    if re.search(r'\d{2,4}年', s) or '月' in s:
        return False
    digits = sum(ch.isdigit() for ch in s)
    if len(s) > 0 and (digits / len(s)) > 0.5:
        return False
    if re.search(r'[\u3040-\u30ff\u4e00-\u9fffA-Za-z]', s):
        return True
    return False

def parse_records_from_text(text: str):
    """貼り付けテキストから records リストを作る（会員番号, 氏名, 大会前レーティング）"""
    text = text.replace('\u3000', ' ').replace('\ufeff', '').replace('\xa0', ' ')
    lines_raw = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines_raw if ln != ""]

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
                        if is_heading(s): 
                            continue
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
                    name = re.sub(r'\b\d+\b$', '', (name or "")).strip()
                    name = rating_regex.sub('', name).strip()
                    name = re.sub(r'\s+', ' ', name).strip()
                    if name == '':
                        name = None

                if member_id in seen_ids:
                    continue
                seen_ids.add(member_id)
                records.append({
                    '会員番号': member_id,
                    '氏名': name,
                    '大会前レーティング': rating_before
                })
        i += 1

    return pd.DataFrame(records)

# ---------- 外部サイト取得関数（あなたが指摘した形式を使用） ----------
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
            # Cloud 環境ではエラーが出る場合があるのでログに残す
            st.write(f"base page 接続失敗: {e} （{attempt+1}/{max_retry}）")
            time.sleep(1)
    else:
        st.write("3回試しましたが接続できませんでした（base page）")
        return None

    res.encoding = "shift_jis"
    soup = BeautifulSoup(res.text, "html.parser")

    for a in soup.find_all("a"):
        text = a.get_text()
        # リンクテキストに回数が含まれるものを探す（柔軟にマッチ）
        if f"{kaisu}" in text:
            href = a.get("href", "").replace("./", "")
            href = urljoin(base_url, href)

            # .htm ページから <frame> を探す
            for attempt in range(max_retry):
                try:
                    sub = requests.get(href, headers=headers, timeout=10)
                    sub.raise_for_status()
                    break
                except requests.exceptions.RequestException as e:
                    st.write(f"フレームページ接続失敗: {e} （{attempt+1}/{max_retry}）")
                    time.sleep(1)
            else:
                st.write(f"{kaisu}回のフレームページに接続できませんでした")
                return None

            sub.encoding = "shift_jis"
            sub_soup = BeautifulSoup(sub.text, "html.parser")
            frame = sub_soup.find("frame") or sub_soup.find("iframe")
            if frame and frame.get("src"):
                return urljoin(href, frame["src"])
            return href
    return None

def load_habikino(kaisu):
    """指定回数の羽曳野レーティングをDataFrameに変換"""
    sheet_url = get_habikino_sheet_url(kaisu)
    if not sheet_url:
        st.error(f"第{kaisu}回が見つかりません（サイトにアクセスできないか、該当リンクなし）")
        return None

    st.write(f"読み込み先 URL: {sheet_url}")
    try:
        tables = pd.read_html(sheet_url, encoding="shift_jis")
    except Exception as e:
        st.error(f"pd.read_html でエラー: {e}")
        return None

    if len(tables) == 0:
        st.error("テーブルが見つかりませんでした")
        return None

    df = tables[0]

    # タイトルから回数・場所・日付を抽出（既存ロジックを踏襲）
    try:
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
    except Exception as e:
        st.write("タイトル解析に失敗しましたが続行します:", e)
        place = ""
        kaisaibi = None

    # データ整形（既存のやり方）
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

    rating_data = pd.DataFrame(
        {
            "場所": [place] * len(membership),
            "回": [kaisu] * len(membership),
            "日付": [kaisaibi] * len(membership),
            "会員番号": membership,
            "大会後レーティング": rating,
        }
    )

    return rating_data

# ---------- ボタン処理 ----------
if st.button("増減表示"):
    if not text_input or text_input.strip() == "":
        st.warning("大会データが入力されていません。")
        st.stop()

    with st.spinner("テキスト解析中..."):
        # 大会番号抽出
        kaisu = extract_tournament_number(text_input)
        if kaisu is None:
            st.error("テキスト中から大会番号（例: 第294回羽曳野RS大会）を検出できませんでした。")
            st.stop()
        st.success(f"検出された大会番号: 第{kaisu}回")

        # テキスト → df_before
        df_before = parse_records_from_text(text_input)
        st.write(f"抽出レコード数: {len(df_before)} 件 (名前欠損: {df_before['氏名'].isnull().sum() if not df_before.empty else 0})")
        if df_before.empty:
            st.warning("参加者データが抽出できませんでした。貼り付けテキストを確認してください。")
            st.stop()

    # 外部サイトから df_after を取得（ネットワーク処理はスピナーを表示）
    with st.spinner("羽曳野サイトから大会データを取得中..."):
        df_after = load_habikino(kaisu)
        if df_after is None:
            st.error("羽曳野の大会ページが取得できませんでした。公開環境からアクセス制限されている可能性があります。")
            st.stop()

    # 正規化
    df_before["会員番号"] = df_before["会員番号"].apply(lambda x: normalize_member_id(x) if pd.notnull(x) else None)
    df_after["会員番号"] = df_after["会員番号"].apply(lambda x: normalize_member_id(x) if pd.notnull(x) else None)

    # 列名を揃える（念のため）
    df_before.rename(columns={"大会前レーティング": "大会前レーティング"}, inplace=True)
    df_after.rename(columns={"大会後レーティング": "大会後レーティング"}, inplace=True)

    # マージ
    df_merge = pd.merge(
        df_before[["会員番号", "氏名", "大会前レーティング"]],
        df_after[["会員番号", "大会後レーティング"]],
        on="会員番号",
        how="outer"
    )

    # 増減
    df_merge["増減"] = df_merge["大会後レーティング"] - df_merge["大会前レーティング"]
    df_merge["氏名"] = df_merge["氏名"].fillna("")

    df_merge = df_merge.sort_values("会員番号").reset_index(drop=True)

    # 結果表示（タイトルはご要望どおり）
    st.subheader(f"第{kaisu}回羽曳野レイティング大会の増減結果")
    st.dataframe(df_merge)

    # CSV ダウンロード
    csv_bytes = df_merge.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button("結果をCSVでダウンロード", csv_bytes, file_name=f"habikino_{kaisu}_zougen.csv", mime="text/csv")
