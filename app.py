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

def get_color(val, alpha=1.0):
    if val <= 5: return f"rgba(169, 201, 217, {alpha})"   # Light Blue (1-5)
    if val <= 10: return f"rgba(92, 169, 204, {alpha})"  # Blue (6-10)
    if val <= 15: return f"rgba(122, 214, 134, {alpha})" # Green (11-15)
    if val <= 20: return f"rgba(255, 230, 109, {alpha})" # Yellow (16-20)
    if val <= 25: return f"rgba(253, 174, 97, {alpha})"  # Orange (21-25)
    if val <= 30: return f"rgba(224, 49, 49, {alpha})"   # Red (26-30)
    return f"rgba(153, 5, 5, {alpha})"                   # Dark Red (31+)

# --- FRONT LEAD CALIBRATION FUNCTION ---
def calibrate_front_lead(speed):
    if speed < 12:
        return speed + 3.0
    elif speed <= 29:
        return speed * 1.25
    else:
        return speed * 1.4

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

    df_om = pd.DataFrame({
        "time": pd.to_datetime(r_om["hourly"]["time"]),
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
            t = pd.to_datetime(f["datetime"])
            speed_kts = f.get("wind_speed_mean", f.get("wind_speed", 0)) * KMH_TO_KNOTS
            niwa_records.append({"time": t, "speed": speed_kts, "dir": f.get("wind_direction", 0)})

        df_niwa = pd.DataFrame(niwa_records)
        limit_date = df_om['time'].min() + pd.Timedelta(days=7)
        df_niwa = df_niwa[df_niwa['time'] < limit_date]

        # Merge: NIWA (days 1-7) + Open-Meteo (days 8-14)
        df_final = pd.concat([df_niwa, df_om[df_om['time'] >= limit_date]]).reset_index(drop=True)

    except Exception:
        df_final = df_om

    # Apply calibration multiplier to align model with live Front Lead sensor readings
    df_final["speed"] = df_final["speed"].apply(calibrate_front_lead)

    sun = pd.DataFrame({
        "date": pd.to_datetime(r_om["daily"]["time"]).date,
        "sunrise": pd.to_datetime(r_om["daily"]["sunrise"]),
        "sunset": pd.to_datetime(r_om["daily"]["sunset"])
    })

    return df_final, sun

def render_forecast_block(df_hourly, df_sun, show_now_line=False, now_ts=None):
    if df_hourly.empty: return
    max_wind = df_hourly['speed'].max()
    crop_start = pd.Timestamp(df_sun['sunrise'].min())
    crop_end = pd.Timestamp(df_sun['sunset'].max())

    # --- 1. DYNAMIC ARROW RIBBON ---
    segments = []
    for _, day in df_sun.iterrows():
        sunrise, sunset = pd.Timestamp(day['sunrise']), pd.Timestamp(day['sunset'])
        seg_dur = (sunset - sunrise) / 3
        for i in range(3):
            t0, t1 = sunrise + (i*seg_dur), sunrise + ((i+1)*seg_dur)
            mask = (df_hourly['time'] >= t0) & (df_hourly['time'] < t1)
            d = df_hourly[mask]
            if not d.empty:
                rads = np.deg2rad(d['dir'])
                avg_dir = np.rad2deg(np.arctan2(np.sin(rads).mean(), np.cos(rads).mean())) % 360
                segments.append({"x_id": f"{day['date']}_{i}", "speed": d['speed'].mean(), "dir": avg_dir})
        segments.append({"x_id": f"{day['date']}_spacer", "spacer": True})

    fig_ribbon = go.Figure()
    for s in segments:
        if "spacer" in s:
            fig_ribbon.add_trace(go.Bar(x=[s['x_id']], y=[1], marker=dict(color="rgba(0,0,0,0)", line_width=0), showlegend=False))
            continue
        val = s['speed']
        fig_ribbon.add_trace(go.Bar(x=[s['x_id']], y=[1], marker=dict(color=get_color(val), line_width=0), showlegend=False))
        heading = (s['dir'] + 180) % 360
        y_arrow = 0.5 + (0.3 * np.cos(np.deg2rad(s['dir'])))
        fig_ribbon.add_annotation(x=s['x_id'], y=y_arrow, text="➤", showarrow=False, textangle=heading-90, font=dict(size=7, color="white"))
        fig_ribbon.add_annotation(x=s['x_id'], y=-0.3, text=f"<b>{int(round(val))}</b>", showarrow=False, font=dict(size=7, color="white"))

    fig_ribbon.update_layout(height=85, margin=dict(l=5, r=5, t=25, b=10), template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', bargap=0, xaxis=dict(showgrid=False, tickmode='array', tickvals=[f"{d}_1" for d in df_sun['date']], ticktext=[f"<b>{d.strftime('%a')}</b>" for d in df_sun['date']], side="top", tickfont=dict(size=9, color="white"), fixedrange=True), yaxis=dict(visible=False, range=[-0.6, 1.1], fixedrange=True))
    st.plotly_chart(fig_ribbon, use_container_width=True, config={'displayModeBar': False})

    # --- 2. COMPACT WIND DASHBOARD ---
    fig_main = go.Figure()
    now_speed = None
    for i in range(len(df_hourly)-1):
        p1, p2 = df_hourly.iloc[i], df_hourly.iloc[i+1]
        day_info_match = df_sun[df_sun['date'] == p1['time'].date()]
        if day_info_match.empty: continue
        day_info = day_info_match.iloc[0]
        sr, ss = pd.Timestamp(day_info['sunrise']), pd.Timestamp(day_info['sunset'])
        transition_points = sorted([t for t in [sr, ss] if p1['time'] < t < p2['time']])
        current_times = [p1['time']] + transition_points + [p2['time']]
        for j in range(len(current_times)-1):
            t_start, t_end = current_times[j], current_times[j+1]
            if t_end < crop_start or t_start > crop_end: continue
            duration = (p2['time'] - p1['time']).total_seconds()
            frac = (t_start - p1['time']).total_seconds() / duration if duration > 0 else 0
            interp_speed = p1['speed'] + frac * (p2['speed'] - p1['speed'])
            if show_now_line and t_start <= now_ts < t_end:
                seg_duration = (t_end - t_start).total_seconds()
                now_frac = (now_ts - t_start).total_seconds() / seg_duration if seg_duration > 0 else 0
                speed_end_seg = interp_speed + (p2['speed']-p1['speed']) * (seg_duration / duration) if duration > 0 else interp_speed
                now_speed = interp_speed + now_frac * (speed_end_seg - interp_speed)
            is_night = t_start < sr or t_start >= ss
            alpha = 0.12 if is_night else
