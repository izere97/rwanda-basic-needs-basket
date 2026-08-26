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
        "🏡 Report & Store Local Data",
        "🎯 Complete BNB & Cost-of-Living Calculator",
        "✏️ Edit Database Prices"
    ])

    # -----------------------------------------------------------------------------
    # TAB 1: OFFICIAL WFP & NISR METRICS
    # -----------------------------------------------------------------------------
    with tab1:
        st.header("Official Market Data & NISR Benchmarks")
        if df_wfp.empty:
            st.warning("No official WFP market records found.")
        else:
            df_wfp['date'] = pd.to_datetime(df_wfp['date'])
            df_wfp['price_rwf'] = pd.to_numeric(df_wfp['price_rwf'])

            col_a, col_b = st.columns(2)
            with col_a:
                provinces = ["All"] + sorted([p for p in df_wfp['admin1'].unique() if p])
                selected_province = st.selectbox("Select Province", options=provinces, key="tab1_prov")
            with col_b:
                filtered_wfp = df_wfp if selected_province == "All" else df_wfp[df_wfp['admin1'] == selected_province]
                districts = ["All"] + sorted([d for d in filtered_wfp['admin2'].unique() if d])
                selected_district = st.selectbox("Select District", options=districts, key="tab1_dist")

            if selected_district != "All":
                filtered_wfp = filtered_wfp[filtered_wfp['admin2'] == selected_district]

            st.subheader("1. NISR CPI Reference Matrix")
            col1, col2 = st.columns([1, 1])
            with col1:
                st.dataframe(df_nisr, use_container_width=True)
            with col2:
                fig_pie = px.pie(df_nisr, names="category", values="weight_percentage", title="NISR Basket Weights (%)")
                st.plotly_chart(fig_pie, use_container_width=True)

            st.subheader("2. WFP Market Price Trends")
            all_commodities = filtered_wfp['commodity'].dropna().unique()
            selected_commodities = st.multiselect("Select Commodities to Graph", options=all_commodities, default=list(all_commodities[:3]) if len(all_commodities) >= 3 else list(all_commodities))
            graph_df = filtered_wfp[filtered_wfp['commodity'].isin(selected_commodities)]
            if not graph_df.empty:
                fig_line = px.line(graph_df, x="date", y="price_rwf", color="commodity", title="Official Price Trends (RWF)")
                st.plotly_chart(fig_line, use_container_width=True)

    # -----------------------------------------------------------------------------
    # TAB 2: LOCAL SUB-DISTRICT REPORTING & DATABASE
    # -----------------------------------------------------------------------------
    with tab2:
        st.header("Custom Local Data Collection")
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

                st.success(f"Reported {price_in} RWF for {commodity_in} in {village_in} Village!")
                st.cache_data.clear()

        st.subheader("2. Local Village Price Database")
        if df_village.empty:
            st.info("No local village entries recorded yet.")
        else:
            st.dataframe(df_village, use_container_width=True)

    # -----------------------------------------------------------------------------
    # TAB 3: COMPLETE BNB & COST-OF-LIVING CALCULATOR (FOOD & NON-FOOD LIST)
    # -----------------------------------------------------------------------------
    with tab3:
        st.header("🎯 Comprehensive Basic Needs Basket & Cost of Living Engine")
        st.markdown("Select location filters, configure family size, enter commodity prices, and calculate overall cost of living.")

        # 1. Five Administrative Level Geographic Cascade
        st.subheader("1. Exact Geographic Location Selection")
        g1, g2, g3, g4, g5 = st.columns(5)
        df_calc = df_village.copy() if not df_village.empty else pd.DataFrame(columns=['province', 'district', 'sector', 'cell', 'village', 'commodity', 'price_rwf'])

        with g1:
            prov_opts = ["All"] + (sorted([p for p in df_calc['province'].dropna().unique() if p]) if not df_calc.empty else [])
            sel_prov = st.selectbox("Province", prov_opts, key="bnb_prov")
        if sel_prov != "All" and not df_calc.empty:
            df_calc = df_calc[df_calc['province'] == sel_prov]

        with g2:
            dist_opts = ["All"] + (sorted([d for d in df_calc['district'].dropna().unique() if d]) if not df_calc.empty else [])
            sel_dist = st.selectbox("District", dist_opts, key="bnb_dist")
        if sel_dist != "All" and not df_calc.empty:
            df_calc = df_calc[df_calc['district'] == sel_dist]

        with g3:
            sec_opts = ["All"] + (sorted([s for s in df_calc['sector'].dropna().unique() if s]) if not df_calc.empty else [])
            sel_sec = st.selectbox("Sector", sec_opts, key="bnb_sec")
        if sel_sec != "All" and not df_calc.empty:
            df_calc = df_calc[df_calc['sector'] == sel_sec]

        with g4:
            cell_opts = ["All"] + (sorted([c for c in df_calc['cell'].dropna().unique() if c]) if not df_calc.empty else [])
            sel_cell = st.selectbox("Cell", cell_opts, key="bnb_cell")
        if sel_cell != "All" and not df_calc.empty:
            df_calc = df_calc[df_calc['cell'] == sel_cell]

        with g5:
            vil_opts = ["All"] + (sorted([v for v in df_calc['village'].dropna().unique() if v]) if not df_calc.empty else [])
            sel_vil = st.selectbox("Village", vil_opts, key="bnb_vil")
        if sel_vil != "All" and not df_calc.empty:
            df_calc = df_calc[df_calc['village'] == sel_vil]

        # 2. Family Parameters & Macro-Weight Ratios
        st.subheader("2. Family Parameters & NISR Weight Ratio")
        p1, p2 = st.columns(2)
        with p1:
            hh_members = st.number_input("Household Size (Persons)", min_value=1, value=5, step=1, key="bnb_hh_size")
        with p2:
            food_share_pct = st.slider(
                "NISR Food Expenditure Share (%)", 
                min_value=20.0, max_value=60.0, value=35.8, step=0.1,
                help="National Institute of Statistics of Rwanda benchmark food allocation ratio (~35.8%)."
            )

        # 3. Master List of Essential Food & Non-Food Items (Standard Monthly Base per 5 Household Members)
        scale_ratio = hh_members / 5.0
        
        default_bnb_items = [
            # --- FOOD ITEMS ---
            {"Category": "Food (Staples)", "Item": "Dry Beans (Ibibonobono)", "Standard Unit": "1 KG", "Monthly Qty": 15.0 * scale_ratio, "Default Price": 900.0},
            {"Category": "Food (Staples)", "Item": "Rice (Umuceri)", "Standard Unit": "1 KG", "Monthly Qty": 10.0 * scale_ratio, "Default Price": 1400.0},
            {"Category": "Food (Staples)", "Item": "Maize Flour (Ufu w'ibigori)", "Standard Unit": "1 KG", "Monthly Qty": 12.0 * scale_ratio, "Default Price": 800.0},
            {"Category": "Food (Staples)", "Item": "Irish Potatoes (Ibirayi)", "Standard Unit": "1 KG", "Monthly Qty": 25.0 * scale_ratio, "Default Price": 450.0},
            {"Category": "Food (Staples)", "Item": "Cassava Flour (Ufu w'imyumbati)", "Standard Unit": "1 KG", "Monthly Qty": 10.0 * scale_ratio, "Default Price": 600.0},
            {"Category": "Food (Fats)", "Item": "Cooking Oil (Amavuta yo guteka)", "Standard Unit": "1 Liter", "Monthly Qty": 3.0 * scale_ratio, "Default Price": 2500.0},
            {"Category": "Food (Proteins)", "Item": "Fresh Milk (Amata)", "Standard Unit": "1 Liter", "Monthly Qty": 15.0 * scale_ratio, "Default Price": 600.0},
            {"Category": "Food (Fresh Produce)", "Item": "Vegetables & Tomatoes (Imboga n'inyanya)", "Standard Unit": "1 KG", "Monthly Qty": 12.0 * scale_ratio, "Default Price": 700.0},
            {"Category": "Food (Essentials)", "Item": "Iodized Salt (Umunyu)", "Standard Unit": "1 KG", "Monthly Qty": 1.0 * scale_ratio, "Default Price": 400.0},
            {"Category": "Food (Essentials)", "Item": "Sugar (Isukari)", "Standard Unit": "1 KG", "Monthly Qty": 2.0 * scale_ratio, "Default Price": 1500.0},
            
            # --- NON-FOOD ITEMS (NFI) & SERVICES ---
            {"Category": "Non-Food (Energy)", "Item": "Charcoal / Fuelwood (Amakara)", "Standard Unit": "1 Large Sack", "Monthly Qty": 1.5 * scale_ratio, "Default Price": 12000.0},
            {"Category": "Non-Food (Hygiene)", "Item": "Laundry Bar Soap (Isabune)", "Standard Unit": "1 Bar", "Monthly Qty": 5.0 * scale_ratio, "Default Price": 1000.0},
            {"Category": "Non-Food (Hygiene)", "Item": "Bathing Soap & Toothpaste", "Standard Unit": "Monthly Set", "Monthly Qty": 1.0 * scale_ratio, "Default Price": 3000.0},
            {"Category": "Non-Food (Housing)", "Item": "House Rent (Inzu)", "Standard Unit": "Monthly Flat Rate", "Monthly Qty": 1.0, "Default Price": 35000.0},
            {"Category": "Non-Food (Utilities)", "Item": "Water Supply Fees (Azi)", "Standard Unit": "Monthly Estimate", "Monthly Qty": 1.0, "Default Price": 4000.0},
            {"Category": "Non-Food (Utilities)", "Item": "Electricity & Lighting (Mutagatifu)", "Standard Unit": "Monthly Estimate", "Monthly Qty": 1.0, "Default Price": 5000.0},
            {"Category": "Non-Food (Healthcare)", "Item": "Mutuelle de Santé Allocation", "Standard Unit": "Monthly Person Share", "Monthly Qty": 1.0 * hh_members, "Default Price": 3000.0},
            {"Category": "Non-Food (Services)", "Item": "Public Transport & Airtime", "Standard Unit": "Monthly Estimate", "Monthly Qty": 1.0, "Default Price": 10000.0}
        ]

        # Auto-population from stored database values if present
        if not df_calc.empty:
            db_medians = df_calc.groupby('commodity')['price_rwf'].median().to_dict()
            for row in default_bnb_items:
                for db_comm, db_price in db_medians.items():
                    if db_comm.lower() in row['Item'].lower():
                        row['Default Price'] = float(db_price)
                        break

        df_input_base = pd.DataFrame(default_bnb_items)
        df_input_base.rename(columns={"Default Price": "Entered Unit Price (RWF)"}, inplace=True)

        st.subheader("3. Comprehensive Price Entry Table (Food + Non-Food)")
        st.caption("Update unit prices directly in the grid below. Monthly totals recalculate automatically.")

        edited_bnb_df = st.data_editor(
            df_input_base,
            key="bnb_data_editor",
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "Entered Unit Price (RWF)": st.column_config.NumberColumn("Entered Unit Price (RWF)", min_value=0.0, format="%d RWF"),
                "Monthly Qty": st.column_config.NumberColumn("Monthly Qty", format="%.1f"),
            }
        )

        edited_bnb_df['Total Monthly Cost (RWF)'] = edited_bnb_df['Monthly Qty'] * edited_bnb_df['Entered Unit Price (RWF)']
        
        food_total = edited_bnb_df[edited_bnb_df['Category'].str.startswith('Food')]['Total Monthly Cost (RWF)'].sum()
        non_food_direct = edited_bnb_df[edited_bnb_df['Category'].str.startswith('Non-Food')]['Total Monthly Cost (RWF)'].sum()
        direct_grand_total = food_total + non_food_direct

        # Mathematical Expenditure Weight Calculations
        food_weight_ratio = food_share_pct / 100.0
        weighted_grand_total = food_total / food_weight_ratio if food_weight_ratio > 0 else 0
        non_food_weighted = weighted_grand_total - food_total

        st.divider()

        # 4. Comparative Calculation Options
        st.subheader("4. Cost-of-Living Calculation Results")
        
        calc_method = st.radio(
            "Select Non-Food Calculation Approach", 
            ["Direct Itemized Sum (Exact NFI List Above)", "Mathematical Expenditure Weight Estimation (NISR Share Ratio)"], 
            horizontal=True
        )

        if calc_method == "Direct Itemized Sum (Exact NFI List Above)":
            m1, m2, m3 = st.columns(3)
            m1.metric("Food Basket Total", f"{food_total:,.0f} RWF")
            m2.metric("Direct Non-Food Total", f"{non_food_direct:,.0f} RWF")
            m3.metric("Itemized Cost of Living", f"{direct_grand_total:,.0f} RWF")
            
            fig_chart = px.pie(edited_bnb_df, names="Category", values="Total Monthly Cost (RWF)", title="Complete Itemized Expenditure Breakdown")
            st.plotly_chart(fig_chart, use_container_width=True)
        else:
            m1, m2, m3 = st.columns(3)
            m1.metric("Food Basket Total", f"{food_total:,.0f} RWF")
            m2.metric(f"Est. Non-Food Expenses ({100-food_share_pct:.1f}%)", f"{non_food_weighted:,.0f} RWF")
            m3.metric("Est. Total Cost of Living (Weighted)", f"{weighted_grand_total:,.0f} RWF")
            
            weight_df = pd.DataFrame({
                "Expense Type": ["Food Basket Total", "Estimated Non-Food Needs"],
                "Amount (RWF)": [food_total, non_food_weighted]
            })
            fig_chart = px.pie(weight_df, names="Expense Type", values="Amount (RWF)", title=f"Expenditure Breakdown based on {food_share_pct}% Food Weight Allocation")
            st.plotly_chart(fig_chart, use_container_width=True)

    # -----------------------------------------------------------------------------
    # TAB 4: DATABASE EDITING ENGINE
    # -----------------------------------------------------------------------------
    with tab4:
        st.header("✏️ Price Modification Engine")
        dataset_choice = st.radio("Select Target Dataset to Edit", ["Local Sub-District / Village Prices", "Official WFP Market Prices"], horizontal=True)

        if dataset_choice == "Local Sub-District / Village Prices":
            if df_village.empty:
                st.info("No local village records available to edit.")
            else:
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
