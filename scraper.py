import os
import io
import pandas as pd
from supabase import create_client, Client

# Retrieve Supabase credentials from environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase URL or Key in environment variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Official WFP Food Prices dataset URL for Rwanda on HDX
WFP_RWANDA_URL = "https://data.humdata.org/dataset/a4a84c1c-81d1-491b-9fbe-1955ae736508/resource/8c22eeb5-cc2e-46bc-8a0d-08b7486b2486/download/wfp_food_prices_rwa.csv"

def run_scraper():
    print("Fetching WFP Rwanda food prices dataset...")
    
    # Load dataset, skipping the HDX description header (row 1)
    df = pd.read_csv(WFP_RWANDA_URL, skiprows=[1], low_memory=False)
    
    # Filter for standard retail prices in Rwandan Francs (RWF)
    df_filtered = df[(df['priceflag'] == 'actual') & (df['currency'] == 'RWF')].copy()
    
    # Get the latest 200 records to insert
    latest_records = df_filtered.tail(200)
    
    inserted_count = 0
    for _, row in latest_records.iterrows():
        try:
            record = {
                "market_name": str(row['admin2']) if pd.notna(row['admin2']) else str(row['market']),
                "commodity": str(row['commodity']),
                "price_rwf": float(row['price']),
                "unit": str(row['unit']),
                "date": str(row['date'])
            }
            
            # Upsert into Supabase market_prices table
            supabase.table("market_prices").upsert(record, on_conflict="market_name,commodity,date").execute()
            inserted_count += 1
        except Exception as e:
            print(f"Skipping row due to error: {e}")

    print(f"Successfully processed and synced {inserted_count} market price records!")

if __name__ == "__main__":
    run_scraper()
