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
LAT, LON = -41.275, 174.825 
KMH_TO_KNOTS = 0.539957

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
    
    df_om = pd.DataFrame({
        "time": pd.to_datetime(r_om_json["hourly"]["time"]),
        "speed": r_om_json["hourly"]["wind_speed_10m"],
        "dir": r_om_json["hourly"]["wind_direction_10m"]
    })
    
    # 2. Fetch NIWA (No fallback: will raise error on failure)
    niwa_url = "https://weather-api-azure.niwa.co.nz/api/grid/combined"
    niwa_params = {"lat": LAT, "long": LON}
    
    response = requests.get(niwa_url, params=niwa_params, timeout=10)
    response.raise_for_status() # Raises HTTPError if status != 200
    r_niwa = response.json()
    
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
    
    sun = pd.DataFrame({
        "date": pd.to_datetime(r_om_json["daily"]["time"]).date,
        "sunrise": pd.to_datetime(r_om_json["daily"]["sunrise"]),
        "sunset": pd.to_datetime(r_om_json["daily"]["sunset"])
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
            alpha = 0.12 if is_night else 1.0
            seg_duration = (t_end - t_start).total_seconds()
            speed_end = interp_speed + (p2['speed']-p1['speed']) * (seg_duration / duration) if duration > 0 else interp_speed
            fig_main.add_trace(go.Scatter(x=[t_start, t_end], y=[interp_speed, speed_end], line=dict(color=get_color(interp_speed, alpha), width=2 if not is_night else 1), mode='lines', showlegend=False, hoverinfo='skip'))

    if show_now_line and now_ts:
        fig_main.add_vline(x=now_ts, line_width=1, line_dash="dash", line_color="white", opacity=0.6)
        if now_speed is not None:
            fig_main.add_annotation(x=now_ts, y=now_speed, text=f"<b>{int(round(now_speed))}</b>", showarrow=False, xanchor="left", xshift=5, font=dict(size=11, color=get_color(now_speed)), bgcolor="rgba(61, 90, 115, 0.6)")
    
    for _, day_sun in df_sun.iterrows():
        sr, ss = pd.Timestamp(day_sun['sunrise']), pd.Timestamp(day_sun['sunset'])
        midpoint = sr + (ss - sr) / 2
        fig_main.add_annotation(x=midpoint, y=max_wind + 6, text=f"<b>{day_sun['date'].strftime('%a')}</b>", showarrow=False, font=dict(size=9, color="rgba(255,255,255,0.6)"))
        day_mask = (df_hourly['time'] >= sr) & (df_hourly['time'] <= ss)
        day_data = df_hourly[day_mask]
        if not day_data.empty:
            for func, offset in [(day_data.loc[day_data['speed'].idxmax()], 3.5), (day_data.loc[day_data['speed'].idxmin()], -3.5)]:
                heading = (func['dir'] + 180) % 360
                fig_main.add_annotation(x=func['time'], y=func['speed'] + (offset/2.5), text="➤", textangle=heading-90, showarrow=False, font=dict(size=6, color="white"))
                fig_main.add_annotation(x=func['time'], y=func['speed'] + offset, text=f"<b>{int(round(func['speed']))}</b>", showarrow=False, font=dict(size=8, color="white"))

    for i in range(len(df_sun)-1):
        ss = pd.Timestamp(df_sun.iloc[i]['sunset'])
        sr_next = pd.Timestamp(df_sun.iloc[i+1]['sunrise'])
        fig_main.add_vrect(x0=ss, x1=sr_next, fillcolor="rgba(0,0,0,0.2)", layer="below", line_width=0)
        night_midpoint = ss + (sr_next - ss) / 2
        fig_main.add_annotation(x=night_midpoint, y=-2.5, text="☾", showarrow=False, font=dict(size=12, color="rgba(255,255,255,0.35)"))

    fig_main.update_layout(height=200, margin=dict(l=10, r=10, t=5, b=5), template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis=dict(visible=False, fixedrange=False, range=[crop_start, crop_end]), yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.03)', zeroline=False, fixedrange=True, showticklabels=False, range=[-5, max_wind + 10]))
    st.plotly_chart(fig_main, use_container_width=True, config={'displayModeBar': False, 'scrollZoom': True})

# --- EXECUTION ---
try:
    df_all, sun_all = get_weather_data()
    now_nz = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=12))).replace(tzinfo=None)
    s1 = sun_all.iloc[:7]
    st.markdown(f'<div class="section-label">{s1.iloc[0]["date"].strftime("%b %d")} - {s1.iloc[-1]["date"].strftime("%d")}</div>', unsafe_allow_html=True)
    mask1 = (df_all['time'] >= pd.Timestamp(s1.iloc[0]['date'])) & (df_all['time'] < pd.Timestamp(s1.iloc[-1]['date']) + pd.Timedelta(days=1))
    render_forecast_block(df_all[mask1], s1, show_now_line=True, now_ts=now_nz)
    st.markdown("<hr style='border: 0; border-top: 1px solid rgba(255,255,255,0.1); margin: 1rem 0;'>", unsafe_allow_html=True)
    s2 = sun_all.iloc[7:14]
    if not s2.empty:
        st.markdown(f'<div class="section-label">{s2.iloc[0]["date"].strftime("%b %d")} - {s2.iloc[-1]["date"].strftime("%d")}</div>', unsafe_allow_html=True)
        mask2 = (df_all['time'] >= pd.Timestamp(s2.iloc[0]['date'])) & (df_all['time'] < pd.Timestamp(s2.iloc[-1]['date']) + pd.Timedelta(days=1))
        render_forecast_block(df_all[mask2], s2)
except Exception as e:
    st.error(f"Error loading forecast: {e}")
