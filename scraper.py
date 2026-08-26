import os
import io
import requests
import pandas as pd
import psycopg2

# HDX WFP Rwanda Food Prices Direct CSV URL
WFP_RWANDA_CSV_URL = "https://data.humdata.org/dataset/a4a84c1c-81d1-491b-9fbe-1955ae736508/resource/8c22eeb5-cc2e-46bc-8a0d-08b7486b2486/download/wfp_food_prices_rwa.csv"

def fetch_and_sync():
    print("Fetching nationwide Rwanda price data from HDX/WFP...")
    res = requests.get(WFP_RWANDA_CSV_URL)
    res.raise_for_status()

    # HDX CSVs include a metadata header on row 1; skip row 1
    df = pd.read_csv(io.StringIO(res.text), skiprows=[1])

    # Clean and rename columns to fit our table structure
    # Columns in dataset: date, admin1, admin2, market, latitude, longitude, category, commodity, unit, price, usdprice
    df = df.rename(columns={
        'market': 'market_name',
        'price': 'price_rwf'
    })

    # Keep relevant fields
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    df['price_rwf'] = pd.to_numeric(df['price_rwf'], errors='coerce')
    
    # Filter out missing records
    df = df.dropna(subset=['market_name', 'commodity', 'price_rwf', 'date'])

    print(f"Parsed {len(df)} price data points across Rwanda.")

    # Connect to Neon
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is missing.")

    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()

    # Ensure table structure accommodates full geographic data
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

    # Upsert data batch into database
    insert_query = """
        INSERT INTO market_prices (market_name, admin1, admin2, commodity, category, unit, price_rwf, date)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (market_name, commodity, date, unit) 
        DO UPDATE SET price_rwf = EXCLUDED.price_rwf;
    """

    data_tuples = [
        (
            row['market_name'], 
            row.get('admin1', ''), 
            row.get('admin2', ''), 
            row['commodity'], 
            row.get('category', ''), 
            row.get('unit', ''), 
            row['price_rwf'], 
            row['date']
        )
        for _, row in df.iterrows()
    ]

    cursor.executemany(insert_query, data_tuples)
    conn.commit()
    cursor.close()
    conn.close()

    print("Data synchronization complete!")

if __name__ == "__main__":
    fetch_and_sync()
