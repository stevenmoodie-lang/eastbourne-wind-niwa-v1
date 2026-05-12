import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import datetime
import numpy as np

# --- PAGE CONFIG ---
st.set_page_config(page_title="Eastbourne Wind NIWA", layout="wide")

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
    <div class="custom-title">Eastbourne Wind (NIWA 1.5km)</div>
""", unsafe_allow_html=True)

# --- SETTINGS ---
LAT, LON = -41.405, 174.867
KMH_TO_KNOTS = 0.539957

def get_color(knots, alpha=1.0):
    if knots <= 5: return f"rgba(169, 201, 217, {alpha})"
    if knots <= 10: return f"rgba(92, 169, 204, {alpha})"
    if knots <= 15: return f"rgba(122, 214, 134, {alpha})"
    if knots <= 20: return f"rgba(255, 230, 109, {alpha})"
    if knots <= 25: return f"rgba(255, 126, 121, {alpha})"
    if knots <= 30: return f"rgba(224, 49, 49, {alpha})"
    return f"rgba(153, 5, 5, {alpha})"

@st.cache_data(ttl=600)
def get_weather_data():
    # 1. Fetch NIWA High-Res Wind Data
    niwa_url = "https://weather-api-azure.niwa.co.nz/api/grid/combined"
    niwa_params = {"lat": LAT, "long": LON}
    r_niwa = requests.get(niwa_url, params=niwa_params, timeout=15).json()
    
    records = []
    for f in r_niwa.get("forecast", []):
        t = pd.to_datetime(f["datetime"])
        if t.tzinfo is not None:
            t = t.tz_convert("Pacific/Auckland").tz_localize(None)
        
        records.append({
            "time": t,
            "speed": f.get("wind_speed", 0) * KMH_TO_KNOTS,
            "dir": f.get("wind_direction", 0)
        })
    df = pd.DataFrame(records)

    # 2. Fetch Solar Data from Open-Meteo (NIWA API is wind-focused)
    sun_url = "https://api.open-meteo.com/v1/forecast"
    sun_params = {
        "latitude": LAT, "longitude": LON,
        "daily": ["sunrise", "sunset"],
        "timezone": "Pacific/Auckland", "forecast_days": 14
    }
    r_sun = requests.get(sun_url, params=sun_params).json()
    sun = pd.DataFrame({
        "date": pd.to_datetime(r_sun["daily"]["time"]).date,
        "sunrise": pd.to_datetime(r_sun["daily"]["sunrise"]),
        "sunset": pd.to_datetime(r_sun["daily"]["sunset"])
    })
    
    return df, sun

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
            fig_ribbon.add_trace(go.Bar(x=[s['x_id']], y=[1], marker=dict(color="rgba(0,0,0,0)"), showlegend=False))
            continue
        fig_ribbon.add_trace(go.Bar(x=[s['x_id']], y=[1], marker=dict(color=get_color(s['speed'])), showlegend=False))
        heading = (s['dir'] + 180) % 360
        fig_ribbon.add_annotation(x=s['x_id'], y=0.5, text="➤", showarrow=False, textangle=heading-90, font=dict(size=7, color="white"))
        fig_ribbon.add_annotation(x=s['x_id'], y=-0.3, text=f"<b>{round(s['speed'])}</b>", showarrow=False, font=dict(size=7, color="white"))

    fig_ribbon.update_layout(
        height=85, margin=dict(l=5, r=5, t=25, b=10), template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=False, tickmode='array', tickvals=[f"{d}_1" for d in df_sun['date']], 
                   ticktext=[f"<b>{d.strftime('%a')}</b>" for d in df_sun['date']], side="top", tickfont=dict(size=9)),
        yaxis=dict(visible=False, range=[-0.6, 1.1])
    )
    st.plotly_chart(fig_ribbon, use_container_width=True, config={'displayModeBar': False})

    # --- 2. COMPACT WIND DASHBOARD ---
    fig_main = go.Figure()
    for i in range(len(df_hourly)-1):
        p1, p2 = df_hourly.iloc[i], df_hourly.iloc[i+1]
        day_info = df_sun[df_sun['date'] == p1['time'].date()]
        if day_info.empty: continue
        sr, ss = pd.Timestamp(day_info.iloc[0]['sunrise']), pd.Timestamp(day_info.iloc[0]['sunset'])
        
        is_night = p1['time'] < sr or p1['time'] >= ss
        alpha = 0.12 if is_night else 1.0
        
        fig_main.add_trace(go.Scatter(
            x=[p1['time'], p2['time']], y=[p1['speed'], p2['speed']],
            line=dict(color=get_color(p1['speed'], alpha), width=2 if not is_night else 1),
            mode='lines', showlegend=False, hoverinfo='skip'
        ))

    # Night Shading & Icons
    for i in range(len(df_sun)-1):
        ss = pd.Timestamp(df_sun.iloc[i]['sunset'])
        sr_next = pd.Timestamp(df_sun.iloc[i+1]['sunrise'])
        fig_main.add_vrect(x0=ss, x1=sr_next, fillcolor="rgba(0,0,0,0.2)", layer="below", line_width=0)
        fig_main.add_annotation(x=ss+(sr_next-ss)/2, y=-2.5, text="☾", showarrow=False, font=dict(size=12, color="rgba(255,255,255,0.35)"))

    if show_now_line and now_ts:
        fig_main.add_vline(x=now_ts, line_width=1, line_dash="dash", line_color="white", opacity=0.6)

    fig_main.update_layout(
        height=200, margin=dict(l=10, r=10, t=5, b=5), template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(visible=False, range=[crop_start, crop_end]),
        yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.03)', zeroline=False, showticklabels=False, range=[-5, max_wind + 10])
    )
    st.plotly_chart(fig_main, use_container_width=True, config={'displayModeBar': False, 'scrollZoom': True})

# --- EXECUTION ---
try:
    df_all, sun_all = get_weather_data()
    now_nz = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=12))).replace(tzinfo=None)

    # BLOCK 1: Week 1
    s1 = sun_all.iloc[:7]
    st.markdown(f'<div class="section-label">{s1.iloc[0]["date"].strftime("%b %d")} - {s1.iloc[-1]["date"].strftime("%d")}</div>', unsafe_allow_html=True)
    mask1 = (df_all['time'] >= pd.Timestamp(s1.iloc[0]['date'])) & (df_all['time'] < pd.Timestamp(s1.iloc[-1]['date']) + pd.Timedelta(days=1))
    render_forecast_block(df_all[mask1], s1, show_now_line=True, now_ts=now_nz)

    st.markdown("<hr style='border: 0; border-top: 1px solid rgba(255,255,255,0.1); margin: 1rem 0;'>", unsafe_allow_html=True)

    # BLOCK 2: Week 2
    s2 = sun_all.iloc[7:14]
    if not s2.empty:
        st.markdown(f'<div class="section-label">{s2.iloc[0]["date"].strftime("%b %d")} - {s2.iloc[-1]["date"].strftime("%d")}</div>', unsafe_allow_html=True)
        mask2 = (df_all['time'] >= pd.Timestamp(s2.iloc[0]['date'])) & (df_all['time'] < pd.Timestamp(s2.iloc[-1]['date']) + pd.Timedelta(days=1))
        render_forecast_block(df_all[mask2], s2)

except Exception as e:
    st.error(f"NIWA Data Unavailable: {e}")
