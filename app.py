import os
import streamlit as st
import pandas as pd
import plotly.express as px
import psycopg2

st.set_page_config(page_title="Custom Basic Needs Basket Dashboard", layout="wide")

def get_db_connection():
    db_url = st.secrets.get("DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        st.error("Missing DATABASE_URL configuration in Streamlit Secrets.")
        st.stop()
    return psycopg2.connect(db_url)

@st.cache_data(ttl=60)
def load_custom_data():
    conn = get_db_connection()
    try:
        df = pd.read_sql("SELECT * FROM local_village_prices ORDER BY created_at DESC;", conn)
        return df
    finally:
        conn.close()

st.title("🇷🇼 Custom Regional Basic Needs Basket Dashboard")
st.markdown("Calculate family basic needs basket costs strictly using your collected market data.")

try:
    df_local = load_custom_data()

    if df_local.empty:
        st.info("No price data found in your database yet. Use the 'Report / Add Prices' tab to start logging commodity prices.")

    tab1, tab2, tab3 = st.tabs([
        "📊 Basic Basket Calculator", 
        "➕ Report / Add Prices", 
        "✏️ Edit & Manage Database"
    ])

    # TAB 1: REGIONAL BASIC NEEDS BASKET CALCULATOR
    with tab1:
        st.header("1. Filter Region & Calculate Basket")
        
        if not df_local.empty:
            # Regional Filters
            c_prov, c_dist, c_sec = st.columns(3)
            with c_prov:
                provinces = ["All"] + sorted([p for p in df_local['province'].dropna().unique() if p])
                sel_prov = st.selectbox("Province", provinces)
            
            filtered_df = df_local if sel_prov == "All" else df_local[df_local['province'] == sel_prov]

            with c_dist:
                districts = ["All"] + sorted([d for d in filtered_df['district'].dropna().unique() if d])
                sel_dist = st.selectbox("District", districts)

            if sel_dist != "All":
                filtered_df = filtered_df[filtered_df['district'] == sel_dist]

            with c_sec:
                sectors = ["All"] + sorted([s for s in filtered_df['sector'].dropna().unique() if s])
                sel_sec = st.selectbox("Sector", sectors)

            if sel_sec != "All":
                filtered_df = filtered_df[filtered_df['sector'] == sel_sec]

            st.divider()

            # Household Size & Quantities Configuration
            st.subheader("2. Household & Monthly Food Consumption Settings")
            col_hh, col_weight = st.columns(2)
            
            with col_hh:
                household_size = st.number_input("Household Size (Number of People)", min_value=1, value=5, step=1)
            with col_weight:
                food_weight_pct = st.slider("Food Expenditure Share of Total Needs (%)", min_value=20, max_value=60, value=36, help="Standard NISR weight is ~35.8%")

            # Calculate Median Unit Prices per Commodity in Selected Region
            latest_prices = filtered_df.groupby('commodity')['price_rwf'].median().reset_index()

            st.subheader("3. Monthly Food Basket Cost")
            
            # Default per-person monthly baseline scaled by household size
            base_quantities = {
                'Beans': 3.0 * household_size,
                'Rice': 2.0 * household_size,
                'Maize flour': 2.5 * household_size,
                'Potatoes (Irish)': 5.0 * household_size,
                'Cassava flour': 2.0 * household_size,
                'Cooking oil': 0.6 * household_size
            }

            basket_items = []
            total_food_cost = 0

            # Dynamic calculation for matched commodities
            for comm_name, qty in base_quantities.items():
                match = latest_prices[latest_prices['commodity'].str.contains(comm_name, case=False, na=False)]
                if not match.empty:
                    unit_price = match['price_rwf'].values[0]
                    monthly_cost = unit_price * qty
                    total_food_cost += monthly_cost
                    basket_items.append({
                        'Commodity': comm_name,
                        'Required Monthly Qty': f"{qty:.1f} kg/L",
                        'Local Median Price (RWF)': f"{unit_price:,.2f}",
                        'Subtotal Cost (RWF)': monthly_cost
                    })

            if basket_items:
                st.dataframe(pd.DataFrame(basket_items), use_container_width=True)
            else:
                st.warning("No matching commodities found for the baseline basket in this selection. Add prices for Beans, Rice, Maize flour, Potatoes, Cassava flour, or Cooking oil.")

            # Calculate Total Non-Food & Full Basic Needs
            if total_food_cost > 0:
                food_weight_ratio = food_weight_pct / 100.0
                estimated_total_needs = total_food_cost / food_weight_ratio
                estimated_non_food = estimated_total_needs - total_food_cost

                st.subheader(f"4. Summary Basic Needs Cost ({household_size}-Person Family)")
                m1, m2, m3 = st.columns(3)
                m1.metric("Monthly Food Basket", f"{total_food_cost:,.0f} RWF")
                m2.metric("Est. Non-Food Needs (Rent, Utilities, etc.)", f"{estimated_non_food:,.0f} RWF")
                m3.metric("Total Minimum Basic Needs", f"{estimated_total_needs:,.0f} RWF")

                # Breakdown Chart
                cost_summary_df = pd.DataFrame({
                    "Category": ["Food Basket", "Non-Food Needs (Rent, Healthcare, Utilities)"],
                    "Cost (RWF)": [total_food_cost, estimated_non_food]
                })
                fig_pie = px.pie(cost_summary_df, names="Category", values="Cost (RWF)", title="Basic Needs Expenditure Share")
                st.plotly_chart(fig_pie, use_container_width=True)

    # TAB 2: REPORT / ADD NEW LOCAL PRICES
    with tab2:
        st.header("Report / Submit Price Entry")
        with st.form("add_price_form"):
            f1, f2, f3 = st.columns(3)
            with f1:
                province_in = st.text_input("Province (e.g., Northern Province)")
                district_in = st.text_input("District (e.g., Musanze)")
            with f2:
                sector_in = st.text_input("Sector (e.g., Muhoza)")
                cell_in = st.text_input("Cell (e.g., Ruhengeri)")
            with f3:
                village_in = st.text_input("Village (e.g., Nyamagumba)")
                reporter_in = st.text_input("Reporter / Market Name")

            p1, p2, p3 = st.columns(3)
            with p1:
                commodity_in = st.text_input("Commodity (e.g., Beans)")
            with p2:
                unit_in = st.text_input("Unit (e.g., 1 KG)", value="1 KG")
            with p3:
                price_in = st.number_input("Price (RWF)", min_value=1.0, step=50.0)

            submit_btn = st.form_submit_button("Save Price Entry")

        if submit_btn:
            if not (district_in and sector_in and commodity_in):
                st.error("District, Sector, and Commodity fields are required.")
            else:
                conn_add = get_db_connection()
                try:
                    cursor = conn_add.cursor()
                    cursor.execute("""
                        INSERT INTO local_village_prices (province, district, sector, cell, village, commodity, unit, price_rwf, reporter_name)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """, (province_in, district_in, sector_in, cell_in, village_in, commodity_in, unit_in, price_in, reporter_in))
                    conn_add.commit()
                    cursor.close()
                finally:
                    conn_add.close()

                st.success(f"Added {commodity_in} at {price_in} RWF for {sector_in} Sector!")
                st.cache_data.clear()

    # TAB 3: EDIT & MANAGE DATABASE
    with tab3:
        st.header("✏️ Edit & Update Your Database")
        st.markdown("Modify prices directly inside the table and click **Save Changes**.")

        if not df_local.empty:
            edited_df = st.data_editor(
                df_local.copy(),
                key="custom_db_editor",
                num_rows="dynamic",
                use_container_width=True,
                column_config={"id": st.column_config.NumberColumn(disabled=True)}
            )

            if st.button("Save Changes to Database"):
                conn_edit = get_db_connection()
                try:
                    cursor = conn_edit.cursor()
                    for idx, row in edited_df.iterrows():
                        cursor.execute("""
                            UPDATE local_village_prices 
                            SET price_rwf = %s, commodity = %s, unit = %s, province = %s, district = %s, sector = %s, cell = %s, village = %s
                            WHERE id = %s;
                        """, (row['price_rwf'], row['commodity'], row['unit'], row['province'], row['district'], row['sector'], row['cell'], row['village'], row['id']))
                    conn_edit.commit()
                    cursor.close()
                    st.success("Database successfully updated!")
                    st.cache_data.clear()
                finally:
                    conn_edit.close()

except Exception as err:
    st.error(f"Error loading application: {err}")
