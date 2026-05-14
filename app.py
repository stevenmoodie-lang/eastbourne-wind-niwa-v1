import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import datetime
import numpy as np

# --- PAGE CONFIG ---
st.set_page_config(page_title="Wellington Harbour Wind (Kts)", layout="wide")

# --- SETTINGS & CONSTANTS ---
LAT, LON = -41.319, 174.839
KMH_TO_KNOTS = 0.539957

# --- LIVE DATA (CENTREPORT API) ---
@st.cache_data(ttl=60)
def get_front_lead_live():
    """Fetches live data directly from CentrePort's weather API."""
    try:
        # This is the direct source for the tables you see on NDBC and CentrePort sites
        url = "https://weather.centreport.co.nz/Home/GetTableData"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
            'Referer': 'https://weather.centreport.co.nz/'
        }
        
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return {"error": f"API Error: {r.status_code}"}
            
        data = r.json()
        
        # Search for Front Lead in the list of stations
        for station in data:
            name = station.get("StationName", "").lower()
            if "front" in name and "lead" in name:
                return {
                    "time": station.get("Time", "N/A"),
                    "dir": station.get("WindDir", "N/A"),
                    "mean": station.get("WindSpeed", 0),
                    "gust": station.get("WindGust", 0)
                }
                
        return {"error": "Station 'Front Lead' not found in API response."}

    except Exception as e:
        return {"error": f"Connection Error: {str(e)}"}

# --- STYLING (CSS) ---
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
            margin-bottom: 0.5rem;
        }
        .live-container {
            background: rgba(0, 0, 0, 0.3);
            border-radius: 10px;
            padding: 12px;
            margin-bottom: 1rem;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .live-label { font-size: 0.65rem; text-transform: uppercase; opacity: 0.7; letter-spacing: 0.5px; margin-bottom: 2px; }
        .live-val { font-size: 1.2rem; font-weight: 800; color: #ffffff; }
        .live-unit { font-size: 0.7rem; opacity: 0.8; margin-left: 2px; }
        .section-label { opacity: 0.5; font-size: 0.7rem; font-weight: 700; margin-top: 1.5rem; text-transform: uppercase; padding-left: 5px; }
    </style>
    <div class="custom-title">Harbour Front Lead</div>
""", unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---
def get_color(val, alpha=1.0):
    if val <= 10: return f"rgba(169, 201, 217, {alpha})"
    if val <= 15: return f"rgba(92, 169, 204, {alpha})"
    if val <= 20: return f"rgba(122, 214, 134, {alpha})"
    if val <= 25: return f"rgba(255, 230, 109, {alpha})"
    if val <= 30: return f"rgba(255, 126, 121, {alpha})"
    if val <= 35: return f"rgba(224, 49, 49, {alpha})"
    return f"rgba(153, 5, 5, {alpha})"

@st.cache_data(ttl=600)
def get_weather_data():
    niwa_url = "https://weather-api-azure.niwa.co.nz/api/grid/combined"
    niwa_params = {"lat": LAT, "long": LON}
    r_niwa = requests.get(niwa_url, params=niwa_params, timeout=15).json()
    
    records = []
    for f in r_niwa.get("forecast", []):
        t = pd.to_datetime(f["datetime"])
        if t.tzinfo is not None:
            t = t.tz_convert("Pacific/Auckland").tz_localize(None)
        speed_kts = f.get("wind_speed_mean", f.get("wind_speed", 0)) * KMH_TO_KNOTS
        records.append({"time": t, "speed": speed_kts, "dir": f.get("wind_direction", 0)})
    
    sun_url = "https://api.open-meteo.com/v1/forecast"
    sun_params = {"latitude": LAT, "longitude": LON, "daily": ["sunrise", "sunset"], "timezone": "Pacific/Auckland", "forecast_days": 14}
    r_sun = requests.get(sun_url, params=sun_params).json()
    sun = pd.DataFrame({
        "date": pd.to_datetime(r_sun["daily"]["time"]).date,
        "sunrise": pd.to_datetime(r_sun["daily"]["sunrise"]),
        "sunset": pd.to_datetime(r_sun["daily"]["sunset"])
    })
    return pd.DataFrame(records), sun

def render_forecast_block(df_hourly, df_sun, show_now_line=False, now_ts=None):
    if df_hourly.empty: return
    max_wind = df_hourly['speed'].max()
    crop_start, crop_end = pd.Timestamp(df_sun['sunrise'].min()), pd.Timestamp(df_sun['sunset'].max())

    segments = []
    for _, day in df_sun.iterrows():
        sunrise, sunset = pd.Timestamp(day['sunrise']), pd.Timestamp(day['sunset'])
        seg_dur = (sunset - sunrise) / 3
        for i in range(3):
            t0, t1 = sunrise + (i*seg_dur), sunrise + ((i+1)*seg_dur)
            d = df_hourly[(df_hourly['time'] >= t0) & (df_hourly['time'] < t1)]
            if not d.empty:
                rads = np.deg2rad(d['dir'])
                avg_dir = np.rad2deg(np.arctan2(np.sin(rads).mean(), np.cos(rads).mean())) % 360
                segments.append({"x_id": f"{day['date']}_{i}", "speed": d['speed'].mean(), "dir": avg_dir})
        segments.append({"x_id": f"{day['date']}_spacer", "spacer": True})

    fig_ribbon = go.Figure()
    for s in segments:
        if "spacer" in s:
            fig_ribbon.add_trace(go.Bar(x=[s['x_id']], y=[1], marker=dict(color="rgba(0,0,0,0)"), showlegend=False))
            continue
        fig_ribbon.add_trace(go.Bar(x=[s['x_id']], y=[1], marker=dict(color=get_color(s['speed'])), showlegend=False))
        fig_ribbon.add_annotation(x=s['x_id'], y=0.5, text="➤", textangle=((s['dir']+180)%360)-90, showarrow=False, font=dict(size=7, color="white"))
        fig_ribbon.add_annotation(x=s['x_id'], y=-0.3, text=f"<b>{int(round(s['speed']))}</b>", showarrow=False, font=dict(size=7, color="white"))

    fig_ribbon.update_layout(height=85, margin=dict(l=5, r=5, t=25, b=10), template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', bargap=0, xaxis=dict(showgrid=False, tickmode='array', tickvals=[f"{d}_1" for d in df_sun['date']], ticktext=[f"<b>{d.strftime('%a')}</b>" for d in df_sun['date']], side="top", tickfont=dict(size=9)), yaxis=dict(visible=False, range=[-0.6, 1.1]))
    st.plotly_chart(fig_ribbon, use_container_width=True, config={'displayModeBar': False})

    fig_main = go.Figure()
    for i in range(len(df_hourly)-1):
        p1, p2 = df_hourly.iloc[i], df_hourly.iloc[i+1]
        fig_main.add_trace(go.Scatter(x=[p1['time'], p2['time']], y=[p1['speed'], p2['speed']], line=dict(color=get_color(p1['speed']), width=2), mode='lines', showlegend=False))

    if show_now_line and now_ts:
        fig_main.add_vline(x=now_ts, line_width=1, line_dash="dash", line_color="white")

    fig_main.update_layout(height=200, margin=dict(l=10, r=10, t=5, b=5), template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis=dict(visible=False, range=[crop_start, crop_end]), yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)', showticklabels=False, range=[-5, max_wind + 10]))
    st.plotly_chart(fig_main, use_container_width=True, config={'displayModeBar': False})

# --- EXECUTION ---

# 1. Fetch Live Report
live_data = get_front_lead_live()

# 2. Render Live Report Banner
if live_data and "error" not in live_data:
    st.markdown(f"""
    <div class="live-container">
        <div style="display: flex; justify-content: space-around; text-align: center;">
            <div><div class="live-label">Current</div><div class="live-val">{live_data['mean']}<span class="live-unit">kts</span></div></div>
            <div><div class="live-label">Max Gust</div><div class="live-val" style="color: #ff7e79;">{live_data['gust']}<span class="live-unit">kts</span></div></div>
            <div><div class="live-label">Direction</div><div class="live-val">{live_data['dir']}</div></div>
            <div style="border-left: 1px solid rgba(255,255,255,0.1); padding-left: 15px;">
                <div class="live-label">Updated</div><div class="live-val" style="font-size: 0.8rem; opacity: 0.6;">{live_data['time']}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.sidebar.error(f"Live Scraper Debug: {live_data.get('error') if live_data else 'Unknown Error'}")
    st.info("Live Front Lead data currently unavailable.")

# 3. Render Forecast
try:
    df_all, sun_all = get_weather_data()
    now_nz = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=12))).replace(tzinfo=None)
    s1 = sun_all.iloc[:7]
    st.markdown(f'<div class="section-label">Forecast: {s1.iloc[0]["date"].strftime("%b %d")}</div>', unsafe_allow_html=True)
    render_forecast_block(df_all, s1, show_now_line=True, now_ts=now_nz)
except Exception as e:
    st.error(f"Forecast error: {e}")
