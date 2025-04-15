import os
import re
from pathlib import Path
import json
from collections import defaultdict

def extract_routes_from_js(file_path, base_dir):
    """从单个JS文件中提取路由信息"""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    routes = []
    
    # Vue Router 路由模式
    vue_patterns = [
        # 基础路由定义
        r'path:\s*[\'\"](.*?)[\'\"]',
        # 命名路由
        r'name:\s*[\'\"](.*?)[\'"].*?path:\s*[\'\"](.*?)[\'"]',
        # 动态路由
        r'path:\s*[\'"](.*?/:\w+.*?)[\'"]*'
    ]

    # React Router 路由模式
    react_patterns = [
        # Route组件路径
        r'<Route\s+path=[\'"](.*?)[\'"]\s*',
        # useNavigate/history.push
        r'(?:useNavigate|history\.push)\([\'\"](.*?)[\'\"]\)',
        # Link组件
        r'<Link\s+to=[\'"](.*?)[\'"]\s*'
    ]

    # 通用URL模式
    general_patterns = [
        # API endpoints
        r'(?:url|endpoint|api):\s*[\'"](/[^\'"]*?)[\'"]\s*',
        # axios/fetch请求
        r'(?:axios|fetch)\([\'\"]((?:/|https?://)[^\'\"]*?)[\'\"]',
        # 普通URL路径
        r'[\'"](/[\w\-./]+?)[\'"]'
    ]

    def is_valid_route(route_path):
        """检查路由路径是否有效"""
        # 过滤掉无效路径
        invalid_paths = {'/', '//', '.', './'}  
        if route_path in invalid_paths:
            return False
            
        # 检查路径是否只包含斜杠或点
        if all(c in './\\' for c in route_path):
            return False
            
        # 过滤掉静态资源文件路径
        static_extensions = [
            '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp',  # 图片
            '.css', '.scss', '.less',  # 样式
            '.js', '.jsx', '.ts', '.tsx',  # 脚本文件
            '.woff', '.woff2', '.ttf', '.eot', '.otf',  # 字体
            '.mp3', '.mp4', '.avi', '.mov', '.flv', '.wmv',  # 媒体
        ]
        
        # 检查路径是否以静态资源扩展名结尾
        for ext in static_extensions:
            if route_path.lower().endswith(ext):
                return False
                
        # 检查路径是否包含文件名模式（带扩展名的文件）
        if re.search(r'/[^/]+\.[a-zA-Z0-9]{2,6}(?:\?.*)?$', route_path):
            return False
            
        return True

    # 计算相对路径
    relative_path = os.path.relpath(file_path, base_dir)

    def extract_with_patterns(patterns, route_type):
        for pattern in patterns:
            matches = re.finditer(pattern, content)
            for match in matches:
                if len(match.groups()) > 1:  # 处理命名路由
                    route_name, route_path = match.group(1), match.group(2)
                    if is_valid_route(route_path):
                        routes.append({
                            'type': route_type,
                            'name': route_name,
                            'path': route_path,
                            'source_file': relative_path.replace('\\', '/')  # 使用相对路径并统一使用正斜杠
                        })
                else:
                    route_path = match.group(1)
                    if route_path and not route_path.startswith(('http://', 'https://', 'ws://', 'wss://')) and is_valid_route(route_path):
                        routes.append({
                            'type': route_type,
                            'path': route_path,
                            'source_file': relative_path.replace('\\', '/')  # 使用相对路径并统一使用正斜杠
                        })

    extract_with_patterns(vue_patterns, 'Vue路由')
    extract_with_patterns(react_patterns, 'React路由')
    extract_with_patterns(general_patterns, '通用路由')

    return routes

def process_js_files(directory):
    """处理目录下的所有JS文件"""
    all_routes = defaultdict(list)
    js_files = Path(directory).rglob('*.js')
    base_dir = Path(directory).parent  # 使用父目录作为基准目录，这样相对路径会包含当前目录名

    for js_file in js_files:
        try:
            routes = extract_routes_from_js(js_file, base_dir)
            if routes:
                # 使用相对于目录的路径作为键
                relative_path = os.path.relpath(js_file, directory)
                all_routes[relative_path].extend(routes)
        except Exception as e:
            print(f"❌ 处理文件失败 {js_file}: {str(e)}")

    return all_routes

def save_routes_to_file(routes, output_file):
    """将提取的路由信息保存到文件，并进行去重处理"""
    # 使用字典存储唯一路由，键为规范化后的路由路径
    unique_routes = {}
    
    def normalize_path(path):
        """规范化路由路径，移除多余的斜杠和点"""
        # 移除连续的斜杠
        path = re.sub(r'/+', '/', path)
        # 移除末尾的斜杠（除非路径只有一个斜杠）
        if len(path) > 1 and path.endswith('/'):
            path = path.rstrip('/')
        return path

    # 遍历所有路由并合并相同路径的路由信息
    for file_routes in routes.values():
        for route in file_routes:
            path = normalize_path(route['path'])
            route['path'] = path  # 更新为规范化后的路径
            
            if path not in unique_routes:
                unique_routes[path] = route
            else:
                # 如果路由已存在且来源文件不同，则更新来源文件信息
                existing_sources = set(unique_routes[path]['source_file'].split(', '))
                new_source = route['source_file']
                if new_source not in existing_sources:
                    existing_sources.add(new_source)
                    unique_routes[path]['source_file'] = ', '.join(sorted(existing_sources))
                
                # 如果新路由有名称而现有路由没有，则更新名称
                if 'name' in route and ('name' not in unique_routes[path] or not unique_routes[path]['name']):
                    unique_routes[path]['name'] = route['name']
    
    # 将字典转换为列表并按路径排序
    final_routes = sorted(unique_routes.values(), key=lambda x: x['path'])
    
    # 保存到文件，使用缩进格式化
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(final_routes, f, ensure_ascii=False, indent=2, sort_keys=True)

def main():
    import argparse
    parser = argparse.ArgumentParser(description='从JS文件中提取路由信息')
    parser.add_argument('directory', help='包含JS文件的目录路径')
    parser.add_argument('--output', default='routes.json', help='输出文件路径（默认：routes.json）')
    args = parser.parse_args()

    if not os.path.exists(args.directory):
        print(f"❌ 错误: 目录不存在 {args.directory}")
        return

    print(f"🔍 正在分析目录: {args.directory}")
    routes = process_js_files(args.directory)

    if routes:
        save_routes_to_file(routes, args.output)
        print(f"\n✅ 完成！发现的路由信息已保存到: {args.output}")
        
        # 打印统计信息
        total_routes = sum(len(file_routes) for file_routes in routes.values())
        print(f"\n📊 统计信息:")
        print(f"处理的文件数: {len(routes)}")
        print(f"发现的路由数: {total_routes}")
        
        # 按类型统计路由数量
        route_types = defaultdict(int)
        for file_routes in routes.values():
            for route in file_routes:
                route_types[route['type']] += 1
        
        print("\n路由类型分布:")
        for route_type, count in route_types.items():
            print(f"• {route_type}: {count}")
    else:
        print("⚠️ 未发现任何路由信息")

if __name__ == "__main__":
    main()