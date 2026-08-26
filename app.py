import os
import streamlit as st
import pandas as pd
import plotly.express as px
import psycopg2

st.set_page_config(page_title="Rwanda Basic Needs Basket & Market Price Dashboard", layout="wide")

def get_db_connection():
    db_url = st.secrets.get("DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        st.error("Missing DATABASE_URL configuration in Streamlit Secrets.")
        st.stop()
    return psycopg2.connect(db_url)

@st.cache_data(ttl=300)
def load_all_data():
    conn = get_db_connection()
    try:
        df_wfp = pd.read_sql("SELECT * FROM market_prices ORDER BY date DESC;", conn)
        df_nisr = pd.read_sql("SELECT * FROM nisr_cpi_weights ORDER BY weight_percentage DESC;", conn)
        df_village = pd.read_sql("SELECT * FROM local_village_prices ORDER BY created_at DESC;", conn)
        return df_wfp, df_nisr, df_village
    finally:
        conn.close()

st.title("🇷🇼 Rwanda Basic Needs Basket & Market Price Dashboard")

try:
    df_wfp, df_nisr, df_village = load_all_data()

    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Official WFP & NISR Metrics", 
        "🏡 Sector, Cell & Village Local Data",
        "🎯 Custom Local Basket Calculator",
        "✏️ Edit & Update Prices"
    ])

    # TAB 1: OFFICIAL DATA
    with tab1:
        st.header("Official Market Data & Basic Needs Basket Engine")
        
        if df_wfp.empty:
            st.warning("No official WFP market records found.")
        else:
            df_wfp['date'] = pd.to_datetime(df_wfp['date'])
            df_wfp['price_rwf'] = pd.to_numeric(df_wfp['price_rwf'])

            col_a, col_b = st.columns(2)
            with col_a:
                provinces = ["All"] + sorted([p for p in df_wfp['admin1'].unique() if p])
                selected_province = st.selectbox("Select Province", options=provinces)
            with col_b:
                filtered_wfp = df_wfp if selected_province == "All" else df_wfp[df_wfp['admin1'] == selected_province]
                districts = ["All"] + sorted([d for d in filtered_wfp['admin2'].unique() if d])
                selected_district = st.selectbox("Select District", options=districts)

            if selected_district != "All":
                filtered_wfp = filtered_wfp[filtered_wfp['admin2'] == selected_district]

            # NISR Weights
            st.subheader("1. NISR CPI Reference Matrix")
            col1, col2 = st.columns([1, 1])
            with col1:
                st.dataframe(df_nisr, use_container_width=True)
            with col2:
                fig_pie = px.pie(df_nisr, names="category", values="weight_percentage", title="NISR Basket Weights (%)")
                st.plotly_chart(fig_pie, use_container_width=True)

            # Basic Needs Basket Engine
            st.subheader("2. Minimum Basic Needs Basket (Household of 5)")
            latest_prices = filtered_wfp.groupby('commodity')['price_rwf'].median().reset_index()
            basket_quantities = {'Beans': 15, 'Rice': 10, 'Maize flour': 12, 'Potatoes (Irish)': 25, 'Cassava flour': 10, 'Cooking oil': 3}

            basket_items = []
            total_food_cost = 0
            for item, qty in basket_quantities.items():
                match = latest_prices[latest_prices['commodity'].str.contains(item, case=False, na=False)]
                if not match.empty:
                    unit_price = match['price_rwf'].values[0]
                    monthly_cost = unit_price * qty
                    total_food_cost += monthly_cost
                    basket_items.append({'Item': item, 'Monthly Quantity': f"{qty} kg/L", 'Median Unit Price (RWF)': f"{unit_price:,.2f}", 'Estimated Cost (RWF)': monthly_cost})

            st.dataframe(pd.DataFrame(basket_items), use_container_width=True)

            if total_food_cost > 0:
                food_weight = 0.358
                estimated_total = total_food_cost / food_weight
                c1, c2, c3 = st.columns(3)
                c1.metric("Monthly Food Basket", f"{total_food_cost:,.0f} RWF")
                c2.metric("NISR Food Weight", f"{food_weight * 100:.1f}%")
                c3.metric("Est. Total Basic Needs", f"{estimated_total:,.0f} RWF")

            # WFP Trends
            st.subheader("3. WFP Market Price Trends")
            all_commodities = filtered_wfp['commodity'].dropna().unique()
            selected_commodities = st.multiselect("Select Commodities to Graph", options=all_commodities, default=list(all_commodities[:3]) if len(all_commodities) >= 3 else list(all_commodities))
            graph_df = filtered_wfp[filtered_wfp['commodity'].isin(selected_commodities)]
            if not graph_df.empty:
                fig_line = px.line(graph_df, x="date", y="price_rwf", color="commodity", title="Official Price Trends (RWF)")
                st.plotly_chart(fig_line, use_container_width=True)

    # TAB 2: LOCAL SUB-DISTRICT DATA
    with tab2:
        st.header("Custom Local Data Collection (Sector, Cell, Village Level)")
        
        st.subheader("1. Report Local Market Price")
        with st.form("local_village_form"):
            f_col1, f_col2, f_col3 = st.columns(3)
            with f_col1:
                province_in = st.text_input("Province (e.g., Northern Province)")
                district_in = st.text_input("District (e.g., Musanze)")
            with f_col2:
                sector_in = st.text_input("Sector (e.g., Muhoza)")
                cell_in = st.text_input("Cell (e.g., Ruhengeri)")
            with f_col3:
                village_in = st.text_input("Village (e.g., Nyamagumba)")
                reporter_in = st.text_input("Reporter / Market Name")

            p_col1, p_col2, p_col3 = st.columns(3)
            with p_col1:
                commodity_in = st.text_input("Commodity (e.g., Beans)")
            with p_col2:
                unit_in = st.text_input("Unit (e.g., 1 KG)", value="1 KG")
            with p_col3:
                price_in = st.number_input("Price (RWF)", min_value=1.0, step=50.0)

            submit_btn = st.form_submit_button("Submit Local Price Report")

        if submit_btn:
            if not (district_in and sector_in and village_in and commodity_in):
                st.error("Please fill in District, Sector, Village, and Commodity fields.")
            else:
                conn_submit = get_db_connection()
                try:
                    cursor = conn_submit.cursor()
                    cursor.execute("""
                        INSERT INTO local_village_prices (province, district, sector, cell, village, commodity, unit, price_rwf, reporter_name)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """, (province_in, district_in, sector_in, cell_in, village_in, commodity_in, unit_in, price_in, reporter_in))
                    conn_submit.commit()
                    cursor.close()
                finally:
                    conn_submit.close()

                st.success(f"Reported {price_in} RWF for {commodity_in} in {village_in} Village ({sector_in} Sector)!")
                st.cache_data.clear()

        st.subheader("2. Local Village Price Database")
        if df_village.empty:
            st.info("No local village entries recorded yet. Use the form above to submit data.")
        else:
            st.dataframe(df_village, use_container_width=True)

    # TAB 3: CUSTOM LOCAL BASKET CALCULATOR
    with tab3:
        st.header("🎯 Regional Basic Needs Basket Calculator (Custom Data)")
        st.markdown("Compute family cost-of-living metrics strictly using your sub-district local price inputs.")

        if df_village.empty:
            st.info("No local price entries available yet. Submit data in Tab 2 to enable calculations.")
        else:
            # 5-Level Administrative Cascading Filters
            st.subheader("1. Select Geographic Location")
            f1, f2, f3, f4, f5 = st.columns(5)
            
            df_calc = df_village.copy()
            
            with f1:
                prov_opts = ["All"] + sorted([p for p in df_calc['province'].dropna().unique() if p])
                sel_prov = st.selectbox("Province", prov_opts, key="calc_prov")
            if sel_prov != "All":
                df_calc = df_calc[df_calc['province'] == sel_prov]

            with f2:
                dist_opts = ["All"] + sorted([d for d in df_calc['district'].dropna().unique() if d])
                sel_dist = st.selectbox("District", dist_opts, key="calc_dist")
            if sel_dist != "All":
                df_calc = df_calc[df_calc['district'] == sel_dist]

            with f3:
                sec_opts = ["All"] + sorted([s for s in df_calc['sector'].dropna().unique() if s])
                sel_sec = st.selectbox("Sector", sec_opts, key="calc_sec")
            if sel_sec != "All":
                df_calc = df_calc[df_calc['sector'] == sel_sec]

            with f4:
                cell_opts = ["All"] + sorted([c for c in df_calc['cell'].dropna().unique() if c])
                sel_cell = st.selectbox("Cell", cell_opts, key="calc_cell")
            if sel_cell != "All":
                df_calc = df_calc[df_calc['cell'] == sel_cell]

            with f5:
                vil_opts = ["All"] + sorted([v for v in df_calc['village'].dropna().unique() if v])
                sel_vil = st.selectbox("Village", vil_opts, key="calc_vil")
            if sel_vil != "All":
                df_calc = df_calc[df_calc['village'] == sel_vil]

            st.divider()

            # Household Parameters
            st.subheader("2. Family Parameters")
            c_hh, c_weight = st.columns(2)
            with c_hh:
                household_members = st.number_input("Household Size (Persons)", min_value=1, value=5, step=1)
            with c_weight:
                food_weight_share = st.slider("Food Expenditure Weight (%)", min_value=20, max_value=60, value=36, help="Standard NISR food expenditure weight is ~35.8%")

            # Compute Local Basket
            st.subheader("3. Calculated Monthly Basic Needs Basket")
            
            # Per-person base monthly quantities scaled by family size
            basket_rules = {
                'Beans': 3.0 * household_members,
                'Rice': 2.0 * household_members,
                'Maize flour': 2.5 * household_members,
                'Potatoes': 5.0 * household_members,
                'Cassava flour': 2.0 * household_members,
                'Cooking oil': 0.6 * household_members
            }

            local_medians = df_calc.groupby('commodity')['price_rwf'].median().reset_index()

            calc_basket_items = []
            custom_food_cost = 0

            for item, qty in basket_rules.items():
                match = local_medians[local_medians['commodity'].str.contains(item, case=False, na=False)]
                if not match.empty:
                    u_price = match['price_rwf'].values[0]
                    subtotal = u_price * qty
                    custom_food_cost += subtotal
                    calc_basket_items.append({
                        'Commodity': item,
                        'Monthly Quantity': f"{qty:.1f} kg/L",
                        'Local Median Price (RWF)': f"{u_price:,.2f}",
                        'Subtotal (RWF)': subtotal
                    })

            if calc_basket_items:
                st.dataframe(pd.DataFrame(calc_basket_items), use_container_width=True)
            else:
                st.warning("No price entries match the baseline basket items in this location selection. Add price data for Beans, Rice, Maize flour, Potatoes, Cassava flour, or Cooking oil.")

            if custom_food_cost > 0:
                food_ratio = food_weight_share / 100.0
                total_cost_of_living = custom_food_cost / food_ratio
                non_food_cost = total_cost_of_living - custom_food_cost

                m1, m2, m3 = st.columns(3)
                m1.metric("Monthly Food Basket", f"{custom_food_cost:,.0f} RWF")
                m2.metric("Est. Non-Food Expenses (Rent, Utilities, etc.)", f"{non_food_cost:,.0f} RWF")
                m3.metric("Total Cost of Living", f"{total_cost_of_living:,.0f} RWF")

                chart_df = pd.DataFrame({
                    "Category": ["Food Basket", "Non-Food Needs"],
                    "Cost (RWF)": [custom_food_cost, non_food_cost]
                })
                fig_breakdown = px.pie(chart_df, names="Category", values="Cost (RWF)", title="Expenditure Breakdown")
                st.plotly_chart(fig_breakdown, use_container_width=True)

    # TAB 4: PRICE MODIFICATION & EDITING ENGINE
    with tab4:
        st.header("✏️ Price Modification Engine")
        st.markdown("Edit existing commodity prices directly below and click **Save Modifications** to update the database.")

        dataset_choice = st.radio("Select Target Dataset to Edit", ["Local Sub-District / Village Prices", "Official WFP Market Prices"], horizontal=True)

        if dataset_choice == "Local Sub-District / Village Prices":
            if df_village.empty:
                st.info("No local village records available to edit.")
            else:
                st.subheader("Edit Village Level Entries")
                editable_village = df_village.copy()
                edited_village_df = st.data_editor(
                    editable_village,
                    key="village_editor",
                    num_rows="dynamic",
                    use_container_width=True,
                    column_config={"id": st.column_config.NumberColumn(disabled=True)}
                )

                if st.button("Save Village Price Changes"):
                    conn_edit = get_db_connection()
                    try:
                        cursor = conn_edit.cursor()
                        for idx, row in edited_village_df.iterrows():
                            cursor.execute("""
                                UPDATE local_village_prices 
                                SET price_rwf = %s, commodity = %s, unit = %s, sector = %s, cell = %s, village = %s
                                WHERE id = %s;
                            """, (row['price_rwf'], row['commodity'], row['unit'], row['sector'], row['cell'], row['village'], row['id']))
                        conn_edit.commit()
                        cursor.close()
                        st.success("Successfully updated local village prices!")
                        st.cache_data.clear()
                    finally:
                        conn_edit.close()

        else:
            if df_wfp.empty:
                st.info("No official market records available to edit.")
            else:
                st.subheader("Filter & Update Official WFP Market Prices")
                
                select_comm = st.selectbox("Select Commodity to Modify", options=sorted(df_wfp['commodity'].dropna().unique()))
                filter_wfp_edit = df_wfp[df_wfp['commodity'] == select_comm].head(100).copy()
                
                edited_wfp_df = st.data_editor(
                    filter_wfp_edit,
                    key="wfp_editor",
                    num_rows="fixed",
                    use_container_width=True,
                    column_config={"id": st.column_config.NumberColumn(disabled=True)}
                )

                if st.button("Save Official WFP Price Changes"):
                    conn_edit = get_db_connection()
                    try:
                        cursor = conn_edit.cursor()
                        for idx, row in edited_wfp_df.iterrows():
                            cursor.execute("""
                                UPDATE market_prices 
                                SET price_rwf = %s
                                WHERE id = %s;
                            """, (row['price_rwf'], row['id']))
                        conn_edit.commit()
                        cursor.close()
                        st.success(f"Updated price entries for {select_comm}!")
                        st.cache_data.clear()
                    finally:
                        conn_edit.close()

except Exception as err:
    st.error(f"Error loading application: {err}")
