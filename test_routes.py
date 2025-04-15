import requests
from urllib.parse import urljoin
from collections import defaultdict
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib3
from tqdm import tqdm

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def load_routes(file_path):
    """加载路由文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def test_route(base_url, path):
    """测试单个路由"""
    url = urljoin(base_url.rstrip('/') + '/', path.lstrip('/'))
    try:
        response = requests.get(url, timeout=10, verify=False)
        content = response.content
        # 去除可能影响长度计算的空白字符
        content = content.strip()
        return {
            'url': url,
            'status_code': response.status_code,
            'content_length': int(response.headers.get('Content-Length', len(response.content))),
            'response_time': response.elapsed.total_seconds()
        }
    except Exception as e:
        return {
            'url': url,
            'status_code': 0,
            'content_length': 0,
            'response_time': 0,
            'error': str(e)
        }

def analyze_results(results):
    """分析测试结果，找出差异化页面和非404页面"""
    # 记录每个响应长度出现的次数
    length_count = defaultdict(int)
    
    # 统计每个响应长度出现的次数
    for result in results:
        length_count[result['content_length']] += 1
    
    # 找出独特的响应长度（只出现一次的长度）
    unique_lengths = {length for length, count in length_count.items() if 1 <= count <= 5}
    
    # 收集具有独特响应长度的页面
    unique_pages = []
    for result in results:
        if result['content_length'] in unique_lengths:
            unique_pages.append(result)
    
    # 按响应长度排序
    unique_pages.sort(key=lambda x: x['content_length'])
    
    # 收集所有非404状态码的页面
    non_404_pages = defaultdict(list)
    for result in results:
        if result['status_code'] != 404:
            non_404_pages[result['status_code']].append(result)
    
    return unique_pages, non_404_pages

def main():
    """命令行入口函数"""
    if len(sys.argv) != 3:
        print('Usage: python test_routes.py <base_url> <routes_file>')
        sys.exit(1)

    base_url = sys.argv[1]
    routes_file = sys.argv[2]

    try:
        routes_data = load_routes(routes_file)
    except Exception as e:
        print(f'Error loading routes file: {e}')
        sys.exit(1)

    all_paths = set()
    for route in routes_data:
        if 'path' in route:
            all_paths.add(route['path'])

    results = []
    with tqdm(total=len(all_paths), desc="测试进度", ncols=80) as pbar:
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_path = {executor.submit(test_route, base_url, path): path for path in all_paths}
            for future in as_completed(future_to_path):
                result = future.result()
                results.append(result)
                pbar.update(1)

    # 分析结果并找出差异化页面
    unique_pages, non_404_pages = analyze_results(results)
    
    # 输出差异化页面信息
    print('\n差异化页面列表（具有独特响应长度的页面）：')
    print('=' * 100)
    print(f"{'URL':<70} {'状态码':<8} {'响应长度(bytes)':<15}")
    print('-' * 100)
    for page in unique_pages:
        print(f"{page['url']:<70} {page['status_code']:<8} {page['content_length']:<15}")
    print('=' * 100)
    print(f'\n总计发现 {len(unique_pages)} 个差异化页面')
    
    # 输出所有非404页面信息
    print('\n所有非404页面列表：')
    for status_code, pages in non_404_pages.items():
        print(f'\n状态码 {status_code} 的页面（共 {len(pages)} 个）：')
        print('=' * 100)
        print(f"{'URL':<70} {'响应长度(bytes)':<15}")
        print('-' * 100)
        for page in pages:
            print(f"{page['url']:<70} {page['content_length']:<15}")
        print('=' * 100)

    # 保存完整测试结果到文件
    with open('route_test_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    main()