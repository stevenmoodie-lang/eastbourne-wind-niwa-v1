@st.cache_data(ttl=120) 
def get_front_lead_live():
    try:
        # We target the source provider directly for better reliability
        url = "https://ndbc.co.nz/centreport/weather.php" 
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/119.0.0.0 Safari/537.36',
            'Referer': 'https://winzurf.co.nz/'
        }
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'lxml')
        
        # Winzurf/NDBC often uses a specific table structure
        table = soup.find('table')
        if not table:
            return None

        for row in table.find_all('tr'):
            cols = [ele.text.strip() for ele in row.find_all('td')]
            # Look specifically for the "Front Lead" row
            if len(cols) > 4 and "Front Lead" in cols[0]:
                return {
                    "time": cols[1],    # Last update time
                    "dir": cols[2],     # Wind direction
                    "mean": cols[3],    # Average speed
                    "gust": cols[4]     # Max gust
                }
    except Exception as e:
        # This will show in your Streamlit logs if it fails
        print(f"Scrape Error: {e}") 
        return None
    return None
