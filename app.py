@st.cache_data(ttl=120) 
def get_front_lead_live():
    try:
        url = "https://ndbc.co.nz/centreport/weather.php" 
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://winzurf.co.nz/'
        }
        r = requests.get(url, headers=headers, timeout=10)
        # Using html.parser for standard compatibility
        soup = BeautifulSoup(r.text, 'html.parser')
        
        table = soup.find('table')
        if not table:
            return None

        for row in table.find_all('tr'):
            # Convert whole row to lowercase and strip whitespace to find a match
            row_text = row.get_text().lower()
            if "front" in row_text and "lead" in row_text:
                cols = [ele.text.strip() for ele in row.find_all('td')]
                
                # Check if we have enough columns (Location, Time, Dir, Mean, Gust)
                if len(cols) >= 5:
                    return {
                        "time": cols[1],
                        "dir": cols[2],
                        "mean": cols[3],
                        "gust": cols[4]
                    }
    except Exception as e:
        print(f"Scrape Error: {e}") 
        return None
    return None
