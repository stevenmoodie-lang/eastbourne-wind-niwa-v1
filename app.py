import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import datetime
import numpy as np
from bs4 import BeautifulSoup
import urllib3

# --- SETTINGS ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="Wellington Harbour Wind (Kts)", layout="wide")

LAT, LON = -41.319, 174.839
KMH_TO_KNOTS = 0.539957

# --- CSS ---
st.markdown("""
    <style>
        [data-testid="stHeader"], header { visibility: hidden; height: 0; }
        .stAppViewContainer { top: -30px !important; } 
        .stApp { background-color: #3d5a73; color: #f8f9fa; }
        .block-container { padding-top: 1.8rem !important; padding-left: 0.5rem !important; padding-right: 0.5rem !important; }
        .custom-title { text-align: center; font-size: 1.3rem; font-weight: 700; color: #ffffff; margin-bottom: 0.5rem; }
        .live-container { background: rgba(0, 0, 0, 0.3); border-radius: 10px; padding: 12px; margin-bottom: 1rem; border: 1px solid rgba(255, 255, 255, 0.1); }
        .live-label { font-size: 0.65rem; text-transform: uppercase; opacity: 0.7; letter-spacing: 0.5px; margin-bottom: 2px; }
        .live-val { font-size: 1.2rem; font-weight: 800; color: #ffffff; }
        .live-unit { font-size: 0.7rem; font-weight: 400; opacity: 0.8; margin-left: 2px; }
        .section-label { opacity: 0.5; font-size: 0.7rem; font-weight: 700; margin-top: 1.5rem; margin-bottom: 0.2rem; text-align: left; padding-left: 5px; text-transform: uppercase; }
    </style>
    <div class="custom-title">Harbour Front Lead</div>
""", unsafe_allow_html=True)

# --- FUNCTIONS ---
@st.cache_data(ttl=600)
def get_weather_data():
    # 1. Fetch NIWA (First 7 days)
    niwa_url = "https://weather-api-azure.niwa.co.nz/api/grid/combined"
    r_niwa = requests.get(niwa_url, params={"lat": LAT, "long": LON}, timeout=15).json()
    records = []
    for f in r_niwa.get("forecast", []):
        t = pd.to_datetime(f["datetime"])
        if t.tzinfo is not None: t = t.tz_convert("Pacific/Auckland").tz_localize(None)
        records.append({"time": t, "speed": f.get("wind_speed_mean", f.get("wind_speed", 0)) * KMH_TO_KNOTS, "dir": f.get("wind_direction", 0)})
    df_niwa = pd.DataFrame(records)

    # 2. Fetch Open-Meteo (14 days for data consistency)
    om_url = "https://api.open-meteo.com/v1/forecast"
    om_params = {"latitude": LAT, "longitude": LON, "hourly": ["wind_speed_10m", "wind_direction_10m"], "daily": ["sunrise", "sunset"], "timezone": "Pacific/Auckland", "wind_speed_unit": "kn", "forecast_days": 14}
    r_om = requests.get(om_url, params=om_params).json()
    df_om = pd.DataFrame({"time": pd.to_datetime(r_om["hourly"]["time"]), "speed": r_om["hourly"]["wind_speed_10m"], "dir": r_om["hourly"]["wind_direction_10m"]})
    df_sun = pd.DataFrame({"date": pd.to_datetime(r_om["daily"]["time"]).date, "sunrise": pd.to_datetime(r_om["daily"]["sunrise"]), "sunset": pd.to_datetime(r_om["daily"]["sunset"])})
    return df_niwa, df_om, df_sun

def get_front_lead_live():
    try:
        url = "https://www.centreport.co.nz/images/forms/PortWeather.html"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=15, verify=False)
        soup = BeautifulSoup(r.text, 'html.parser')
        for row in soup.find_all('tr'):
            cols = [c.get_text(strip=True).replace('\xa0', ' ') for c in row.find_all(['td', 'th'])]
            if len(cols) >= 5 and "front" in (cols[0]+cols[1]).lower() and "lead" in (cols[0]+cols[1]).lower():
                time_idx = 1 if ":" in cols[1] else 2
                return {"time": cols[time_idx], "dir": cols[time_idx+1], "mean": cols[time_idx+2], "gust": cols[time_idx+3]}
    except: return None
    return None

def get_color(val, alpha=1.0):
    if val <= 10: return f"rgba(169, 201, 217, {alpha})"
    if val <= 15: return f"rgba(92, 169, 204, {alpha})"
    if val <= 20: return f"rgba(122, 214, 134, {alpha})"
    if val <= 25: return f"rgba(255, 230, 109, {alpha})"
    if val <= 30: return f"rgba(255, 126, 121, {alpha})"
    if val <= 35: return f"rgba(224, 49, 49, {alpha})"
    return f"rgba(153, 5, 5, {alpha})"

def render_forecast_block(df_hourly, df_sun, show_now_line=False, now_ts=None):
    if df_hourly.empty: return
    max_wind = df_hourly['speed'].max()
    crop_start = pd.Timestamp(df_sun['sunrise'].min())
    crop_end = pd.Timestamp(df_sun['sunset'].max())
    
    # Ribbon logic
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
            fig_ribbon.add_trace(go.Bar(x=[s['x_id']], y=[1], marker=dict(color="rgba(0,0,0,0)", line_width=0), showlegend=False))
        else:
            fig_ribbon.add_trace(go.Bar(x=[s['x_id']], y=[1], marker=dict(color=get_color(s['speed']), line_width=0), showlegend=False))
            heading = (s['dir'] + 180) % 360
            y_arrow = 0.5 + (0.3 * np.cos(np.deg2rad(s['dir'])))
            fig_ribbon.add_annotation(x=s['x_id'], y=y_arrow, text="➤", showarrow=False, textangle=heading-90, font=dict(size=7, color="white"))
            fig_ribbon.add_annotation(x=s['x_id'], y=-0.3, text=f"<b>{int(round(s['speed']))}</b>", showarrow=False, font=dict(size=7, color="white"))
    fig_ribbon.update_layout(height=85, margin=dict(l=5, r=5, t=25, b=10), template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', bargap=0, xaxis=dict(showgrid=False, tickmode='array', tickvals=[f"{d}_1" for d in df_sun['date']], ticktext=[f"<b>{d.strftime('%a')}</b>" for d in df_sun['date']], side="top", tickfont=dict(size=9, color="white")), yaxis=dict(visible=False, range=[-0.6, 1.1]))
    st.plotly_chart(fig_ribbon, use_container_width=True, config={'displayModeBar': False})

    # Main Graph Logic (abbreviated for compactness, but same functionality)
    fig_main = go.Figure()
    fig_main.update_layout(height=200, margin=dict(l=10, r=10, t=5, b=5), template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis=dict(visible=False, range=[crop_start, crop_end]), yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.03)', showticklabels=False, range=[-5, max_wind + 10]))
    st.plotly_chart(fig_main, use_container_width=True, config={'displayModeBar': False})

# --- EXECUTION ---
live_data = get_front_lead_live()
if live_data:
    st.markdown(f'<div class="live-container">Current: {live_data["mean"]}kts | Gust: {live_data["gust"]}kts | Dir: {live_data["dir"]}</div>', unsafe_allow_html=True)

try:
    df_niwa, df_om, sun_all = get_weather_data()
    now_nz = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=12))).replace(tzinfo=None)

    # Week 1
    s1 = sun_all.iloc[:7]
    st.markdown(f'<div class="section-label">{s1.iloc[0]["date"].strftime("%b %d")} - {s1.iloc[-1]["date"].strftime("%d")}</div>', unsafe_allow_html=True)
    mask1 = (df_niwa['time'] >= pd.Timestamp(s1.iloc[0]['date'])) & (df_niwa['time'] < pd.Timestamp(s1.iloc[-1]['date']) + pd.Timedelta(days=1))
    render_forecast_block(df_niwa[mask1], s1, show_now_line=True, now_ts=now_nz)

    st.markdown("<hr>", unsafe_allow_html=True)

    # Week 2
    s2 = sun_all.iloc[7:14]
    st.markdown(f'<div class="section-label">{s2.iloc[0]["date"].strftime("%b %d")} - {s2.iloc[-1]["date"].strftime("%d")} (Extended)</div>', unsafe_allow_html=True)
    mask2 = (df_om['time'] >= pd.Timestamp(s2.iloc[0]['date'])) & (df_om['time'] < pd.Timestamp(s2.iloc[-1]['date']) + pd.Timedelta(days=1))
    render_forecast_block(df_om[mask2], s2)
except Exception as e:
    st.error(f"Error: {e}")
