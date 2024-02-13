from flask import Flask, jsonify, request
import requests
import re
import json
import asyncio
from playwright.async_api import async_playwright

app = Flask(__name__)

# -----------------------------
# Utility Functions
# -----------------------------

def fetch_and_filter_movies(search_url, search_text):
    try:
        response = requests.get(search_url, timeout=10)
        response.raise_for_status()
        try:
            movies_data = response.json()
            filtered_movies = [movie for movie in movies_data if search_text.lower() in movie.get('title', '').lower()]
            return filtered_movies
        except json.JSONDecodeError:
            return {"error": "Invalid JSON response"}
    except requests.RequestException as e:
        return {"error": f"Error fetching data: {e}"}

def fetch_and_format_episode_info(glink):
    datatext = raw_and_preprocess(glink)
    parsed_content = preprocess_and_parse(datatext)
    return parsed_content

def raw_and_preprocess(link):
    raw_prefix = '''>##![Image description](https://i.imgur.com/Dd8lryt.png)[SPY MOVIES](https://t.me/spymoviesofficial)
    >🚨Telegram: https://t.me/spymoviesofficial
    >Want a little tutorial? 👉[CLICK•HERE](https://rentry.co/mdgym)👈
    ```Please check tutorial, it will be worth it!```
    !!! info STREAMING LINKS:\n\n\n'''    
    purl = link.replace("https://rentry.org/", "").replace("https://rentry.co/", "")
    try:
        response = requests.get(f'https://rentry.org/api/raw/{purl}')
        content = response.json()['content']
        formatted_content = content.replace(raw_prefix, "")
        return "\n".join([ll.rstrip() for ll in formatted_content.splitlines() if ll.strip()])
    except requests.RequestException as e:
        return {"error": f"Request failed: {e}"}
    except KeyError:
        return {"error": "Unexpected response structure"}
    

def parse_series_content(content):
    parsed_data = {}
    current_season = None
    current_item = None

    for line in content.split('\n'):
        line = line.strip()
        if 'Season' in line or ('Download' in line and '[Zip File]' in line):
            if 'Season' in line:
                current_season = line
                parsed_data[current_season] = {}
                current_item = None
            elif 'Download' in line and '[Zip File]' in line:
                # Handle standalone zip file entries
                current_item = line
                if current_season:
                    parsed_data[current_season][current_item] = []
                else:
                    parsed_data[current_item] = []

        elif line.startswith('Ep') and 'p' in line:
            current_item = line
            if current_season:
                parsed_data[current_season][current_item] = []

        elif 'http' in line:
            link = line.split(' ')[-1]
            if current_item:
                parsed_data[current_season][current_item].append(link)
            elif current_season and not current_item:
                current_item = 'Download Links'
                if current_item not in parsed_data[current_season]:
                    parsed_data[current_season][current_item] = []
                parsed_data[current_season][current_item].append(link)
                
    pattern = "https://hubcloud.lol/drive/"
    for season, episodes in parsed_data.items():
        for episode, links in episodes.items():
            parsed_data[season][episode] = [link for link in links if not link.startswith(pattern)]
    return json.dumps({"data":parsed_data,"type":"series"})

def parse_movie_content(content):
    formatdata = content.replace("HubCloud [Instant DL]", "").replace("🔗 ", "").strip("\n")
    pattern = r"(.+)\s+(\bhttps://hubcloud\.lol/video/\w+\b)"
    matches = re.findall(pattern, formatdata)
    matches_dict = {match[0].strip(): match[1] for match in matches}
    return json.dumps({"data":matches_dict,"type":"movie"})

def preprocess_and_parse(content):
    if any("Ep" and "Season" in line for line in content.split('\n')):
        return parse_series_content(content)
    else:
        return parse_movie_content(content)
    
async def scrape(url):
    try:
        # Start Playwright and open a browser
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        
        # Go to the initial URL
        await page.goto(url)
        
        # Wait for the first button to be visible and get its href
        await page.wait_for_selector('a.btn.btn-primary', state='visible')
        first_button = await page.query_selector('a.btn.btn-primary')
        first_href = await first_button.get_attribute('href')
        
        # Navigate to the href obtained from the first button
        await page.goto(first_href)
        
        # Wait for the second button to be visible and get its href
        await page.wait_for_selector('a.btn.btn-success.btn-lg.h6', state='visible', timeout=10000)
        second_button = await page.query_selector('a.btn.btn-success.btn-lg.h6')
        second_href = await second_button.get_attribute('href')
        
        # Clean up and return the second href
        await browser.close()
        await playwright.stop()
        return {"success": True, "stream": second_href}
    except Exception as e:
        # Ensure resources are cleaned up on error
        if 'browser' in locals():
            await browser.close()
            await playwright.stop()
        return {"success": False, "error": str(e)}


# -----------------------------
# Flask Routes
# -----------------------------

@app.route('/')
def home():
    return jsonify({"spy-cli": "online"})

@app.route('/search', methods=['GET'])
def search_movies():
    search_text = request.args.get('query')
    if not search_text:
        return jsonify({"error": "No search text provided"}), 400

    search_url = "https://raw.githubusercontent.com/junioralive/spycli-database/main/src/spycli-database_data.json"
    matching_movies = fetch_and_filter_movies(search_url, search_text)
    return jsonify(matching_movies)

@app.route('/fetch', methods=['GET'])
def api_fetch_episode_info():
    glink = request.args.get('url')
    if not glink:
        return jsonify({"error": "No glink provided"}), 400

    try:
        episode_info_json = fetch_and_format_episode_info(glink)
        return jsonify(json.loads(episode_info_json))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
def run_scrape_sync(url):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(scrape(url))
    loop.close()
    return result

@app.route('/scrape', methods=['GET'])
def scrape_endpoint():
    url = request.args.get('url')
    if not url:
        return jsonify({"success": False, "error": "No URL provided"}), 400
    result = run_scrape_sync(url)
    return jsonify(result)

if __name__ == '__main__':
    app.run()
