import streamlit as st
import pandas as pd
import datetime as dt
from io import BytesIO
import hashlib

# ----------------------
# Page background color
# ----------------------
st.markdown(
    """
    <style>
    html, body, [class*="css"]  {
        background-color: #f0f8ff !important;  /* light blue */
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ----------------------
# Streamlit page config
# ----------------------
st.set_page_config(
    page_title="Limpopo Province Pharmaceutical Desktop",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ----------------------
# Password handling
# ----------------------
def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()

USERS = {
    "admin": "21232f297a57a5a743894a0e4a801fc3",
    "pharma": "6cb75f652a9b52798eb6cf2201057c73"
}

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# ----------------------
# Login screen
# ----------------------
def login_screen():
    try:
        st.image("logo.png", width=550)
    except:
        st.warning("⚠️ Logo not found. Place 'logo.png' in the same folder.")

    st.markdown("""
        <div style='text-align:center; padding: 10px;'>
            <h1 style='color:#0047AB;'>Rx💊 Pharmaceutical Products Dashboard</h1>
            <h3 style='margin-top:-10px; color:#888;'>Secure Login</h3>
            <hr style='margin-top:15px;'>
        </div>
    """, unsafe_allow_html=True)

    login_col = st.columns([1, 2, 1])[1]
    with login_col:
        username = st.text_input("👤 Username")
        password = st.text_input("🔒 Password", type="password")
        if st.button("Login", use_container_width=True):
            if username in USERS and USERS[username] == hash_password(password):
                st.session_state.logged_in = True
            else:
                st.error("❌ Invalid username or password")

if not st.session_state.logged_in:
    login_screen()
    st.stop()

# ----------------------
# Dashboard header
# ----------------------
st.markdown("""
    <div style='background-color:#0047AB;padding:15px;border-radius:10px'>
        <h1 style='color:white;text-align:center;'>Rx💊 Limpopo Province Pharmaceutical Stock Dashboard</h1>
    </div>
""", unsafe_allow_html=True)

st.write("Upload your Excel file to start analyzing pharmaceutical stock levels across facilities.")
uploaded_file = st.file_uploader("📂 Upload Excel File", type=["xlsx", "xls"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    df.columns = df.columns.str.strip()
    df = df.loc[:, ~df.columns.str.contains("^Unnamed")]

    # ----------------------
    # Identify columns
    # ----------------------
    facility_col = None
    for c in df.columns:
        if c.lower() == "facility name":
            facility_col = c
            break
    if not facility_col:
        for c in df.columns:
            if c.lower() in ["facility", "hospital", "clinic"]:
                facility_col = c
                break

    desc_col = next(
        (c for c in df.columns if c.lower() in ["description", "item description", "medicine", "nsn description"]),
        None)
    stock_col = next((c for c in df.columns if c.lower() in ["on hand", "stock", "stock_on_hand", "qty", "quantity"]),
                     None)
    expiry_col = next((c for c in df.columns if c.lower() in ["expiry", "expiry date", "expiration", "exp"]), None)
    amc_col = next(
        (c for c in df.columns if c.lower() in ["amc", "average monthly consumption", "avg monthly consumption"]),
        None)
    nsn_col = next((c for c in df.columns if c.lower() == "nsn"), None)

    missing = [name for name, col in
               zip(["Facility", "Description", "Stock", "Expiry", "AMC"], [facility_col, desc_col, stock_col, expiry_col, amc_col]) if
               col is None]
    if missing:
        st.error("❌ Missing required columns: " + ", ".join(missing))
        st.stop()

    # ----------------------
    # Clean numeric and date columns
    # ----------------------
    df[stock_col] = pd.to_numeric(df[stock_col], errors="coerce").fillna(0)

    # AMC: fix comma decimals
    df[amc_col] = df[amc_col].astype(str).str.replace(",", ".", regex=False)
    df[amc_col] = pd.to_numeric(df[amc_col], errors="coerce").fillna(0)

    df[expiry_col] = pd.to_datetime(df[expiry_col], errors="coerce")
    df["Days_Left"] = (df[expiry_col] - dt.datetime.today()).dt.days

    # ----------------------
    # Expiry status
    # ----------------------
    def expiry_status(days):
        if pd.isna(days): return "No Expiry"
        if days < 0: return "Expired"
        if days <= 30: return "⚠️ Expiring <30 days"
        if days <= 90: return "🟡 Expiring <90 days"
        return "🟢 OK"

    df["Expiry_Status"] = df["Days_Left"].apply(expiry_status)

    # ----------------------
    # Hybrid Item Key (NSN + Description / Description alone)
    # ----------------------
    if nsn_col:
        df[nsn_col] = df[nsn_col].astype(str).str.strip()
        df.loc[df[nsn_col].isin(["", "nan", "None"]), nsn_col] = pd.NA
    else:
        df['NSN'] = pd.NA
        nsn_col = 'NSN'

    df["Item_Key"] = df.apply(
        lambda r: f"{r[facility_col]}|{r[nsn_col]}|{r[desc_col]}" if pd.notna(r[nsn_col])
        else f"{r[facility_col]}|{r[desc_col]}",
        axis=1
    )

    # ----------------------
    # Grouping for stock-out calculation
    # ----------------------
    LEAD_TIME_DAYS = 7
    grouped = df.groupby("Item_Key", as_index=False).agg(
        Facility_Name=(facility_col, "first"),
        Description=(desc_col, "first"),
        NSN=(nsn_col, "first"),
        Total_Stock=(stock_col, "sum"),
        AMC=(amc_col, "first")
    )

    grouped["ADU"] = grouped["AMC"] / 30
    grouped["Stock_Balance_After_Lead"] = grouped["Total_Stock"] - (grouped["ADU"] * LEAD_TIME_DAYS)
    grouped["Stock_Status"] = grouped["Stock_Balance_After_Lead"].apply(
        lambda x: "🔴 OUT OF STOCK" if x <= 0 else "🟢 OK"
    )

    # Merge back to batch-level df
    df = df.merge(
        grouped[["Item_Key", "Total_Stock", "ADU", "Stock_Balance_After_Lead", "Stock_Status"]],
        on="Item_Key",
        how="left"
    )

    # ----------------------
    # Filters
    # ----------------------
    st.subheader("🔍 Filters")
    col1, col2 = st.columns([2, 3])
    with col1:
        search_facility = st.text_input("🏥 Search Facility")
    with col2:
        search_text = st.text_input("🔎 Search Item")

    df_filtered = df.copy()
    if search_facility.strip():
        df_filtered = df_filtered[df_filtered[facility_col].str.contains(search_facility, case=False, na=False)]
    if search_text.strip():
        df_filtered = df_filtered[df_filtered[desc_col].str.contains(search_text, case=False, na=False)]

    # ----------------------
    # Stock Summary with distinct-item logic
    # ----------------------
    st.subheader("📊 Stock Summary")
    c1, c2, c3, c4, c5, c6 = st.columns(6)

    c1.metric("Expired Items", df_filtered[df_filtered["Expiry_Status"] == "Expired"].shape[0])
    c2.metric("Expiring <30 Days", df_filtered[df_filtered["Expiry_Status"] == "⚠️ Expiring <30 days"].shape[0])
    c3.metric("Expiring <90 Days", df_filtered[df_filtered["Expiry_Status"] == "🟡 Expiring <90 days"].shape[0])

    distinct_items_count = df_filtered['Item_Key'].nunique()
    c4.metric("Total Items", distinct_items_count)

    out_of_stock_count = grouped[grouped["Stock_Status"] == "🔴 OUT OF STOCK"]['Item_Key'].nunique()
    covered_items_count = grouped[grouped["Stock_Status"] == "🟢 OK"]['Item_Key'].nunique()

    c5.metric("🚨 Items Out of Stock (7-Day Risk)", out_of_stock_count)
    c6.metric("📦 Items Covered", covered_items_count)

    # ----------------------
    # Items expiring soon (batch-level)
    # ----------------------
    st.subheader("⚠️ Items Expiring Soon")
    df_expiring = df_filtered[df_filtered["Days_Left"] <= 90]

    def color_row(r):
        if r["Expiry_Status"] == "Expired":
            return ["background-color:#ff9999"] * len(r)
        elif r["Expiry_Status"] == "⚠️ Expiring <30 days":
            return ["background-color:#ffe16b"] * len(r)
        elif r["Expiry_Status"] == "🟡 Expiring <90 days":
            return ["background-color:#fff4b3"] * len(r)
        else:
            return [""] * len(r)

    if not df_expiring.empty:
        st.dataframe(df_expiring.style.apply(color_row, axis=1), height=400, use_container_width=True)
    else:
        st.info("✅ No items expiring within 90 days.")

    st.dataframe(df_filtered, height=500, use_container_width=True)

    # ----------------------
    # Download button
    # ----------------------
    @st.cache_data
    def to_excel(data):
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            data.to_excel(writer, index=False, sheet_name="Filtered")
        return output.getvalue()

    st.download_button(
        label="💾 Download Excel",
        data=to_excel(df_filtered),
        file_name="filtered_stock.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

else:
    st.info("⬆️ Upload an Excel file to begin.")

# ----------------------
# Cleanup padding
# ----------------------
st.markdown("""
    <style>
    .css-18e3th9{padding-top:0rem;}
    .css-1d391kg{padding-left:0rem;padding-right:0rem;}
    </style>
""", unsafe_allow_html=True)







