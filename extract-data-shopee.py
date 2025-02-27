import streamlit as st
import json
import base64
import pandas as pd
from datetime import datetime
import os
import io
import xlsxwriter

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

# Set page title
st.set_page_config(page_title="Extract Data Shopee")
# Judul aplikasi
st.title("Extract Data Shopee")

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
    @st.cache_data
    def process_har_files(har_files):
        data_list = []

        for har_file in har_files:
            with open(har_file, "r", encoding="utf-8") as f:
                har_data = json.load(f)

            entries = har_data.get("log", {}).get("entries", [])

            for entry in entries:
                url = entry.get("request", {}).get("url")
                if not url or ("items" not in url and "recommend_post" not in url):
                    continue

                try:
                    response_content = entry.get("response", {}).get("content", {}).get("text", "{}")
                    encoding = entry.get("response", {}).get("content", {}).get("encoding", "").lower()
                    if encoding == "base64":
                        response_content = base64.b64decode(response_content).decode('utf-8')

                    response_data = json.loads(response_content)

                    # Kelompok 1: Produk Aktif (data.items)
                    if "data" in response_data and "items" in response_data["data"]:
                        items_data = response_data["data"]["items"]
                        for item in items_data:
                            ctime = item.get("ctime")
                            ctime_date = datetime.fromtimestamp(ctime).strftime('%Y-%m-%d') if ctime else None
                            item_rating = item.get("item_rating", {})
                            rating_star = item_rating.get("rating_star", None)
                            rating_count = item_rating.get("rating_count", [0])[0]  # Ambil index pertama dari rating_count
                            item_data = {
                                "source": "Aktif",
                                "upload": ctime_date,
                                "shopid": str(item.get("shopid")),
                                "itemid": str(item.get("itemid")),
                                "item_name": item.get("name"),
                                "sold_30_days": item.get("sold"),
                                "historical_sold": item.get("historical_sold"),
                                "price": item.get("price") / 100000 if item.get("price") else None,
                                "shop_name": item.get("shop_name"),
                                "last update": entry.get("startedDateTime", "").split("T")[0],  # Tambahkan kolom baru
                                "url": create_shopee_url("https://shopee.co.id/", item.get("name"), item.get("shopid"), item.get("itemid")),
                                "rating_star": rating_star,  # Tambahkan kolom baru untuk rating_star
                                "rating_count": rating_count,  # Tambahkan kolom baru untuk rating_count
                                "shop_rating": item.get("shop_rating"),
                                "shop_location": item.get("shop_location")
                            }
                            data_list.append(item_data)

                    # Kelompok 2: Produk Tidak Aktif (items.item_basic)
                    if "items" in response_data:
                        items_data = response_data["items"]
                        for item in items_data:
                            item_basic = item.get("item_basic", {})
                            if item_basic:  # Hanya proses jika item_basic tidak kosong
                                ctime = item_basic.get("ctime")
                                ctime_date = datetime.fromtimestamp(ctime).strftime('%Y-%m-%d') if ctime else None
                                item_rating_basic = item_basic.get("item_rating", {})
                                rating_star_basic = item_rating_basic.get("rating_star", None)
                                rating_count_basic = item_rating_basic.get("rating_count", [0])[0]  # Ambil index pertama dari rating_count
                                item_basic_data = {
                                    "source": "Tidak Aktif",
                                    "upload": ctime_date,
                                    "shopid": str(item.get("shopid")),
                                    "itemid": str(item_basic.get("itemid")),
                                    "item_name": item_basic.get("name"),
                                    "sold_30_days": item_basic.get("sold"),
                                    "historical_sold": item_basic.get("historical_sold"),
                                    "price": item_basic.get("price") / 100000 if item_basic.get("price") else None,
                                    "shop_name": item_basic.get("shop_name"),
                                    "last update": entry.get("startedDateTime", "").split("T")[0],  # Tambahkan kolom baru
                                    "url": create_shopee_url("https://shopee.co.id/", item_basic.get("name"), item.get("shopid"), item.get("itemid")),
                                    "rating_star": rating_star_basic,  # Tambahkan kolom baru untuk rating_star
                                    "rating_count": rating_count_basic,  # Tambahkan kolom baru untuk rating_count
                                    "shop_rating": item_basic.get("shop_rating"),
                                    "shop_location": item_basic.get("shop_location")
                                }
                                data_list.append(item_basic_data)

                    # Kelompok 3: Produk Serupa (data.sections.data.item) - hanya dari URL yang mengandung "recommend_post"
                    if "data" in response_data and "sections" in response_data["data"]:
                        sections_data = response_data["data"]["sections"]
                        for section in sections_data:
                            if "data" in section and "item" in section["data"]:
                                items_data = section["data"]["item"]
                                for item in items_data:
                                    ctime = item.get("ctime")
                                    ctime_date = datetime.fromtimestamp(ctime).strftime('%Y-%m-%d') if ctime else None
                                    item_rating = item.get("item_rating", {})
                                    rating_star = item_rating.get("rating_star", None)
                                    rating_count = item_rating.get("rating_count", [0])[0]  # Ambil index pertama dari rating_count
                                    item_data = {
                                        "source": "Produk Serupa",
                                        "upload": ctime_date,
                                        "shopid": str(item.get("shopid")),
                                        "itemid": str(item.get("itemid")),
                                        "item_name": item.get("name"),
                                        "sold_30_days": item.get("sold"),
                                        "historical_sold": item.get("historical_sold"),
                                        "price": item.get("price") / 100000 if item.get("price") else None,
                                        "shop_name": item.get("shop_name"),
                                        "last update": entry.get("startedDateTime", "").split("T")[0],  # Tambahkan kolom baru
                                        "url": create_shopee_url("https://shopee.co.id/", item.get("name"), item.get("shopid"), item.get("itemid")),
                                        "rating_star": rating_star,  # Tambahkan kolom baru untuk rating_star
                                        "rating_count": rating_count,  # Tambahkan kolom baru untuk rating_count
                                        "shop_rating": item.get("shop_rating"),
                                        "shop_location": item.get("shop_location")
                                    }
                                    data_list.append(item_data)

                except json.JSONDecodeError:
                    pass  # Lewati jika response content tidak valid

        df = pd.DataFrame(data_list)

        if not df.empty:
            df['item_name'] = df['item_name'].str.replace(r'\s+', ' ', regex=True)  # Ganti satu atau lebih spasi dengan satu spasi
            df['sold_30_days'] = pd.to_numeric(df['sold_30_days'], errors='coerce').astype('Int64')
            df['historical_sold'] = pd.to_numeric(df['historical_sold'], errors='coerce').astype('Int64')
            df['rating_star'] = round(pd.to_numeric(df['rating_star'], errors='coerce').astype('float64'), 1)
            df['shop_rating'] = round(pd.to_numeric(df['shop_rating'], errors='coerce').astype('float64'), 1)

            # Reorder columns
            new_order = ['source', 'last update', 'upload', 'shopid', 'itemid', 'item_name', 'price', 'sold_30_days', 'historical_sold', 'url', 'rating_star', 'rating_count', 'shop_name', 'shop_rating', 'shop_location']
            df = df.reindex(columns=new_order)

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

        if not df.empty:
            # Buat 3 kolom untuk dropdown filter
            col1, col2, col3 = st.columns(3)

            with col1:
                source_filter = st.multiselect("Filter Source", options=sorted(df['source'].unique().tolist()), default=None)
            with col2:
                item_name_filter = st.multiselect("Filter Item Name", options=sorted(df['item_name'].unique().tolist()), default=None)
            with col3:
                shop_name_filter = st.multiselect("Filter Shop Name", options=sorted(df['shop_name'].unique().tolist()), default=None)

            # Filter DataFrame berdasarkan dropdown
            filtered_df = df.copy()
            if source_filter: # Check if source_filter list is not empty
                filtered_df = filtered_df[filtered_df['source'].isin(source_filter)]
            if item_name_filter: # Check if item_name_filter list is not empty
                filtered_df = filtered_df[filtered_df['item_name'].isin(item_name_filter)]
            if shop_name_filter: # Check if shop_name_filter list is not empty
                filtered_df = filtered_df[filtered_df['shop_name'].isin(shop_name_filter)]

            # Checkbox untuk menampilkan semua data
            show_all_data = st.checkbox("Tampilkan Semua Data (Tanpa Pagination)", value=False)

            row_count = len(filtered_df)  # Hitung jumlah baris setelah filtering
            st.write(f"Total Data: {row_count} Baris") # Tampilkan jumlah baris

            if show_all_data:
                # Tampilkan seluruh DataFrame tanpa pagination
                st.subheader("Result Data (Semua Data)")
                st.dataframe(filtered_df, use_container_width=True)
                data_to_download = filtered_df # Download seluruh filtered_df
            else:
                # Pagination
                items_per_page = 25  # Jumlah item per halaman
                num_pages = max(1, (len(filtered_df) + items_per_page - 1) // items_per_page)
                page_options = list(range(1, num_pages + 1))
                page_number = st.selectbox("Halaman", options=page_options, index=0)
                start_index = (page_number - 1) * items_per_page
                end_index = start_index + items_per_page
                paged_df = filtered_df.iloc[start_index:end_index]

                # Tampilkan hasil dengan pagination
                st.subheader("Result Data (Halaman {})".format(page_number))
                st.dataframe(paged_df, use_container_width=True)
                data_to_download = filtered_df # Download seluruh filtered_df

            # Opsi untuk mengunduh hasil sebagai Excel
            excel_file = io.BytesIO()  # Create a BytesIO object to hold the Excel file
            with pd.ExcelWriter(excel_file, engine='xlsxwriter') as writer:
                data_to_download.to_excel(writer, index=False, sheet_name='Shopee Data')  # Write DataFrame to Excel

            # Set the cursor to the beginning of the BytesIO object
            excel_file.seek(0)

            # Mendapatkan tanggal dan waktu saat ini
            current_time = datetime.now().strftime("%d-%m-%Y %H:%M")

            # Membuat nama file berdasarkan tanggal dan waktu
            file_name = f"Extract Shopee {current_time}.xlsx"

            # Tombol untuk mengunduh file Excel
            st.download_button(
                label="Download Excel",
                data=excel_file,
                file_name=file_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("No data extracted from the uploaded HAR files.")

    # Opsi logout
    if st.button("Logout"):
        st.session_state.logged_in = False
        st.success("Anda telah berhasil logout.")
