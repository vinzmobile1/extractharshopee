import os
import json
import base64
import datetime
import pandas as pd
import streamlit as st
from urllib.parse import quote
from io import BytesIO

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
                name = trim_name(find_nested_value(item, "item_card_displayed_asset.name"))
                if name == "N/A":
                    name = trim_name(find_nested_value(item, "item_basic.name"))
                if name == "N/A":
                    name = trim_name(find_nested_value(item, "name"))
                price = find_value(item, ["price"], 0) / 100000
                shop_name = find_value(item, ["shop_name"])
                rating_star = round(find_value(item, ["rating_star"], 0), 1)
                historical_sold = find_value(item, ["historical_sold_count", "historical_sold"], 0)
                monthly_sold = find_value(item, ["monthly_sold_count", "sold"], 0)
                rating_count = find_nested_value(item, "item_rating.rating_count", "N/A")
                if isinstance(rating_count, list) and rating_count:
                    rating_count = rating_count[0]
                ctime = find_value(item, ["ctime"])
                ctime = datetime.datetime.fromtimestamp(ctime).strftime('%Y-%m-%d') if isinstance(ctime, (int, float)) else "N/A"
                shopee_url = create_shopee_url("https://shopee.co.id/", name, shopid, itemid)
                data_list.append({
                    "itemid": itemid,
                    "shopid": shopid,                    
                    "upload_date": ctime,
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
        st.error(f"Error processing file: {e}")
    return pd.DataFrame(data_list) if data_list else None

st.title("Shopee HAR File Parser")

uploaded_files = st.file_uploader("Upload HAR files", type=["har"], accept_multiple_files=True)

if uploaded_files:
    all_dataframes = [ekstrak_dan_simpan_data(file) for file in uploaded_files]
    all_dataframes = [df for df in all_dataframes if df is not None]

    if all_dataframes:
        final_df = pd.concat(all_dataframes, ignore_index=True)
        st.write("### Data Extracted")
        st.dataframe(final_df)
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            final_df.to_excel(writer, index=False, sheet_name="Shopee Data")
            writer.book.close()
        output.seek(0)
        st.download_button("Download Excel", output, "shopee_data.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.warning("No valid data extracted from the uploaded files.")
