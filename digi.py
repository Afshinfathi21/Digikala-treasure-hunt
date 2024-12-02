import asyncio
import sqlite3
import os
import time
from aiohttp import ClientSession
from tenacity import retry, wait_exponential, stop_after_attempt
import threading

discovered_categories = set() 
db_lock = asyncio.Lock()

def create_database():
    conn = sqlite3.connect('images.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS urls (
        id INTEGER PRIMARY KEY,
        url TEXT UNIQUE,
        pid INTEGER
    )''')
    conn.commit()
    conn.close()

async def insert_image_url(url, pid):
    async with db_lock:  
        conn = sqlite3.connect('images.db')
        try:
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO urls (url, pid) VALUES (?, ?)", (url, pid))
            conn.commit()
        finally:
            conn.close()

@retry(wait=wait_exponential(multiplier=1, min=4, max=10), stop=stop_after_attempt(5))
async def safe_request(session, url, params=None):
    async with session.get(url, params=params) as response:
        response.raise_for_status() 
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
    async with semaphore: 
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

async def fetch_product_images(session, product_id, semaphore): 
    product_url = f"https://api.digikala.com/v2/product/{product_id}/"
    print(f"Fetching images for product ID {product_id}...")
    async with semaphore: 
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

                  
            print(f"Completed Inserting urls for product ID {product_id}.")
            return urls
        except Exception as e:
            print(f"Error fetching product {product_id}: {e}")

async def fetch_all_categories(session, base_category,semaphore):

     
    categories_to_explore = [base_category]  

    while categories_to_explore:
        current_category = categories_to_explore.pop(0)
        if current_category in discovered_categories:
            continue  

        discovered_categories.add(current_category)
        base_url = f"https://api.digikala.com/v1/categories/{current_category}/search/"

        try:
            subcategories = await parse_categories(session, base_url,semaphore)
            

            for subcat in subcategories:
                if subcat not in discovered_categories:
                    categories_to_explore.append(subcat)
        except Exception as e:
            print(f"Failed to fetch subcategories for {current_category}: {e}")

async def parse_categories(session, base_url,semaphore):
    async with semaphore:
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


# async def fetch_product_ids(session, page_num, semaphore,categorie,base_url):
#     base_url=base_url.format(categorie)

#     params = {"page": page_num}
#     async with semaphore:  
#         try:
#             data = await safe_request(session, base_url, params)
#             print(f"Fetched product IDs for page {page_num}")

#             return [product["id"] for product in data.get("data", {}).get("products", [])]
#         except Exception as e:
#             print(f"Error fetching page {page_num}: {e}")
#             return []
total_product=0
async def fetch_product_ids(session, max_pages, semaphore,categorie,base_url):
    global total_product
    base_url=base_url.format(categorie)
    all_product=[]
    for page_num in range(1,max_pages+1):

        params = {"page": page_num}
        async with semaphore:  
            try:
                data = await safe_request(session, base_url, params)
                print(f"Fetched product IDs for page {page_num}")
                product_ids=[product["id"] for product in data.get("data", {}).get("products", [])]
                total_product+=len(product_ids)
                all_product.extend(product_ids)
            except Exception as e:
                print(f"Error fetching page {page_num}: {e}")
                return []
    return all_product


async def main():
    base_url = "https://api.digikala.com/v1/categories/vehicles-spare-parts/search/"
    t1=time.perf_counter()
    create_database()
    os.makedirs("images", exist_ok=True)
    max_pages=1
    semaphore = asyncio.Semaphore(10) 

    async with ClientSession() as session:
        tasks = []
        base_category = "vehicles-spare-parts"
        print("Fetching all categories recursively...")
        categories=await parse_categories(session,base_url,semaphore)
        categories.append(base_category)
        all_categories=[fetch_all_categories(session,categorie,semaphore) for categorie in categories]
        await asyncio.gather(*all_categories)
 
        for categorie in discovered_categories:
            print(f"Starting to fetch product IDs For categorie {categorie}")
            task= fetch_product_ids(session, max_pages, semaphore,categorie,base_url)
            tasks.append(task)
        product_ids_list = await asyncio.gather(*tasks)


        image_tasks = []
        for product_ids in product_ids_list:
            for pid in product_ids:
                image_tasks.append(fetch_product_images(session, pid, semaphore))
        image_urls=await asyncio.gather(*image_tasks)


        download_tasks = [download_image(session, url, semaphore) for url in image_urls]
        await asyncio.gather(*download_tasks)

    t2=time.perf_counter()
    print(t2-t1,'sec')


    print(f"Total Discover categorie {len(discovered_categories)}")
    # print(f"Total image for all product {count_url}")
    print(f"total product counts:{total_product}")


if __name__ == "__main__":
    asyncio.run(main())
