import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import datetime
import numpy as np

# --- PAGE CONFIG ---
st.set_page_config(page_title="Wellington Harbour Wind (Kts)", layout="wide")

# --- SETTINGS ---
# Updated coordinates for more accurate Front Lead positioning
LAT, LON = -41.319, 174.839 
KMH_TO_KNOTS = 0.539957

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
    r_om = requests.get(om_url, params=om_params, timeout=10)
    r_om.raise_for_status()
    r_om_json = r_om.json()
    
    # Ensure time is timezone-naive
    df_om = pd.DataFrame({
        "time": pd.to_datetime(r_om_json["hourly"]["time"]).tz_localize(None),
        "speed": r_om_json["hourly"]["wind_speed_10m"],
        "dir": r_om_json["hourly"]["wind_direction_10m"]
    })
    
    # 2. Fetch NIWA
    niwa_url = "https://weather-api-azure.niwa.co.nz/api/grid/combined"
    niwa_params = {"lat": LAT, "long": LON}
    
    response = requests.get(niwa_url, params=niwa_params, timeout=10)
    response.raise_for_status()
    r_niwa = response.json()
    
    niwa_records = []
    for f in r_niwa.get("forecast", []):
        t = pd.to_datetime(f["datetime"])
        # Ensure NIWA time is also naive
        if t.tz is not None:
            t = t.tz_localize(None)
        speed_kts = f.get("wind_speed_mean", f.get("wind_speed", 0)) * KMH_TO_KNOTS
        niwa_records.append({"time": t, "speed": speed_kts, "dir": f.get("wind_direction", 0)})
    
    df_niwa = pd.DataFrame(niwa_records)
    limit_date = df_om['time'].min() + pd.Timedelta(days=7)
    
    # Now this comparison will work safely
    df_niwa = df_niwa[df_niwa['time'] < limit_date]
    
    # Merge: NIWA (days 1-7) + Open-Meteo (days 8-14)
    df_final = pd.concat([df_niwa, df_om[df_om['time'] >= limit_date]]).reset_index(drop=True)
    
    sun = pd.DataFrame({
        "date": pd.to_datetime(r_om_json["daily"]["time"]).date,
        "sunrise": pd.to_datetime(r_om_json["daily"]["sunrise"]).tz_localize(None),
        "sunset": pd.to_datetime(r_om_json["daily"]["sunset"]).tz_localize(None)
    })
    
    return df_final, sun

# --- EXECUTION ---
# (Rest of your rendering logic remains the same)
try:
    df_all, sun_all = get_weather_data()
    # Ensure now_nz is also naive for comparison
    now_nz = datetime.datetime.now().replace(tzinfo=None)
    
    s1 = sun_all.iloc[:7]
    # ... [Rest of your UI rendering code] ...
except Exception as e:
    st.error(f"Error loading forecast: {e}")
