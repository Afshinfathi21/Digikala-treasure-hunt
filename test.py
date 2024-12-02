import asyncio
import aiohttp
import sqlite3
import os
import time
from aiohttp import ClientSession
from tenacity import retry, wait_exponential, stop_after_attempt
import threading

discovered_categories = set()
categorie_lock=asyncio.Lock()
# Database setup with thread lock
db_lock = asyncio.Lock()

def create_database():
    conn = sqlite3.connect('images.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS urls (
        id INTEGER PRIMARY KEY,
        pid INTEGER,
        url TEXT UNIQUE
    )''')

    conn.commit()
    conn.close()

async def insert_image_url(url, pid):
    async with db_lock:  # Ensure only one thread accesses the database at a time
        conn = sqlite3.connect('images.db')
        try:
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO urls (url, pid) VALUES (?, ?)", (url, pid))
            conn.commit()
        finally:
            conn.close()


# Retry decorator for network requests
@retry(wait=wait_exponential(multiplier=1, min=4, max=10), stop=stop_after_attempt(5))
async def safe_request(session, url, params=None):
    async with session.get(url, params=params) as response:
        response.raise_for_status()  # Raise an exception for HTTP errors
        return await response.json()
    

async def fetch_urls_from_database():
    conn = sqlite3.connect('images.db')
    try:
        c = conn.cursor()
        c.execute("SELECT url FROM urls")
        return [row[0] for row in c.fetchall()]
    finally:
        conn.close()


async def download_image(session, url, semaphore):
    async with semaphore:  # Ensure rate limiting
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                filename = f"image_{int(time.time() * 1000)}.jpg"
                filepath = os.path.join("images", filename)
                with open(filepath, "wb") as f:
                    f.write(await response.read())
                print(f"Downloaded {filename}")
        except Exception as e:
            print(f"Failed to download {url}: {e}")

total_image=0
async def fetch_product_images(session, product_id, semaphore):
    global total_image 
    product_url = f"https://api.digikala.com/v2/product/{product_id}/"
    print(f"Fetching images for product ID {product_id}...")
    async with semaphore:  # Ensure rate limiting
        try:
            data = await safe_request(session, product_url)
            images = data.get("data", {}).get("product", {}).get("images", {})
            urls = []

            # Extract image URLs
            if "main" in images and "url" in images["main"]:
                urls.append(images["main"]["url"][0])

            if "list" in images:
                for image in images["list"]:
                    if "url" in image:
                        urls.append(image["url"][0]) 

            if not urls:
                print(f"No images found for product ID {product_id}.")
                return

      
            tasks = []
            for url in urls:
                total_image+=1

            print(f"Completed Inserting urls for product ID {product_id}.")
        except Exception as e:
            print(f"Error fetching product {product_id}: {e}")

async def fetch_all_categories(session, base_category):

        categories_to_explore = [base_category]  
        while categories_to_explore:
            current_category = categories_to_explore.pop(0)
            if current_category in discovered_categories:
                continue  

            discovered_categories.add(current_category)
            base_url = f"https://api.digikala.com/v1/categories/{current_category}/search/"

            try:
                subcategories = await parse_categories(session, base_url)
                

                for subcat in subcategories:
                    if subcat not in discovered_categories:
                        categories_to_explore.append(subcat)
            except Exception as e:
                print(f"Failed to fetch subcategories for {current_category}: {e}")

async def parse_categories(session, base_url):

    try:
        data = await safe_request(session, base_url)
        subcategories = [
            category['url']["uri"].split('/search/category-')[-1].rstrip('/')
            for category in data.get("data", {}).get("sub_categories_best_selling", [])
        ]
        return subcategories
    except Exception as e:
        print(f"Failed to parse categories from {base_url}: {e}")
        return []

total_product=0
async def producer(queue, session, categorie, max_pages, semaphore):
    global total_product
    """Fetch product IDs and add them to the queue."""
    base_url = f"https://api.digikala.com/v1/categories/{categorie}/search/?th_no_track=1"
    for page in range(1, max_pages + 1):
        print(f"Fetching product IDs from page {page} of category {categorie}...")
        params = {"page": page}
        await parse_categories(session,base_url)
        async with semaphore:
            try:
                data = await safe_request(session, base_url, params)
                product_ids = [product["id"] for product in data.get("data", {}).get("products", [])]
                for pid in product_ids:
                    total_product+=1
                    await queue.put(pid)
                
            except Exception as e:
                print(f"Error fetching page {page} of category {categorie}: {e}")
    await queue.put(None)  # Signal this producer is done
    

async def consumer(queue, session, semaphore):
    """Consume product IDs from the queue and process them."""
    while True:
        product_id = await queue.get()
        if product_id is None:  # Termination signal
            break
        await fetch_product_images(session, product_id, semaphore)
        
    print("Consumer exiting...")
# Main logic
async def main():
    t1=time.perf_counter()
    base_url = "https://api.digikala.com/v1/categories/vehicles-spare-parts/search/"
    create_database()
    os.makedirs("images", exist_ok=True)
    max_pages = 1
    semaphore = asyncio.Semaphore(10)
    queue = asyncio.Queue()
    
    async with ClientSession() as session:
        # Parse categories
        print("Start Fetching Categories...")
        categories=await parse_categories(session,base_url)
        categories.append('vehicles-spare-parts')
        all_categories=[fetch_all_categories(session,categorie) for categorie in categories]
        await asyncio.gather(*all_categories)

        # Create producer and consumer tasks
        producer_tasks = [producer(queue, session, categorie, max_pages, semaphore) for categorie in discovered_categories]

        consumer_tasks = [consumer(queue, session, semaphore) for _ in range(5)]  # Number of consumers

        # Run producers and consumers concurrently
        await asyncio.gather(
            *producer_tasks,  # Start all producers
            *consumer_tasks,  # Start all consumers
        )
    t2=time.perf_counter()
    print(t2-t1,"sec")
    print(list(discovered_categories))
    print(len(discovered_categories))
    print(total_product)
    print(total_image)
    

if __name__ == "__main__":
    asyncio.run(main())
