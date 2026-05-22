import sys
import json
import random
from googleapiclient.discovery import build

class Search:

    def __init__(self):
        # Hardcoded API Key and CSE ID
        self.api_key = "AIzaSyDzHh4frHyxdYmwqkZL2a5WrgpqKraVddQ"
        self.cse_id = "4753b0aec5ce84a68"

    def search_google_images(self, query):
        try:
            service = build("customsearch", "v1", developerKey=self.api_key)
            res = service.cse().list(
                q=query, 
                cx=self.cse_id,
                searchType='image',
                num=10
            ).execute()
            return [item['link'] for item in res.get('items', [])]
        except Exception as e:
            print(f"Error in search_google_images: {e}", file=sys.stderr)
            return []

def main(query):  # Make sure 'query' is defined as a parameter
    search_instance = Search()
    images = search_instance.search_google_images(query)
    if images:
        selected_image = random.choice(images)
        return json.dumps({"image_url": selected_image})
    else:
        return json.dumps({"error": "No images found"})

if __name__ == "__main__":
    if len(sys.argv) > 1:
        query = ' '.join(sys.argv[1:])
        print(main(query))
    else:
        print("Usage: python image_search.py [search query]")