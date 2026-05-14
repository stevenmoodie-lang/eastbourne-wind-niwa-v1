import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import datetime
import numpy as np

# --- SETTINGS ---
LAT, LON = -41.319, 174.839
KMH_TO_KNOTS = 0.539957

# ... [Keep your existing get_color function and CSS here] ...

@st.cache_data(ttl=600)
def get_weather_data():
    # 1. Fetch NIWA (Days 1-7)
    niwa_url = "https://weather-api-azure.niwa.co.nz/api/grid/combined"
    niwa_params = {"lat": LAT, "long": LON}
    r_niwa = requests.get(niwa_url, params=niwa_params, timeout=15).json()
    
    niwa_records = []
    for f in r_niwa.get("forecast", []):
        t = pd.to_datetime(f["datetime"])
        if t.tzinfo is not None:
            t = t.tz_convert("Pacific/Auckland").tz_localize(None)
        
        # NIWA raw assumed km/h
        speed_kts = f.get("wind_speed_mean", f.get("wind_speed", 0)) * KMH_TO_KNOTS
        niwa_records.append({"time": t, "speed": speed_kts, "dir": f.get("wind_direction", 0)})
    
    df_niwa = pd.DataFrame(niwa_records)
    # Filter for first 7 days
    limit_date = df_niwa['time'].min() + pd.Timedelta(days=7)
    df_niwa = df_niwa[df_niwa['time'] < limit_date]

    # 2. Fetch Open-Meteo (Days 1-14)
    om_url = "https://api.open-meteo.com/v1/forecast"
    om_params = {
        "latitude": LAT, "longitude": LON,
        "hourly": ["wind_speed_10m", "wind_direction_10m"],
        "daily": ["sunrise", "sunset"],
        "timezone": "Pacific/Auckland", "wind_speed_unit": "kn", "forecast_days": 14
    }
    r_om = requests.get(om_url, params=om_params).json()
    
    df_om = pd.DataFrame({
        "time": pd.to_datetime(r_om["hourly"]["time"]),
        "speed": r_om["hourly"]["wind_speed_10m"],
        "dir": r_om["hourly"]["wind_direction_10m"]
    })
    
    # Filter Open-Meteo for days 8-14
    df_om = df_om[df_om['time'] >= limit_date]

    # Combine
    df_final = pd.concat([df_niwa, df_om]).reset_index(drop=True)

    # Sunrise/Sunset (using Open-Meteo)
    sun = pd.DataFrame({
        "date": pd.to_datetime(r_om["daily"]["time"]).date,
        "sunrise": pd.to_datetime(r_om["daily"]["sunrise"]),
        "sunset": pd.to_datetime(r_om["daily"]["sunset"])
    })
    
    return df_final, sun

# ... [Keep your existing render_forecast_block and execution logic] ...
