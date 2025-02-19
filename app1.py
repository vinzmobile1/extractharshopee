import streamlit as st
import json
import base64
import pandas as pd
from datetime import datetime
import os

# Data user dan password beserta masa aktifnya
users = {
    "aby": {"password": "@aby", "valid_until": "20/02/2026"},
    "demo": {"password": "@demo", "valid_until": "25/02/2025"}
}

# Fungsi untuk memeriksa otentikasi
def check_credentials(username, password):
    if username in users:
        user_info = users[username]
        if user_info["password"] == password:
            valid_until = datetime.strptime(user_info["valid_until"], "%d/%m/%Y")
            if datetime.now() <= valid_until:
                return True
            else:
                st.error("Akun Anda telah kedaluwarsa.")
        else:
            st.error("Password salah.")
    else:
        st.error("Username tidak ditemukan.")
    return False

# Judul aplikasi
st.title("HAR File Processor")

# Form login
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    with st.form(key='login_form'):
        username = st.text_input(label='Username')
        password = st.text_input(label='Password', type='password')
        login_button = st.form_submit_button(label='Login')

    # Proses login
    if login_button:
        if check_credentials(username, password):
            st.session_state.logged_in = True  # Set status login
            st.success("Login berhasil!")  # Tampilkan pesan sukses
else:
    # Jika sudah login, tampilkan halaman pemrosesan file HAR
    st.markdown("""
    Aplikasi ini memproses file HAR, mengekstrak data produk dari Shopee, dan menghasilkan URL produk.
    """)

    # Fungsi untuk membuat URL
    def create_shopee_url(awalan, name, shopid, itemid):
        name_formatted = name.replace(' ', '-')
        url = f"{awalan}{name_formatted}-i.{shopid}.{itemid}"
        return url

    # Fungsi untuk memproses file HAR
    def process_har_files(har_files):
        data_list = []

        for har_file in har_files:
            with open(har_file, "r", encoding="utf-8") as f:
                har_data = json.load(f)

            entries = har_data.get("log", {}).get("entries", [])

            for entry in entries:
                url = entry.get("request", {}).get("url")
                if not url or "items" not in url:
                    continue

                try:
                    response_content = entry.get("response", {}).get("content", {}).get("text", "{}")
                    encoding = entry.get("response", {}).get("content", {}).get("encoding", "").lower()
                    if encoding == "base64":
                        response_content = base64.b64decode(response_content).decode('utf-8')

                    response_data = json.loads(response_content)

                    if "data" in response_data and "items" in response_data["data"]:
                        items_data = response_data["data"]["items"]
                        for item in items_data:
                            ctime = item.get("ctime")
                            ctime_date = datetime.fromtimestamp(ctime).strftime('%Y-%m-%d') if ctime else None
                            item_data = {
                                "status_produk": "Aktif",
                                "shopid": str(item.get("shopid")),  # Convert to text
                                "itemid": str(item.get("itemid")),  # Convert to text
                                "item_name": item.get("name"),
                                "sold_30_days": item.get("sold"),
                                "historical_sold": item.get("historical_sold"),
                                "price": item.get("price") / 100000 if item.get("price") else None,
                                "shop_name": item.get("shop_name"),
                                "info": item.get("info"),
                                "startedDateTime": entry.get("startedDateTime", "").split("T")[0],
                                "url": create_shopee_url("https://shopee.co.id/", item.get("name"), item.get("shopid"), item.get("itemid")),
                                "upload": ctime_date
                            }
                            data_list.append(item_data)

                    if "items" in response_data:
                        items_data = response_data["items"]
                        for item in items_data:
                            item_basic = item.get("item_basic", {})
                            if item_basic:
                                ctime = item_basic.get("ctime")
                                ctime_date = datetime.fromtimestamp(ctime).strftime('%Y-%m-%d') if ctime else None
                                item_basic_data = {
                                    "status_produk": "Tidak Aktif",
                                    "shopid": str(item.get("shopid")),  # Convert to text
                                    "itemid": str(item.get("itemid")),  # Convert to text
                                    "item_name": item_basic.get("name"),
                                    "sold_30_days": item_basic.get("sold"),
                                    "historical_sold": item_basic.get("historical_sold"),
                                    "price": item_basic.get("price") / 100000 if item_basic.get("price") else None,
                                    "shop_name": item_basic.get("shop_name"),
                                    "info": None,
                                    "startedDateTime": entry.get("startedDateTime", "").split("T")[0],
                                    "url": create_shopee_url("https://shopee.co.id/", item_basic.get("name"), item.get("shopid"), item_basic.get("itemid")),
                                    "upload": ctime_date
                                }
                                data_list.append(item_basic_data)

                except json.JSONDecodeError:
                    pass

        df = pd.DataFrame(data_list)

        if not df.empty:
            df['score_with_prefix'] = df['info'].str.extract(r'\{([^}]+)\}')
            df['score_product'] = df['score_with_prefix'].str.extract(r'SCORE:([0-9.]+)')
            df.drop(columns=['score_with_prefix'], inplace=True)
            df.drop(columns=['info'], inplace=True)

            df['sold_30_days'] = pd.to_numeric(df['sold_30_days'], errors='coerce').astype('Int64')
            df['historical_sold'] = pd.to_numeric(df['historical_sold'], errors='coerce').astype('Int64')
            df['score_product'] = pd.to_numeric(df['score_product'], errors='coerce').astype('float64')

        return df

    # Upload file HAR
    uploaded_files = st.file_uploader("Upload HAR files", type=["har"], accept_multiple_files=True)

    if uploaded_files:
        # Simpan file HAR yang diunggah ke direktori sementara
        temp_dir = "./temp_har_files"
        os.makedirs(temp_dir, exist_ok=True)
        har_files = []

        for file in uploaded_files:
            file_path = os.path.join(temp_dir, file.name)
            with open(file_path, "wb") as f:
                f.write(file.getbuffer())
            har_files.append(file_path)

        # Proses file HAR
        df = process_har_files(har_files)

        # Hapus file HAR sementara
        for file_path in har_files:
            os.remove(file_path)

        # Tampilkan hasil
        st.subheader("Result Data")
        st.dataframe(df)

        # Opsi untuk mengunduh hasil sebagai CSV
        csv = df.to_csv(index=False)
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name="result_data.csv",
            mime="text/csv"
        )

    # Opsi logout
    if st.button("Logout"):
        st.session_state.logged_in = False
        st.success("Anda telah berhasil logout.")
