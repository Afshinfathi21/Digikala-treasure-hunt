# Digikala Treasure Hunt Image Scraper

This project is a Python-based script designed to scrape product images from [Digikala](https://www.digikala.com) for the purpose of participating in their treasure hunt competition. The images might contain hidden codes, and finding them could lead to rewards.

## Features

- **Recursive Category Exploration**: Automatically navigates through all subcategories starting from a base category.
- **Product Image Fetching**: Extracts image URLs for products listed under specific categories.
- **Image Downloading**: Saves images locally for manual inspection or further processing.
- **SQLite Database Support**: Maintains a record of fetched image URLs to avoid duplication.
- **Retry Mechanism**: Implements exponential backoff for handling network errors.

## How It Works

1. **Fetch Categories**: Begins with a base category and recursively fetches all subcategories.
2. **Fetch Product IDs**: Retrieves product IDs from each category.
3. **Fetch Image URLs**: Extracts image URLs from the product details.
4. **Download Images**: Downloads all fetched image URLs to a local directory.

## Challenges and Known Issues

1. **Rate Limiting**:
   - Digikala imposes rate limits, which can result in delayed responses or redirections. The current solution employs a semaphore to limit concurrent requests and exponential backoff for retries.

2. **Redirection Handling**:
   - Occasionally, Digikala redirects requests to a generic error page. This slows down the process and requires handling redirections more effectively.

3. **Performance**:
   - The script performs slowly for large-scale scrapes, especially due to the nested category exploration and multiple network requests.

4. **Incomplete Downloads**:
   - Some images might fail to download due to transient network issues or invalid URLs.

## Potential Improvements

- **Improved Redirection Handling**:
  Implement logic to detect and bypass redirection loops more efficiently.
  
- **Request Optimization**:
  Introduce batching mechanisms to reduce the number of network requests and minimize overhead.

- **Parallel Processing**:
  Utilize multiprocessing for downloading images to leverage multi-core CPUs.

- **Rate-Limit Detection**:
  Dynamically adjust request rates based on server response times or status codes.

- **Error Logging**:
  Maintain a log of failed requests for debugging and retrying.

## Installation and Usage

### Prerequisites

- Python 3.8+
- `sqlite3` (default with Python)
- Required Python libraries:
  - `aiohttp`
  - `tenacity`

Install dependencies using pip:

```bash
pip install aiohttp tenacity

git clone https://github.com/your-username/digikala-treasure-hunt.git
cd digikala-treasure-hunt



Feel free to adjust the repository URL and add a LICENSE file to align with your GitHub setup.
