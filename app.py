import os
import streamlit as st
import pandas as pd
import plotly.express as px
import psycopg2

st.set_page_config(page_title="Rwanda Basic Needs Basket", layout="wide")

@st.cache_resource
def init_db():
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
    query = "SELECT * FROM market_prices ORDER BY date DESC;"
    return pd.read_sql(query, conn)

st.title("🇷🇼 Rwanda Nationwide Market Price Dashboard")

try:
    df_prices = load_market_data()
    if df_prices.empty:
        st.warning("Database connected, but no records were found.")
    else:
        df_prices['date'] = pd.to_datetime(df_prices['date'])
        df_prices['price_rwf'] = pd.to_numeric(df_prices['price_rwf'])

        # Sidebar Regional Filters
        st.sidebar.header("📍 Geographic Filters")
        
        provinces = ["All"] + list(df_prices['admin1'].dropna().unique())
        selected_province = st.sidebar.selectbox("Select Province", options=provinces)
        
        if selected_province != "All":
            filtered_df = df_prices[df_prices['admin1'] == selected_province]
        else:
            filtered_df = df_prices

        districts = ["All"] + list(filtered_df['admin2'].dropna().unique())
        selected_district = st.sidebar.selectbox("Select District", options=districts)

        if selected_district != "All":
            filtered_df = filtered_df[filtered_df['admin2'] == selected_district]

        markets = filtered_df['market_name'].dropna().unique()
        selected_market = st.sidebar.selectbox("Select Market", options=markets)

        filtered_df = filtered_df[filtered_df['market_name'] == selected_market]

        # Commodity Selection
        commodities = filtered_df['commodity'].dropna().unique()
        selected_commodities = st.sidebar.multiselect(
            "Select Commodities", 
            options=commodities, 
            default=list(commodities[:3]) if len(commodities) >= 3 else list(commodities)
        )

        final_df = filtered_df[filtered_df['commodity'].isin(selected_commodities)]

        # Dashboard Visualizations
        st.header(f"1. Price Trends in {selected_market}")
        if not final_df.empty:
            fig = px.line(
                final_df, 
                x="date", 
                y="price_rwf", 
                color="commodity",
                labels={"price_rwf": "Price (RWF)", "date": "Date", "commodity": "Commodity"}
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data found for this selection.")

        st.header("2. Dataset Preview")
        st.dataframe(final_df[['date', 'admin1', 'admin2', 'market_name', 'commodity', 'unit', 'price_rwf']], use_container_width=True)

except Exception as err:
    st.error(f"Error fetching data: {err}")
