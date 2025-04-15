import os
import requests
import argparse
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from time import sleep
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from tqdm import tqdm
import jsbeautifier

def format_js_file(file_path):
    """格式化单个JS文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 配置格式化选项
        opts = jsbeautifier.default_options()
        opts.indent_size = 2
        opts.space_in_empty_paren = True
        opts.preserve_newlines = True
        opts.max_preserve_newlines = 2
        opts.wrap_line_length = 0

        # 格式化JS代码
        formatted = jsbeautifier.beautify(content, opts)

        # 写回文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(formatted)

        return True
    except Exception as e:
        print(f"[ERROR] 格式化失败 {file_path}: {str(e)}")
        return False

def get_js_files(base_url, retry=3, max_depth=5):
    downloaded_urls = set()
    url_lock = Lock()
    parsed_url = urlparse(base_url)
    save_dir = os.path.join('.', parsed_url.netloc)
    
    def extract_js_urls_from_content(content, base_url):
        import re
        patterns = [
            r'(?:src|href)=["\']([^"\']*?\.js)["\']',
            r'import.*?["\']([^"\']*?\.js)["\']',
            r'require\(["\']([^"\']*?\.js)["\']',
            r'loadScript\(["\']([^"\']*?\.js)["\']'
        ]
        js_urls = set()
        for pattern in patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                full_url = urljoin(base_url, match)
                js_urls.add(full_url)
        return js_urls

    def download_js_recursive(url, current_depth=1, pbar=None):
        with url_lock:
            if current_depth > max_depth or url in downloaded_urls:
                return None
            downloaded_urls.add(url)
        return download_single_js(url, current_depth, pbar)

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Connection': 'keep-alive'
    }

    try:
        response = requests.get(base_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
    except requests.exceptions.RequestException as e:
        print(f"[WARNING] 主页面请求失败: {e}")
        return []

    js_urls = set()
    for script in soup.find_all('script', src=True):
        if src := script.get('src'):
            js_urls.add(urljoin(base_url, src))

    print(f"发现 {len(js_urls)} 个JS文件需要下载")
    os.makedirs(save_dir, exist_ok=True)

    def download_single_js(js_url, depth, pbar):
        parsed = urlparse(js_url)
        if not parsed.path.lower().endswith('.js'):
            return None

        path_segments = parsed.path.strip('/').split('/')
        filename = path_segments[-1] or 'index.js'
        local_path = os.path.join(save_dir, *path_segments)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        session = requests.Session()
        for attempt in range(retry):
            try:
                js_response = session.get(js_url, headers=headers, timeout=10)
                js_response.raise_for_status()
                js_content = js_response.text
                
                with open(local_path, 'w', encoding='utf-8') as f:
                    f.write(js_content)

                # 格式化下载的JS文件
                if format_js_file(local_path):
                    print(f"[SUCCESS] 已格式化: {local_path}")

                if pbar:
                    pbar.update(1)

                new_js_urls = extract_js_urls_from_content(js_content, js_url)
                if new_js_urls:
                    with ThreadPoolExecutor(max_workers=5) as inner_executor:
                        futures = [inner_executor.submit(download_js_recursive, new_url, depth + 1, None)
                                  for new_url in new_js_urls if new_url not in downloaded_urls]
                        for future in futures:
                            future.result()

                return os.path.relpath(local_path, '.')
            except Exception as e:
                if attempt < retry - 1:
                    sleep(1)
                else:
                    print(f"Failed: {js_url} - {str(e)}")
                    if pbar:
                        pbar.update(1)
                    return None
            finally:
                session.close()

    all_downloaded = []
    results_lock = Lock()

    def download_worker(js_url, pbar):
        if downloaded_file := download_js_recursive(js_url, 1, pbar):
            with results_lock:
                all_downloaded.append(downloaded_file)

    with tqdm(total=len(js_urls), desc="下载进度", ncols=80) as pbar:
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(download_worker, url, pbar) for url in js_urls]
            for future in futures:
                future.result()

    print(f"下载完成！共成功下载并格式化 {len(all_downloaded)} 个文件到 {save_dir}")
    return all_downloaded

def main():
    parser = argparse.ArgumentParser(description='下载指定网站的所有JS文件并进行格式化')
    parser.add_argument('url', help='目标网站URL (需包含协议，如https://)')
    parser.add_argument('--retry', type=int, default=2, help='下载失败重试次数（默认2次）')
    parser.add_argument('--depth', type=int, default=5, help='JS文件递归下载的最大深度（默认3层）')
    args = parser.parse_args()

    downloaded_files = get_js_files(args.url, args.retry, args.depth)
    
    if downloaded_files:
        parsed_url = urlparse(args.url)
        save_dir = parsed_url.netloc
        print("\n下载文件列表：")
        for file in downloaded_files:
            print(f"* {file}")

if __name__ == "__main__":
    main()