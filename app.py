import os
import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client, Client

# Page setup
st.set_page_config(page_title="Rwanda Basic Needs Basket", layout="wide")

# Connect to Supabase
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY")
    return create_client(url, key)

supabase = init_supabase()

# Fetch Data Functions
@st.cache_data(ttl=3600)
def load_market_data():
    res = supabase.table("market_prices").select("*").execute()
    return pd.DataFrame(res.data)

@st.cache_data(ttl=3600)
def load_basket_standards():
    res = supabase.table("basket_standards").select("*").execute()
    return pd.DataFrame(res.data)

st.title("🇷🇼 Rwanda Food Basket & Market Price Dashboard")

df_prices = load_market_data()
df_standards = load_basket_standards()

if df_prices.empty:
    st.warning("No price data found in database. Run your GitHub Actions scraper first!")
    st.stop()

# Data Preprocessing
df_prices['date'] = pd.to_datetime(df_prices['date'])
df_prices['price_rwf'] = pd.to_numeric(df_prices['price_rwf'])

# Sidebar Filters
st.sidebar.header("Filter Options")
selected_market = st.sidebar.selectbox("Select Market", options=df_prices['market_name'].unique())
selected_commodities = st.sidebar.multiselect("Select Commodities", options=df_prices['commodity'].unique(), default=df_prices['commodity'].unique()[:3])

filtered_df = df_prices[(df_prices['market_name'] == selected_market) & (df_prices['commodity'].isin(selected_commodities))]

# Key Metrics
st.header("1. Commodity Price Trends")
if not filtered_df.empty:
    fig = px.line(filtered_df, x="date", y="price_rwf", color="commodity", title=f"Price Trends in {selected_market} (RWF)")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No data available for selected filter combination.")

# Basket Cost Calculator Section
st.header("2. Minimum Nutrition Basket Cost Estimator")
if not df_standards.empty:
    st.write("Baseline Daily Nutritional Requirements per Adult (2,100 kcal target):")
    st.dataframe(df_standards, use_container_width=True)
    
    # Calculate latest available price for each basket commodity
    latest_date = df_prices['date'].max()
    latest_prices = df_prices[df_prices['date'] == latest_date].groupby('commodity')['price_rwf'].mean().reset_dict() if not df_prices.empty else {}
    
    # Simple cost calculation
    basket_merge = df_standards.copy()
    basket_merge['latest_avg_price'] = basket_merge['commodity'].map(latest_prices).fillna(0)
    # Price is per kg (1000g), daily cost = (grams / 1000) * price
    basket_merge['daily_cost_rwf'] = (basket_merge['daily_grams_per_adult'] / 1000.0) * basket_merge['latest_avg_price']
    
    total_daily_cost = basket_merge['daily_cost_rwf'].sum()
    total_monthly_cost = total_daily_cost * 30
    
    col1, col2 = st.columns(2)
    col1.metric("Est. Daily Basket Cost / Adult", f"{total_daily_cost:,.0f} RWF")
    col2.metric("Est. Monthly Basket Cost / Adult", f"{total_monthly_cost:,.0f} RWF")
