import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import datetime
import numpy as np

# --- PAGE CONFIG ---
st.set_page_config(page_title="Wellington Harbour Wind (Kts)", layout="wide")

# --- CSS: MOBILE OPTIMIZATION ---
st.markdown("""
    <style>
        [data-testid="stHeader"], header { visibility: hidden; height: 0; }
        .stAppViewContainer { top: -30px !important; } 
        .stApp { background-color: #3d5a73; color: #f8f9fa; }
        .block-container { 
            padding-top: 1.8rem !important; 
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }
        .custom-title {
            text-align: center;
            font-size: 1.3rem;
            font-weight: 700;
            color: #ffffff;
            margin-bottom: 0.3rem;
            white-space: nowrap;
        }
        .section-label {
            opacity: 0.5;
            font-size: 0.7rem;
            font-weight: 700;
            margin-top: 1.5rem;
            margin-bottom: 0.2rem;
            text-align: left;
            padding-left: 5px;
            text-transform: uppercase;
        }
    </style>
    <div class="custom-title">Harbour Front Lead (NIWA/OM - Knots)</div>
""", unsafe_allow_html=True)

# --- SETTINGS ---
LAT, LON = -41.319, 174.839 
KMH_TO_KNOTS = 0.539957

# --- UPDATED COLOR CATEGORIES ---
def get_color(val, alpha=1.0):
    if val <= 5: return f"rgba(169, 201, 217, {alpha})"   # Light Blue (1-5)
    if val <= 10: return f"rgba(92, 169, 204, {alpha})"  # Blue (6-10)
    if val <= 15: return f"rgba(122, 214, 134, {alpha})" # Green (11-15)
    if val <= 20: return f"rgba(255, 230, 109, {alpha})" # Yellow (16-20)
    if val <= 25: return f"rgba(253, 174, 97, {alpha})"  # Orange (21-25)
    if val <= 30: return f"rgba(224, 49, 49, {alpha})"   # Red (26-30)
    return f"rgba(153, 5, 5, {alpha})"                   # Dark Red (31+)

@st.cache_data(ttl=600)
def get_weather_data():
    # 1. Fetch Open-Meteo
    om_url = "https://api.open-meteo.com/v1/forecast"
    om_params = {
        "latitude": LAT, "longitude": LON,
        "hourly": ["wind_speed_10m", "wind_direction_10m"],
        "daily": ["sunrise", "sunset"],
        "timezone": "Pacific/Auckland", "wind_speed_unit": "kn", "forecast_days": 14
    }
    r_om = requests.get(om_url, params=om_params, timeout=10).json()
    
    # Standardize to timezone-naive to prevent comparison errors
    df_om = pd.DataFrame({
        "time": pd.to_datetime(r_om["hourly"]["time"]).tz_localize(None),
        "speed": r_om["hourly"]["wind_speed_10m"],
        "dir": r_om["hourly"]["wind_direction_10m"]
    })
    
    # 2. Try to fetch NIWA for the first 7 days
    try:
        niwa_url = "https://weather-api-azure.niwa.co.nz/api/grid/combined"
        niwa_params = {"lat": LAT, "long": LON}
        r_niwa = requests.get(niwa_url, params=niwa_params, timeout=10).json()
        
        niwa_records = []
        for f in r_niwa.get("forecast", []):
            t = pd.to_datetime(f["datetime"]).tz_localize(None)
            speed_kts = f.get("wind_speed_mean", f.get("wind_speed", 0)) * KMH_TO_KNOTS
            niwa_records.append({"time": t, "speed": speed_kts, "dir": f.get("wind_direction", 0)})
        
        df_niwa = pd.DataFrame(niwa_records)
        limit_date = df_om['time'].min() + pd.Timedelta(days=7)
        df_niwa = df_niwa[df_niwa['time'] < limit_date]
        df_final = pd.concat([df_niwa, df_om[df_om['time'] >= limit_date]]).reset_index(drop=True)
    except Exception:
        df_final = df_om

    sun = pd.DataFrame({
        "date": pd.to_datetime(r_om["daily"]["time"]).date,
        "sunrise": pd.to_datetime(r_om["daily"]["sunrise"]).tz_localize(None),
        "sunset": pd.to_datetime(r_om["daily"]["sunset"]).tz_localize(None)
    })
    
    return df_final, sun

# ... [The rest of your original render_forecast_block and EXECUTION remains exactly as you had it] ...
