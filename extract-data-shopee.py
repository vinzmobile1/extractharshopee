import streamlit as st
import json
import base64
import pandas as pd
import os
import io
import datetime
from urllib.parse import quote

# Data user dan password beserta masa aktifnya
users = {
    "aby": {"password": "@aby", "valid_until": "20/02/2026"},
    "demo": {"password": "@demo", "valid_until": "25/02/2025"}
}

def check_credentials(username, password):
    if username in users:
        user_info = users[username]
        if user_info["password"] == password:
            valid_until = datetime.datetime.strptime(user_info["valid_until"], "%d/%m/%Y")
            if datetime.datetime.now() <= valid_until:
                return True
            else:
                st.error("Akun Anda telah kedaluwarsa.")
        else:
            st.error("Password salah.")
    else:
        st.error("Username tidak ditemukan.")
    return False

st.set_page_config(page_title="Extract Data Shopee")
st.title("Extract Data Shopee")

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    with st.form(key='login_form'):
        username = st.text_input(label='Username')
        password = st.text_input(label='Password', type='password')
        login_button = st.form_submit_button(label='Login')

    if login_button:
        if check_credentials(username, password):
            st.session_state.logged_in = True
            st.success("Login berhasil!")
else:
    st.markdown("""
    Aplikasi ini memproses file HAR, mengekstrak data produk dari Shopee, dan menghasilkan URL produk.
    """)

    def trim_name(name):
        return " ".join(name.split()) if isinstance(name, str) else name

    def find_nested_value(data, path, default="N/A"):
        keys = path.split(".")
        for key in keys:
            if isinstance(data, dict) and key in data:
                data = data[key]
            elif isinstance(data, list) and key.isdigit() and len(data) > int(key):
                data = data[int(key)]
            else:
                return default
        return data

    def find_value(data, keys, default="N/A"):
        if isinstance(data, dict):
            for key in keys:
                if key in data:
                    return data[key]
            for v in data.values():
                result = find_value(v, keys, default)
                if result != default:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = find_value(item, keys, default)
                if result != default:
                    return result
        return default

    def create_shopee_url(awalan, name, shopid, itemid):
        name_formatted = name.replace(' ', '-')
        return f"{awalan}{name_formatted}-i.{shopid}.{itemid}"

    def ekstrak_dan_simpan_data(file):
        data_list = []
        try:
            har_data = json.load(file)
            for entry in har_data.get("log", {}).get("entries", []):
                content = entry.get("response", {}).get("content", {})
                text = content.get("text")
                encoding = content.get("encoding")

                if not text:
                    continue

                try:
                    decoded_text = base64.b64decode(text).decode('utf-8') if encoding == "base64" else text
                    json_data = json.loads(decoded_text)
                except Exception:
                    continue

                item_lists = find_value(json_data, ["item_cards", "items", "item"], [])
                if not isinstance(item_lists, list):
                    continue

                for item in item_lists:
                    itemid = str(find_value(item, ["itemid"]))
                    shopid = str(find_value(item, ["shopid"]))
                    name = trim_name(find_nested_value(item, "item_basic.name", "N/A"))
                    price = find_value(item, ["price"], 0) / 100000
                    shop_name = find_value(item, ["shop_name"])
                    rating_star = round(find_value(item, ["rating_star"], 0), 1)
                    historical_sold = find_value(item, ["historical_sold_count", "historical_sold"], 0)
                    monthly_sold = find_value(item, ["monthly_sold_count", "sold"], 0)
                    rating_count = find_nested_value(item, "item_rating.rating_count", "N/A")
                    ctime = find_value(item, ["ctime"])
                    ctime = datetime.datetime.fromtimestamp(ctime).strftime('%Y-%m-%d %H:%M:%S') if isinstance(ctime, (int, float)) else "N/A"
                    shopee_url = create_shopee_url("https://shopee.co.id/", name, shopid, itemid)

                    data_list.append({
                        "itemid": itemid,
                        "shopid": shopid,
                        "Tanggal Upload": ctime,
                        "shop_name": shop_name,
                        "item_name": name,
                        "price": price,
                        "sold_30_days": monthly_sold,
                        "historical_sold": historical_sold,
                        "shopee_url": shopee_url,
                        "rating_star": rating_star,
                        "rating_count": rating_count,
                    })
        except Exception as e:
            print(f"Error processing file: {e}")
        return pd.DataFrame(data_list) if data_list else None

    uploaded_files = st.file_uploader("Upload HAR files", type=["har"], accept_multiple_files=True)

    if uploaded_files:
        all_dataframes = [ekstrak_dan_simpan_data(file) for file in uploaded_files]
        all_dataframes = [df for df in all_dataframes if df is not None]

        if all_dataframes:
            final_df = pd.concat(all_dataframes, ignore_index=True)
            final_df.fillna("", inplace=True)
            st.dataframe(final_df, use_container_width=True)
            excel_file = io.BytesIO()
            with pd.ExcelWriter(excel_file, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, index=False, sheet_name='Shopee Data')
            excel_file.seek(0)
            file_name = f"Extract Shopee {datetime.datetime.now().strftime('%d-%m-%Y %H:%M')}.xlsx"
            st.download_button("Download Excel", data=excel_file, file_name=file_name, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.warning("Tidak ada data yang diekstrak dari file HAR yang diunggah.")

    if st.button("Logout"):
        st.session_state.logged_in = False
        st.success("Anda telah berhasil logout.")
