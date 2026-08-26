import os
import io
import requests
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

WFP_RWANDA_CSV_URL = "https://data.humdata.org/dataset/a4a84c1c-81d1-491b-9fbe-1955ae736508/resource/8c22eeb5-cc2e-46bc-8a0d-08b7486b2486/download/wfp_food_prices_rwa.csv"
FALLBACK_DB_URL = "postgresql://neondb_owner:npg_QNeqPho0Eb6g@ep-weathered-wind-axfc5in6-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require"

def sync_wfp_data(conn):
    print("Fetching WFP market price data...")
    res = requests.get(WFP_RWANDA_CSV_URL)
    res.raise_for_status()

    df = pd.read_csv(io.StringIO(res.text), skiprows=[1])
    df = df.rename(columns={'market': 'market_name', 'price': 'price_rwf'})
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    df['price_rwf'] = pd.to_numeric(df['price_rwf'], errors='coerce')

    df = df.dropna(subset=['market_name', 'commodity', 'price_rwf', 'date'])
    df['admin1'] = df['admin1'].fillna('')
    df['admin2'] = df['admin2'].fillna('')
    df['category'] = df['category'].fillna('')
    df['unit'] = df['unit'].fillna('')

    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS market_prices (
            id SERIAL PRIMARY KEY,
            market_name VARCHAR(150),
            admin1 VARCHAR(100),
            admin2 VARCHAR(100),
            commodity VARCHAR(150),
            category VARCHAR(100),
            unit VARCHAR(50),
            price_rwf NUMERIC,
            date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT unique_market_entry UNIQUE (market_name, commodity, date, unit)
        );
    """)
    conn.commit()

    insert_query = """
        INSERT INTO market_prices (market_name, admin1, admin2, commodity, category, unit, price_rwf, date)
        VALUES %s
        ON CONFLICT (market_name, commodity, date, unit) 
        DO UPDATE SET price_rwf = EXCLUDED.price_rwf;
    """

    data_tuples = [
        (row['market_name'], row['admin1'], row['admin2'], row['commodity'], row['category'], row['unit'], row['price_rwf'], row['date'])
        for _, row in df.iterrows()
    ]

    # Optimized bulk payload insertion (10,000 rows per batch)
    execute_values(cursor, insert_query, data_tuples, page_size=10000)
    conn.commit()
    cursor.close()
    print(f"Synced {len(data_tuples)} WFP market price points in bulk!")

def sync_nisr_cpi_weights(conn):
    print("Syncing NISR CPI weight matrix...")
    nisr_cpi_weights = [
        ("Food and non-alcoholic beverages", 35.8, "Food Basket"),
        ("Housing, water, electricity, gas and other fuels", 26.4, "Housing & Utilities"),
        ("Transport", 10.5, "Transport"),
        ("Restaurants and Hotels", 7.2, "Prepared Food"),
        ("Clothing and footwear", 5.1, "Non-Food Basket"),
        ("Furnishings, household equipment", 4.3, "Household Goods"),
        ("Health", 3.0, "Healthcare"),
        ("Education", 2.8, "Education"),
        ("Alcoholic beverages, tobacco and narcotics", 2.3, "Other"),
        ("Miscellaneous goods and services", 1.5, "Services"),
        ("Communication", 0.8, "Communication"),
        ("Recreation and culture", 0.3, "Other")
    ]

    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS nisr_cpi_weights (
            id SERIAL PRIMARY KEY,
            category VARCHAR(150) UNIQUE,
            weight_percentage NUMERIC,
            basket_group VARCHAR(100)
        );
    """)
    conn.commit()

    insert_query = """
        INSERT INTO nisr_cpi_weights (category, weight_percentage, basket_group)
        VALUES %s
        ON CONFLICT (category) 
        DO UPDATE SET weight_percentage = EXCLUDED.weight_percentage, basket_group = EXCLUDED.basket_group;
    """

    execute_values(cursor, insert_query, nisr_cpi_weights)
    conn.commit()
    cursor.close()
    print("NISR CPI weight reference table synchronized.")

def init_village_prices_table(conn):
    print("Initializing local village level prices table...")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS local_village_prices (
            id SERIAL PRIMARY KEY,
            province VARCHAR(100),
            district VARCHAR(100),
            sector VARCHAR(100),
            cell VARCHAR(100),
            village VARCHAR(100),
            commodity VARCHAR(150),
            unit VARCHAR(50),
            price_rwf NUMERIC,
            reporter_name VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    cursor.close()
    print("Local village prices schema verified.")

def fetch_and_sync():
    db_url = os.environ.get("DATABASE_URL") or FALLBACK_DB_URL
    conn = psycopg2.connect(db_url)
    
    sync_wfp_data(conn)
    sync_nisr_cpi_weights(conn)
    init_village_prices_table(conn)
    
    conn.close()
    print("Full system sync completed successfully!")

if __name__ == "__main__":
    fetch_and_sync()
