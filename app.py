@st.cache_data(ttl=120)
def get_front_lead_live():
    try:
        url = "https://ndbc.co.nz/centreport/weather.php" 
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://winzurf.co.nz/'
        }
        r = requests.get(url, headers=headers, timeout=10)
        # Standard parser is often more reliable for simple tables
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Find the table - some sites use multiple, so we'll grab the first one
        table = soup.find('table')
        if not table:
            return None

        for row in table.find_all('tr'):
            cells = row.find_all(['td', 'th'])
            if len(cells) < 5:
                continue
            
            # Get text from first cell (The Location Name)
            loc_name = cells[0].get_text(strip=True).lower()
            
            # Fuzzy matching: Check if 'front' and 'lead' are in the name
            if "front" in loc_name and "lead" in loc_name:
                cols = [c.get_text(strip=True) for c in cells]
                return {
                    "time": cols[1],
                    "dir": cols[2],
                    "mean": cols[3],
                    "gust": cols[4]
                }
    except Exception as e:
        # This will show up in your Streamlit logs
        st.sidebar.error(f"Scraper encountered an issue: {e}")
        return None
    return None
