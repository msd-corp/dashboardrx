import streamlit as st
import pandas as pd
import datetime as dt
from io import BytesIO
import hashlib

# ----------------------
# Page background color
# ----------------------
st.markdown("""
<style>
html, body, [class*="css"]  {
    background-color: #f0f8ff !important;
}
</style>
""", unsafe_allow_html=True)

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
# Login screen with logo and green header
# ----------------------
def login_screen():
    try:
        st.image("logo.png", width=550)
    except:
        st.warning("⚠️ Logo not found. Place 'logo.png' in the same folder.")

    st.markdown("""
        <div style='text-align:center; padding: 10px; background-color:#28a745; border-radius:8px;'>
            <h1 style='color:white;'>Rx💊 Pharmaceutical Products Dashboard</h1>
            <h3 style='margin-top:-10px; color:white;'>Secure Login</h3>
            <hr style='margin-top:15px; border-color:white;'>
        </div>
    """, unsafe_allow_html=True)

    login_col = st.columns([1, 2, 1])[1]
    with login_col:
        username = st.text_input("👤 Username", key="username")
        password = st.text_input("🔒 Password", type="password", key="password")
        st.markdown("""
            <style>
            div.stButton > button:first-child {
                background-color: #4CAF50;
                color: white;
                height: 3em;
                width: 100%;
                font-size: 20px;
            }
            </style>
        """, unsafe_allow_html=True)
        if st.button("Login"):
            if username in USERS and USERS[username] == hash_password(password):
                st.session_state.logged_in = True
            else:
                st.error("❌ Invalid username or password")

if not st.session_state.logged_in:
    login_screen()
    st.stop()

# ----------------------
# Load default Excel from GitHub or uploaded file
# ----------------------
GITHUB_EXCEL_URL = "https://raw.githubusercontent.com/username/repo/main/stock.xlsx"  # <-- replace with your raw link
uploaded_file = st.file_uploader("📂 Upload Excel File (optional)", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
else:
    try:
        df = pd.read_excel(GITHUB_EXCEL_URL)
    except Exception as e:
        st.error(f"❌ Could not load Excel from GitHub: {e}")
        st.stop()

df.columns = df.columns.str.strip()
df = df.loc[:, ~df.columns.str.contains("^Unnamed")]

# ----------------------
# Columns setup
# ----------------------
facility_col = df.columns[1]  # Facility Name
onhand_col = df.columns[7]    # OnHand
nsn_col = df.columns[2]       # NSN
amc_col = df.columns[5]       # AMC
desc_col = next((c for c in df.columns if c.strip().lower() in ["description","item description","medicine","nsn description"]), None)
stock_col = next((c for c in df.columns if c.strip().lower() in ["on hand","stock","stock_on_hand","qty","quantity"]), None)
expiry_col = next((c for c in df.columns if c.strip().lower() in ["expiry","expiry date","expiration","exp"]), None)

missing = [name for name, col in zip(["Item/Description", "Stock", "Expiry"], [desc_col, stock_col, expiry_col]) if col is None]
if missing:
    st.error("❌ Missing required columns: " + ", ".join(missing))
    st.stop()

# ----------------------
# Data preprocessing
# ----------------------
df[stock_col] = pd.to_numeric(df[stock_col], errors="coerce").fillna(0)
df[expiry_col] = pd.to_datetime(df[expiry_col], errors="coerce")
df["Days_Left"] = (df[expiry_col] - dt.datetime.today()).dt.days
df[onhand_col] = pd.to_numeric(df[onhand_col], errors='coerce').fillna(0)
df[amc_col] = pd.to_numeric(df[amc_col], errors='coerce').fillna(0)

# Expiry status
def expiry_status(days):
    if pd.isna(days): return "No Expiry"
    if days < 0: return "Expired"
    if days <= 30: return "⚠️ Expiring <30 days"
    if days <= 90: return "🟡 Expiring <90 days"
    return "🟢 OK"

df["Expiry_Status"] = df["Days_Left"].apply(expiry_status)

# Projected Stock until next delivery (7 days)
next_delivery_days = 7
df["Avg_Daily_Usage"] = df[amc_col] / 30
df["Projected_Consumption"] = df["Avg_Daily_Usage"] * next_delivery_days
df["Available_Until_Delivery"] = df[onhand_col] - df["Projected_Consumption"]
df["Stock_Status"] = df["Available_Until_Delivery"].apply(lambda x: "✅ Sufficient" if x>0 else "🛑 Risk of Stockout")
df["At_Risk_Flag"] = df["Available_Until_Delivery"] <= 0

# ----------------------
# Sidebar filters
# ----------------------
st.sidebar.subheader("🔍 Filters")
search_facility = st.sidebar.text_input("🏥 Facility")
search_text = st.sidebar.text_input("🔎 Item")

df_filtered = df.copy()
if search_facility.strip():
    df_filtered[facility_col] = df_filtered[facility_col].astype(str)
    df_filtered = df_filtered[df_filtered[facility_col].str.contains(search_facility, case=False, na=False)]

if search_text.strip():
    df_filtered[desc_col] = df_filtered[desc_col].astype(str)
    df_filtered = df_filtered[df_filtered[desc_col].str.contains(search_text, case=False, na=False)]

# ----------------------
# Stock Availability Top Card
# ----------------------
total_items = df_filtered.shape[0]
available_items = (df_filtered["Available_Until_Delivery"] > 0).sum()
percent_available = available_items / total_items * 100 if total_items > 0 else 0

st.subheader("📊 Stock Availability Until Next Delivery (7 days)")
st.markdown(
    f"<div style='background-color:#d4edda;padding:20px;border-radius:12px;text-align:center;"
    f"font-weight:bold;font-size:24px;color:#155724;'>"
    f"✅ Stock Availability: {available_items} / {total_items} ({percent_available:.1f}%)"
    f"</div>",
    unsafe_allow_html=True
)

# ----------------------
# Dashboard header (blue)
# ----------------------
st.markdown("""
<div style='background-color:#0047AB;padding:15px;border-radius:10px'>
<h1 style='color:white;text-align:center;'>Rx💊 Limpopo Province Pharmaceutical Stock Dashboard</h1>
</div>
""", unsafe_allow_html=True)

# ----------------------
# Stock Summary
# ----------------------
st.subheader("📊 Stock Summary")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Expired Items", df_filtered[df_filtered["Expiry_Status"] == "Expired"].shape[0])
c2.metric("Expiring <30 Days", df_filtered[df_filtered["Expiry_Status"] == "⚠️ Expiring <30 days"].shape[0])
c3.metric("Expiring <90 Days", df_filtered[df_filtered["Expiry_Status"] == "🟡 Expiring <90 days"].shape[0])
c4.metric("Total Items", df_filtered.shape[0])

# ----------------------
# Top 10 Critical Facilities (vertical)
# ----------------------
critical_threshold = 80  # percent available below this is critical
facility_availability = df_filtered.groupby(facility_col)["Available_Until_Delivery"].apply(
    lambda x: max(0, (x>0).sum()/len(x)*100)
)

top_facilities = facility_availability[facility_availability < critical_threshold].sort_values().head(10)

st.subheader("⚠️ Top 10 Critical Facilities (Stock < 80%)")
st.bar_chart(top_facilities, height=250)  # vertical bars

# ----------------------
# Items expiring soon
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
    if df_expiring.size <= 262144:
        st.dataframe(df_expiring.style.apply(color_row, axis=1).set_properties(**{'font-size':'14px','text-align':'center'}), height=400)
    else:
        st.dataframe(df_expiring, height=400)
else:
    st.info("✅ No items expiring within 90 days.")

# ----------------------
# Expandable Details
# ----------------------
with st.expander("📋 View Detailed Facility Stock Data"):
    st.dataframe(df_filtered.sort_values(by="Available_Until_Delivery"), height=500)

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

# ----------------------
# Cleanup padding
# ----------------------
st.markdown("""
<style>
.css-18e3th9{padding-top:0rem;}
.css-1d391kg{padding-left:0rem;padding-right:0rem;}
</style>
""", unsafe_allow_html=True)
