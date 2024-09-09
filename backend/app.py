from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from openai import OpenAI
import requests
from bs4 import BeautifulSoup
import json
import time
import sqlite3
import math
import re

from urllib.parse import urljoin, quote

def url_join(base, path):
    return urljoin(base, path)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://gmunhoz0810.github.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MAX_PARTS_PER_QUERY = 4
MAX_CONVERSATION_HISTORY = 50
MAX_USER_MESSAGES = 50

class Query(BaseModel):
    query: str

class Conversation:
    def __init__(self):
        self.messages = [
            {"role": "system", "content": """You are a helpful assistant for a parts website called partselect. 
             Use the get_part_or_model_info function when a user asks about specific parts or models by number (if called with model number, it also returns installation instruction videos for some common parts of it).
             If you have the model's number and a user wants to find parts for it, use the search_a_models_parts_by_name function to search parts by name in a model's page (DONT USE THIS IF the user wants installation instructions, use the get_part_or_model_info with the model number for that).
             If the user wants installation instructions of a part on a model, always call the get_part_or_model_info with the model number first!
             If the user wants to check compatibility between a part and a model specifically and you have both its numbers, use the check_compatibility function.
             Remember information from previous messages and function calls to provide context-aware responses. 
             When multiple parts are queried, provide the requested information about all of them, but only what was asked.

When responding to user queries about models:
1. Only mention information that is directly relevant to the user's query.
2. Don't provide all retrieved information unless specifically asked.
3. Use your judgment to determine which information is most relevant to the user's question.
4. You MUST use the following syntax to display multimedia content (ONLY DISPLAY MULTIMIDIA LINKS THAT WERE RETURNED FROM FUNCTIONS):
   - For manuals: {{display:manual|URL|TITLE}}
   - For diagrams: {{display:diagram|URL|TITLE}}
   - For videos: {{display:video|URL|TITLE}}
5. Only include links to videos, manuals, or diagrams if they are specifically relevant to the user's query.
6. If the user asks about installation or a specific part replacement, include the relevant video or manual.
7. When display information about models, be carefull to not display too many videos/manual/diagrams. 
Try to not overwhealm the user. Keep it at maximum 3 or each per message, unless specifically asked for more.

Example usage:
- Manual: {{display:manual|https://example.com/manual.pdf|Installation Instructions}}
- Diagram: {{display:diagram|https://example.com/diagram.jpg|BOTTOM FRAME/DRY SYSTEM}}
- Video: {{display:video|https://www.youtube.com/watch?v=VIDEO_ID|Replacing the Silverware Basket}}

Maintain a helpful and informative tone, but be concise in your responses. 
Do not answer queries unrelated to appliances, installation, parts, models, partselect (the company) etc. under any circumstance, even if the user asks you to.

When handling repair queries, use the get_repair_info function. For the function to be used it needs to be called with one of these symptoms, exactly as written here:

Dishwasher:
- Not Cleaning Properly
- Not Draining
- Noisy
- Leaking
- Will Not Start
- Door Latch Failure
- Will Not Fill Water
- Will Not Dispense Detergent
- Not Drying Properly

Refrigerator:
- Noisy
- Leaking
- Will Not Start
- Not Making Ice
- Refrigerator Too Warm
- Not Dispensing Water
- Refrigerator Freezer Too Warm
- Door Sweating
- Light Not Working
- Refrigerator Too Cold
- Running Too Long
- Freezer Too Cold

Match the user's description to the closest symptom from this list.
             """}
        ]
        self.user_message_count = 0
        self.conversation_id = self.generate_conversation_id()

    def generate_conversation_id(self):
        return str(int(time.time()))

    def add_message(self, role, content, name=None):
        message = {"role": role, "content": content}
        if name:
            message["name"] = name
        self.messages.append(message)
        
        if role == "user":
            self.user_message_count += 1

        if len(self.messages) > MAX_CONVERSATION_HISTORY + 1:
            self.messages = [self.messages[0]] + self.messages[-(MAX_CONVERSATION_HISTORY):]

        self.save_message_to_db(role, content, name)

    def get_messages(self):
        return self.messages

    def save_message_to_db(self, role, content, name=None):
        conn = sqlite3.connect('conversations.db')
        c = conn.cursor()

        c.execute('''CREATE TABLE IF NOT EXISTS messages
                     (conversation_id TEXT, role TEXT, content TEXT, name TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

        c.execute("INSERT INTO messages (conversation_id, role, content, name) VALUES (?, ?, ?, ?)",
                  (self.conversation_id, role, content, name))

        conn.commit()
        conn.close()

    def is_conversation_limit_reached(self):
        return self.user_message_count >= MAX_USER_MESSAGES

    def reset(self):
        self.__init__()

conversation = Conversation()

def get_part_or_model_info(*query_items):
    print(f"Calling get_part_or_model_info function with query items: {query_items}")
    results = {}
    for item in query_items[:MAX_PARTS_PER_QUERY]:
        try:
            result = search_item(item)
            if isinstance(result, dict):
                if result.get('type') == 'error':
                    results[item] = result
                elif result.get('type') == 'model':
                    results[item] = {
                        "type": "model",
                        "model_name": result.get('model_name', 'Unknown Model'),
                        "model_url": result.get('model_url', ''),
                        "manuals": [f"{{{{display:manual|{manual.get('url', '')}|{manual.get('title', 'Manual')}}}}}" for manual in result.get('manuals', [])],
                        "diagrams": [f"{{{{display:diagram|{diagram.get('url', '')}|{diagram.get('title', 'Diagram')}}}}}" for diagram in result.get('diagrams', [])],
                        "videos": [f"{{{{display:video|{video.get('url', '')}|{video.get('title', 'Video')}}}}}" for video in result.get('videos', [])],
                        "parts_url": result.get('parts_url', '')
                    }
                elif result.get('type') == 'part':
                    results[item] = {
                        "type": "part",
                        "part_number": result.get('part_number', 'Unknown Part'),
                        "part_url": result.get('part_url', ''),
                        "image": f"{{{{display:image|{result.get('image_url', '')}|{result.get('part_number', 'Part Image')}}}}}",
                        "product_description": result.get('product_description', ''),
                        "symptoms_it_fixes": result.get('symptoms_it_fixes', ''),
                        "appliances_its_for": result.get('appliances_its_for', ''),
                        "compatible_brands": result.get('compatible_brands', ''),
                        "installation_video": f"{{{{display:video|{result.get('installation_video', '')}|Installation Video}}}}" if result.get('installation_video') != "No installation video available" else '',
                        "price": result.get('price', 'Price not available'),
                        "availability": result.get('availability', 'Availability not specified'),
                        "ps_number": result.get('ps_number', 'PartSelect Number not available'),
                        "mfg_number": result.get('mfg_number', 'Manufacturer Part Number not available'),
                        "installation_difficulty": result.get('installation_difficulty', 'Unknown'),
                        "installation_time": result.get('installation_time', 'Unknown'),
                        "review_count": result.get('review_count', 'No reviews'),
                        "rating": result.get('rating', 'No rating')
                    }
                else:
                    results[item] = result
            else:
                results[item] = {
                    "type": "error",
                    "error": f"Unexpected result type for item {item}"
                }
        except Exception as e:
            print(f"Error processing item {item}: {str(e)}")
            results[item] = {
                "type": "error",
                "error": f"Failed to process item: {str(e)}"
            }
    return results

def search_item(query: str):
    search_url = f"https://www.partselect.com/api/search/?searchterm={query}"
    print(f"Searching for item: {query}")
    
    try:
        search_response = requests.get(search_url, allow_redirects=True)
        search_response.raise_for_status()
        
        if '/Models/' in search_response.url:
            return search_model(search_response.url)
        elif 'PS' in search_response.url:
            return search_part(search_response.url)
        else:
            print(f"Item {query} not found")
            return {"error": f"Item {query} not found"}

    except requests.RequestException as e:
        print(f"Error fetching item info: {e}")
        return {"error": f"Failed to fetch data: {str(e)}"}
    except Exception as e:
        print(f"Unexpected error: {e}")
        return {"error": f"An unexpected error occurred: {str(e)}"}

def search_part(part_url: str):
    print(f"Searching part URL: {part_url}")
    
    try:
        response = requests.get(part_url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        image_url = None
        main_image_container = soup.find('div', class_='main-image-container')
        if main_image_container:
            image_link = main_image_container.find('a', id='MagicZoom-PartImage-Images')
            if image_link:
                image_url = image_link.get('href')
        
        if not image_url:
            thumbnails = soup.find('div', class_='pd__img__thumbs')
            if thumbnails:
                first_thumbnail = thumbnails.find('a', class_='js-part-img-thumb')
                if first_thumbnail:
                    image_url = first_thumbnail.get('href')
        
        product_description = soup.find('div', {'class': 'pd__description'})
        product_description = product_description.text.strip() if product_description else "No description available."
        
        troubleshooting_section = soup.select_one('.pd__wrap.row')
        symptoms_it_fixes = ""
        appliances_its_for = ""
        compatible_brands = ""

        if troubleshooting_section:
            sections = troubleshooting_section.find_all('div', class_='col-md-6 mt-3')
            
            for section in sections:
                title = section.find('div', class_='bold mb-1').get_text(strip=True)
                content = section.find('div', {'data-collapse-container': True})
                
                if content:
                    content = content.get_text(strip=True)
                else:
                    content = section.contents[-1].strip()

                if "fixes the following symptoms" in title.lower():
                    symptoms_it_fixes = content
                elif "works with the following products" in title.lower():
                    if not appliances_its_for:
                        appliances_its_for = content
                    else:
                        compatible_brands = content
        
        videos = soup.find_all('div', {'class': 'yt-video'})
        installation_video = next((video for video in videos if "How Buying OEM Parts" not in video.find('img')['title']), None)
        video_link = f"https://www.youtube.com/watch?v={installation_video['data-yt-init']}" if installation_video else "No installation video available"
        
        price_element = soup.find('span', {'class': 'price pd__price'})
        price = price_element.text.strip() if price_element else "Price not available"
        
        availability_element = soup.find('div', {'class': 'js-partAvailability'})
        availability = availability_element.text.strip() if availability_element else "Availability not specified"
        
        ps_number = soup.find(itemprop="productID")
        ps_number = ps_number.text.strip() if ps_number else "PartSelect Number not available"
        
        mfg_number = soup.find(itemprop="mpn")
        mfg_number = mfg_number.text.strip() if mfg_number else "Manufacturer Part Number not available"
        
        repair_rating_section = soup.select_one('.pd__repair-rating')
        installation_difficulty = "Unknown"
        installation_time = "Unknown"

        if repair_rating_section:
            installation_difficulty_element = repair_rating_section.select_one('.d-flex p.bold')
            if installation_difficulty_element:
                installation_difficulty = installation_difficulty_element.text.strip()

            installation_time_element = repair_rating_section.select('.d-flex p.bold')[1] if len(repair_rating_section.select('.d-flex p.bold')) > 1 else None
            if installation_time_element:
                installation_time = installation_time_element.text.strip()
        
        review_section = soup.find('a', class_='bold no-underline js-scrollTrigger', href='#CustomerReviews')
        review_count = "No reviews"
        rating = "No rating"
        if review_section:
            review_count_element = review_section.find('span', class_='rating__count')
            if review_count_element:
                review_count = review_count_element.text.strip()
            
            rating_element = review_section.find('div', class_='rating__stars__upper')
            if rating_element and 'style' in rating_element.attrs:
                width_str = rating_element['style']
                width_percentage = float(width_str.split(':')[1].strip().rstrip('%'))
                rating = round(width_percentage / 20, 1)
        
        part_info = {
            "type": "part",
            "part_number": ps_number,
            "part_url": part_url,
            "image_url": image_url,
            "product_description": product_description,
            "symptoms_it_fixes": symptoms_it_fixes,
            "appliances_its_for": appliances_its_for,
            "compatible_brands": compatible_brands,
            "installation_video": video_link,
            "price": price,
            "availability": availability,
            "ps_number": ps_number,
            "mfg_number": mfg_number,
            "installation_difficulty": installation_difficulty,
            "installation_time": installation_time,
            "review_count": review_count,
            "rating": rating
        }
        
        print(f"Retrieved information for part:")
        print(json.dumps(part_info, indent=2))
        
        return part_info
    
    except requests.RequestException as e:
        print(f"Error fetching part info: {e}")
        return {"error": f"Failed to fetch data: {str(e)}"}
    except Exception as e:
        print(f"Unexpected error: {e}")
        return {"error": f"An unexpected error occurred: {str(e)}"}

def check_compatibility(model_number: str, part_number: str):
    print(f"Checking compatibility between model {model_number} and part {part_number}")
    
    try:
        model_url = f"https://www.partselect.com/Models/{model_number}/"
        parts = get_all_parts(model_url)
        
        is_compatible = any(
            (part.get('ps_number') == part_number) or (part.get('mfg_number') == part_number)
            for part in parts
        )
        
        compatible_part = next(
            (part for part in parts if part.get('ps_number') == part_number or part.get('mfg_number') == part_number),
            None
        )
        
        print(f"Compatibility result: {'Compatible' if is_compatible else 'Not compatible'}")
        if compatible_part:
            print(f"Compatible part found: {compatible_part}")
        else:
            print(f"No compatible part found for {part_number}")
        
        return {
            "is_compatible": is_compatible,
            "model_number": model_number,
            "part_number": part_number,
            "parts_url": urljoin(model_url, 'Parts/'),
            "compatible_part": compatible_part
        }
    
    except requests.RequestException as e:
        print(f"Error checking compatibility: {e}")
        return {"error": f"Failed to fetch data: {str(e)}"}
    except Exception as e:
        print(f"Unexpected error in check_compatibility: {e}")
        return {"error": f"An unexpected error occurred: {str(e)}"}

def get_all_parts(model_url: str):
    parts = []
    parts_url = urljoin(model_url, 'Parts/')
    
    while parts_url:
        try:
            print(f"Fetching parts from: {parts_url}")
            response = requests.get(parts_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            part_items = soup.find_all('div', class_='mega-m__part')
            
            for item in part_items:
                part_info = {}
                
                ps_match = re.search(r'PartSelect #:\s*(PS\d+)', item.text)
                if ps_match:
                    part_info['ps_number'] = ps_match.group(1)
                
                mfg_match = re.search(r'Manufacturer #:\s*(\S+)', item.text)
                if mfg_match:
                    part_info['mfg_number'] = mfg_match.group(1)
                
                part_link = item.find('a', class_='bold mb-1 mega-m__part__name')
                if part_link and 'href' in part_link.attrs:
                    part_info['url'] = urljoin(parts_url, part_link['href'])
                
                if part_info:
                    parts.append(part_info)
                    print(f"Debug: Found part: {part_info}")
            
            print(f"Parts found on this page: {len(part_items)}")
            
            next_page = soup.find('li', class_='next')
            if next_page:
                next_link = next_page.find('a')
                if next_link and 'href' in next_link.attrs:
                    parts_url = urljoin(parts_url, next_link['href'])
                    print(f"Next page URL: {parts_url}")
                else:
                    print("No more pages")
                    parts_url = None
            else:
                print("No next page found")
                parts_url = None
        except Exception as e:
            print(f"Error fetching parts: {e}")
            parts_url = None
    
    print(f"Total parts found: {len(parts)}")
    return parts

def search_model(model_url: str):
    print(f"Searching model URL: {model_url}")
    
    try:
        response = requests.get(model_url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        model_name = soup.find('h1', {'class': 'title-main'})
        model_name = model_name.text.strip() if model_name else "Model name not found"
        
        manuals = []
        manual_section = soup.find('div', class_='d-flex flex-wrap mt-2 mb-4')
        if manual_section:
            manual_items = manual_section.find_all('a', class_='mega-m__manuals')
            for item in manual_items:
                title = item.find('div', class_='mega-m__manuals__title')
                title = title.text.strip() if title else "Unknown title"
                url = item.get('href', '')
                if url:
                    manuals.append({
                        "title": title,
                        "url": url
                    })
        
        diagrams = []
        diagram_section = soup.find('div', class_='row mb-3')
        if diagram_section:
            diagram_items = diagram_section.find_all('a', class_='no-underline d-block')
            for item in diagram_items:
                title = item.find('span')
                title = title.text.strip() if title else "Unknown title"
                url = item.get('href', '')
                if url:
                    diagrams.append({
                        "title": title,
                        "url": url_join(model_url, url)
                    })
        
        videos = []
        videos_url = url_join(model_url, 'Videos/')
        while videos_url:
            videos_response = requests.get(videos_url)
            videos_response.raise_for_status()
            videos_soup = BeautifulSoup(videos_response.text, 'html.parser')
            video_items = videos_soup.find_all('div', class_='yt-video')
            for item in video_items:
                title = item.find('img')
                title = title['title'] if title and 'title' in title.attrs else "Unknown title"
                video_id = item.get('data-yt-init')
                if video_id:
                    videos.append({
                        "title": title,
                        "url": f"https://www.youtube.com/watch?v={video_id}"
                    })
            
            next_page = videos_soup.find('li', class_='next')
            next_link = next_page.find('a') if next_page else None
            if next_link and 'href' in next_link.attrs:
                videos_url = url_join(videos_url.split('?')[0], next_link['href'])
            else:
                videos_url = None
        
        parts_url = url_join(model_url, 'Parts/')
        
        model_info = {
            "type": "model",
            "model_name": model_name,
            "model_url": model_url,
            "manuals": manuals,
            "diagrams": diagrams,
            "videos": videos,
            "parts_url": parts_url
        }
        
        print(f"Retrieved information for model:")
        print(json.dumps(model_info, indent=2))
        
        return model_info
    
    except requests.RequestException as e:
        print(f"Error fetching model info: {e}")
        return {"type": "error", "error": f"Failed to fetch data: {str(e)}"}
    except Exception as e:
        print(f"Unexpected error: {e}")
        return {"type": "error", "error": f"An unexpected error occurred: {str(e)}"}
    
def get_repair_info(appliance_type, symptom):
    formatted_symptom = symptom.replace(' ', '-')

    general_repair_url = f"https://www.partselect.com/Repair/{appliance_type}/{formatted_symptom}/"
    print(f"Fetching general repair info from: {general_repair_url}")
    return scrape_general_repair_info(general_repair_url)

def scrape_general_repair_info(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        main_content = soup.find('div', id='main')
        if not main_content:
            return {"error": "Main content not found on the page"}

        video_url = None
        video_container = main_content.find('div', class_='yt-video')
        if video_container and 'data-yt-init' in video_container.attrs:
            video_url = f"https://www.youtube.com/watch?v={video_container['data-yt-init']}"

        repair_stats = main_content.find('div', class_='repair__intro')
        repair_info = {}
        if repair_stats:
            difficulty = repair_stats.find('li', string=lambda text: 'Rated as' in text if text else False)
            repair_stories = repair_stats.find('li', string=lambda text: 'repair stories' in text if text else False)
            step_videos = repair_stats.find('li', string=lambda text: 'step by step videos' in text if text else False)
            
            repair_info = {
                "difficulty": difficulty.text.strip() if difficulty else "Not specified",
                "repair_stories": repair_stories.text.strip() if repair_stories else "Not specified",
                "step_videos": step_videos.text.strip() if step_videos else "Not specified"
            }

        causes = []
        symptom_list = main_content.find('div', class_='symptom-list')
        if symptom_list:
            cause_sections = symptom_list.find_all('div', class_='symptom-list__desc')
            for section in cause_sections:
                cause_title = section.find_previous('h2', class_='section-title')
                cause_description = section.find('div', class_='col-lg-6')
                if cause_title and cause_description:
                    causes.append({
                        "title": cause_title.text.strip(),
                        "description": cause_description.text.strip()
                    })

        return {
            'video_url': video_url,
            'repair_info': repair_info,
            'causes': causes,
            'link_to_repair_webpage': url
        }
    except requests.RequestException as e:
        print(f"RequestException in scrape_general_repair_info: {str(e)}")
        return {"error": f"Failed to fetch the page: {str(e)}"}
    except Exception as e:
        print(f"Unexpected error in scrape_general_repair_info: {str(e)}")
        return {"error": f"An unexpected error occurred: {str(e)}"}
    
def search_a_models_parts_by_name(model_number: str, part_name: str):
    print(f"Searching for part '{part_name}' in model {model_number}")
    base_url = "https://www.partselect.com"
    parts_url = f"{base_url}/Models/{model_number}/Parts/"
    search_results = []

    try:
        session = requests.Session()
        
        search_url = f"{parts_url}?SearchTerm={quote(part_name)}"
        print(f"Searching at URL: {search_url}")
        
        while search_url:
            response = session.get(search_url)
            response.raise_for_status()
            
            print(f"Response status code: {response.status_code}")
            print(f"Response URL: {response.url}")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            no_results = soup.find('div', class_='alert alert-info')
            if no_results and "We couldn't find any parts" in no_results.text:
                print(f"No results found for '{part_name}'")
                return []
            
            part_items = soup.find_all('div', class_='mega-m__part')
            print(f"Number of part items found on this page: {len(part_items)}")
            
            for item in part_items:
                part_info = {}
                
                part_link = item.find('a', class_='bold mb-1 mega-m__part__name')
                if part_link:
                    part_info['name'] = part_link.text.strip()
                    part_info['url'] = urljoin(base_url, part_link.get('href', ''))
                    print(f"Found part: {part_info['name']}")
                
                ps_match = re.search(r'PartSelect #:\s*(PS\d+)', item.text)
                if ps_match:
                    part_info['ps_number'] = ps_match.group(1)
                    print(f"PartSelect number: {part_info['ps_number']}")
                
                mfg_match = re.search(r'Manufacturer #:\s*(\S+)', item.text)
                if mfg_match:
                    part_info['mfg_number'] = mfg_match.group(1)
                    print(f"Manufacturer number: {part_info['mfg_number']}")
                
                price_element = item.find('div', class_='mega-m__part__price')
                if price_element:
                    part_info['price'] = price_element.text.strip()
                    print(f"Price: {part_info['price']}")
                
                availability_element = item.find('div', class_='mega-m__part__avlbl')
                if availability_element:
                    part_info['availability'] = availability_element.text.strip()
                    print(f"Availability: {part_info['availability']}")
                
                # Updated image URL extraction
                image_container = item.find('a', class_='mega-m__part__img')
                if image_container:
                    picture_element = image_container.find('picture')
                    if picture_element:
                        webp_source = picture_element.find('source', type='image/webp')
                        if webp_source and 'data-srcset' in webp_source.attrs:
                            # Get the first URL from data-srcset (ignoring the 2x version)
                            part_info['image_url'] = webp_source['data-srcset'].split(',')[0].strip().split()[0]
                        else:
                            jpeg_source = picture_element.find('source', type='image/jpeg')
                            if jpeg_source and 'data-srcset' in jpeg_source.attrs:
                                # If webp is not available, use jpeg
                                part_info['image_url'] = jpeg_source['data-srcset'].split(',')[0].strip().split()[0]
                            else:
                                img_element = picture_element.find('img')
                                if img_element and 'data-src' in img_element.attrs:
                                    part_info['image_url'] = img_element['data-src']
                                else:
                                    part_info['image_url'] = "Image not available"
                    else:
                        part_info['image_url'] = "Image not available"
                else:
                    part_info['image_url'] = "Image not available"
                print(f"Image URL: {part_info['image_url']}")
                
                if part_info:
                    search_results.append(part_info)
                    print(f"Added part to results: {part_info}")
            
            next_page = soup.find('li', class_='next')
            if next_page and next_page.find('a'):
                next_link = next_page.find('a')
                if next_link and 'href' in next_link.attrs:
                    search_url = urljoin(parts_url, next_link['href'])
                    print(f"Moving to next page: {search_url}")
                else:
                    search_url = None
                    print("No more pages (next link without href)")
            else:
                search_url = None
                print("No more pages")
        
        print(f"Total parts found: {len(search_results)}")
        return search_results

    except requests.RequestException as e:
        print(f"RequestException in search_a_models_parts_by_name: {str(e)}")
        return {"error": f"Failed to search for parts: {str(e)}"}
    except Exception as e:
        print(f"Unexpected error in search_a_models_parts_by_name: {str(e)}")
        return {"error": f"An unexpected error occurred: {str(e)}"}
    
@app.post("/query")
async def process_query(query: Query):
    try:
        print(f"Received query: {query.query}")

        if conversation.is_conversation_limit_reached():
            return {"response": "This conversation is getting too long. Let's start a new one!", "conversation_ended": True}
        
        conversation.add_message("user", query.query)
        
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_part_or_model_info",
                    "description": "Get detailed information about specific parts or models by their numbers (includes installation instructions if called with a model number)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query_items": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                },
                                "description": "The part numbers, model numbers, or names to look up (maximum 4)"
                            }
                        },
                        "required": ["query_items"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_compatibility",
                    "description": "Check if a part is compatible with a specific model",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "model_number": {
                                "type": "string",
                                "description": "The model number to check compatibility for"
                            },
                            "part_number": {
                                "type": "string",
                                "description": "The part number to check compatibility for"
                            }
                        },
                        "required": ["model_number", "part_number"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_repair_info",
                    "description": "Get repair information for appliance issues. Note: Always display the videos returned by this using the special sintaxe.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "appliance_type": {
                                "type": "string",
                                "enum": ["Dishwasher", "Refrigerator"],
                                "description": "The type of appliance"
                            },
                            "symptom": {
                                "type": "string",
                                "description": "The problem or symptom the appliance is experiencing"
                            }
                        },
                        "required": ["appliance_type", "symptom"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_a_models_parts_by_name",
                    "description": "Search for parts to buy by name on a specific model's parts page",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "model_number": {
                                "type": "string",
                                "description": "The model number of the appliance"
                            },
                            "part_name": {
                                "type": "string",
                                "description": "The name or type of the part to search for"
                            }
                        },
                        "required": ["model_number", "part_name"]
                    }
                }
            }
        ]

        print("Calling OpenAI API for response")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=conversation.get_messages(),
            tools=tools,
            tool_choice="auto"
        )
        
        assistant_message = response.choices[0].message
        print(f"Assistant message: {assistant_message}")

        if assistant_message.tool_calls:
            for tool_call in assistant_message.tool_calls:
                if tool_call.function.name == "get_part_or_model_info":
                    function_args = json.loads(tool_call.function.arguments)
                    query_items = function_args.get("query_items", [])
                    print(f"AI detected query items: {query_items}")
                    item_info = get_part_or_model_info(*query_items)
                    
                    conversation.add_message("function", json.dumps(item_info), name="get_part_or_model_info")

                elif tool_call.function.name == "check_compatibility":
                    function_args = json.loads(tool_call.function.arguments)
                    model_number = function_args.get("model_number")
                    part_number = function_args.get("part_number")
                    compatibility_info = check_compatibility(model_number, part_number)
                    
                    conversation.add_message("function", json.dumps(compatibility_info), name="check_compatibility")

                elif tool_call.function.name == "get_repair_info":
                    print("Calling get_repair_info function")
                    function_args = json.loads(tool_call.function.arguments)
                    print(f"Function arguments: {function_args}")
                    repair_info = get_repair_info(
                        function_args["appliance_type"],
                        function_args["symptom"]
                    )
                    print(f"Repair info result: {repair_info}")
                    conversation.add_message("function", json.dumps(repair_info), name="get_repair_info")

                elif tool_call.function.name == "search_a_models_parts_by_name":
                    function_args = json.loads(tool_call.function.arguments)
                    model_number = function_args.get("model_number")
                    part_name = function_args.get("part_name")
                    print(f"Calling search_a_models_parts_by_name with model_number: {model_number}, part_name: {part_name}")
                    search_results = search_a_models_parts_by_name(model_number, part_name)
                    
                    if isinstance(search_results, dict) and "error" in search_results:
                        print(f"Error in search_a_models_parts_by_name: {search_results['error']}")
                        conversation.add_message("function", json.dumps({"error": search_results['error']}), name="search_a_models_parts_by_name")
                    else:
                        print(f"Search results: {json.dumps(search_results, indent=2)}")
                        conversation.add_message("function", json.dumps(search_results), name="search_a_models_parts_by_name")
            
            print("Getting final response after function calls")
            final_response = client.chat.completions.create(
                model="gpt-4o",
                messages=conversation.get_messages(),
                tools=tools,
                tool_choice="auto"
            )
            assistant_response = final_response.choices[0].message.content
        else:
            assistant_response = assistant_message.content
        
        if assistant_response is None:
            assistant_response = "I apologize, but I couldn't generate a proper response. Could you please rephrase your question?"

        conversation.add_message("assistant", assistant_response)
        
        print("Final response generated")
        print(f"Assistant response: {assistant_response}")
        
        return {
            "response": assistant_response,
            "conversation_ended": False
        }

    except Exception as e:
        print(f"An error occurred while processing the query: {str(e)}")
        error_message = f"I apologize, but I encountered an error while processing your request. Please try again or rephrase your question. Error details: {str(e)}"
        conversation.add_message("assistant", error_message)
        return {"response": error_message, "conversation_ended": False}
    
@app.post("/reset")
async def reset_conversation():
    global conversation
    conversation.reset()
    return {"message": "Conversation reset successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))