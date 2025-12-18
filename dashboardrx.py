import streamlit as st
import pandas as pd
import datetime as dt
from io import BytesIO
import hashlib
import altair as alt

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
# Login screen
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

    login_col = st.columns([1,2,1])[1]
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
# Load Excel from GitHub
# ----------------------
GITHUB_EXCEL_URL = "https://raw.githubusercontent.com/msd-corp/dashboardrx/main/stock.xlsx"

try:
    df = pd.read_excel(GITHUB_EXCEL_URL)
except Exception as e:
    st.error(f"❌ Could not load Excel from GitHub. Check the URL and network: {e}")
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

# Fix AMC decimal if comma exists
df[amc_col] = df[amc_col].astype(str).str.replace(",", ".")
df[amc_col] = pd.to_numeric(df[amc_col], errors='coerce').fillna(0)

def expiry_status(days):
    if pd.isna(days): return "No Expiry"
    if days < 0: return "Expired"
    if days <= 30: return "⚠️ Expiring <30 days"
    if days <= 90: return "🟡 Expiring <90 days"
    return "🟢 OK"

df["Expiry_Status"] = df["Days_Left"].apply(expiry_status)

# ----------------------
# Hybrid Item Key for NSN + Description
# ----------------------
df[nsn_col] = df[nsn_col].astype(str).str.strip()
df.loc[df[nsn_col].isin(["", "nan", "None"]), nsn_col] = pd.NA

df["Item_Key"] = df.apply(
    lambda r:
        f"{r[facility_col]}|{r[nsn_col]}|{r[desc_col]}" if pd.notna(r[nsn_col])
        else f"{r[facility_col]}|{r[desc_col]}",
    axis=1
)

# ----------------------
# Stock-out Calculation (AMC -> ADU -> 7-day Lead)
# ----------------------
LEAD_TIME_DAYS = 7
grouped = (
    df.groupby("Item_Key", as_index=False)
      .agg(
          Facility_Name=(facility_col, "first"),
          Description=(desc_col, "first"),
          NSN=(nsn_col, "first"),
          Total_Stock=(onhand_col, "sum"),
          AMC=(amc_col, "first")
      )
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
# Sidebar Filters
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
# Stock Availability Top Card (Filtered)
# ----------------------
filtered_items = df_filtered.groupby("Item_Key").agg({
    "Total_Stock": "first",
    "Stock_Balance_After_Lead": "first"
}).reset_index()

total_items = filtered_items.shape[0]
available_items = (filtered_items["Stock_Balance_After_Lead"] > 0).sum()
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
<h1 style='color:white;text-align:center;'>masedi💊 Rx_Soln Product Dashboard</h1>
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
c4.metric("Total Items", filtered_items.shape[0])

# ----------------------
# Top 10 Critical Facilities (Altair Horizontal)
# ----------------------
critical_threshold = 80
facility_availability = df_filtered.groupby(facility_col)["Stock_Balance_After_Lead"].apply(
    lambda x: max(0, (x>0).sum()/len(x)*100)
).reset_index(name="Availability_Percent")

top_facilities = facility_availability[facility_availability["Availability_Percent"] < critical_threshold] \
    .sort_values("Availability_Percent").head(10)

def bar_color(facility_name):
    if search_facility.strip() and facility_name.lower() in search_facility.strip().lower():
        return "#28a745"
    return "#dc3545"

top_facilities["Color"] = top_facilities[facility_col].apply(bar_color)

with st.expander("⚠️ Top 10 Critical Facilities (Stock < 80%)"):
    chart = alt.Chart(top_facilities).mark_bar().encode(
        x=alt.X("Availability_Percent:Q", title="Stock Availability (%)"),
        y=alt.Y(f"{facility_col}:N", sort="-x", title="Facility"),
        color=alt.Color("Color:N", scale=None, legend=None),
        tooltip=[facility_col, "Availability_Percent"]
    ).properties(
        width=600,
        height=350
    ).configure_axis(
        labelFontSize=14,
        titleFontSize=16
    ).configure_title(
        fontSize=18
    )
    st.altair_chart(chart, use_container_width=True)

# ----------------------
# Items Expiring Soon
# ----------------------
df_expiring = df_filtered[df_filtered["Days_Left"] <= 90]

with st.expander("⚠️ Items Expiring Soon"):
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
            st.dataframe(df_expiring.style.apply(color_row, axis=1)
                         .set_properties(**{'font-size':'14px','text-align':'center'}), height=400)
        else:
            st.dataframe(df_expiring, height=400)
    else:
        st.info("✅ No items expiring within 90 days.")

# ----------------------
# Expandable Details
# ----------------------
with st.expander("📋 View Detailed Facility Stock Data"):
    st.dataframe(df_filtered.sort_values(by="Stock_Balance_After_Lead"), height=500)

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
