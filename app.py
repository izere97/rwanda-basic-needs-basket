import os
import streamlit as st
import pandas as pd
import plotly.express as px
import psycopg2

st.set_page_config(page_title="Rwanda Basic Needs Basket", layout="wide")

@st.cache_resource
def init_db():
    # Read Postgres Connection URL from Secrets or Environment
    db_url = st.secrets.get("DATABASE_URL") or os.environ.get("DATABASE_URL")
    
    if not db_url:
        st.error("Missing DATABASE_URL in Streamlit Secrets.")
        st.stop()
        
    return psycopg2.connect(db_url)

try:
    conn = init_db()
except Exception as e:
    st.error(f"Failed to connect to Neon Database: {e}")
    st.stop()

@st.cache_data(ttl=3600)
def load_market_data():
    query = "SELECT * FROM market_prices;"
    return pd.read_sql(query, conn)

st.title("🇷🇼 Rwanda Food Basket & Market Price Dashboard")

try:
    df_prices = load_market_data()
    if df_prices.empty:
        st.warning("Database connected, but `market_prices` table is currently empty.")
    else:
        st.success(f"Successfully loaded {len(df_prices)} market records from Neon!")
        
        # Preprocessing
        df_prices['date'] = pd.to_datetime(df_prices['date'])
        df_prices['price_rwf'] = pd.to_numeric(df_prices['price_rwf'])

        # Sidebar Filters
        st.sidebar.header("Filter Options")
        markets = df_prices['market_name'].dropna().unique()
        selected_market = st.sidebar.selectbox("Select Market", options=markets)
        
        commodities = df_prices['commodity'].dropna().unique()
        selected_commodities = st.sidebar.multiselect(
            "Select Commodities", 
            options=commodities, 
            default=list(commodities[:3]) if len(commodities) >= 3 else list(commodities)
        )

        filtered_df = df_prices[
            (df_prices['market_name'] == selected_market) & 
            (df_prices['commodity'].isin(selected_commodities))
        ]

        # Trend Chart
        st.header("1. Commodity Price Trends")
        if not filtered_df.empty:
            fig = px.line(
                filtered_df, 
                x="date", 
                y="price_rwf", 
                color="commodity", 
                title=f"Price Trends in {selected_market} (RWF)"
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data available for selected filters.")

        # Data Table
        st.header("2. Scraped Market Data Table")
        st.dataframe(df_prices, use_container_width=True)

except Exception as err:
    st.error(f"Error executing SQL query: {err}")
