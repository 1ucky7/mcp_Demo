import json
import re
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path
from mcp.server.fastmcp import FastMCP
# 导入getjs模块的功能
from getjs import get_js_files
# 导入extract_routes模块的功能
from extract_routes import process_js_files, save_routes_to_file
# 导入test_routes模块的功能
from test_routes import load_routes, test_route, analyze_results

# 初始化 MCP 服务
mcp = FastMCP("JS 路由提取与测试")

@mcp.tool()
def get_js(url: str) -> str:
    """
    下载指定网站的所有JS文件，并格式化后保存到本地目录
    参数：
        url: 目标网站的URL，如 https://xxx.xxx.com
    返回：脚本执行结果，包含下载的js，以及保存的路径，路径一般是网站域名
    """
    print(f"调试信息 - 开始下载JS文件，目标URL: {url}")
    parsed_url = urlparse(url)
    try:
        # 直接调用get_js_files函数
        downloaded_files = get_js_files(url)
        
        # 构建返回结果
        if downloaded_files:
            save_dir = parsed_url.netloc
            result = f"下载完成！共成功下载并格式化 {len(downloaded_files)} 个文件到 {save_dir}\n\n下载文件列表：\n"
            for file in downloaded_files:
                result += f"* {file}\n"
            return result
        else:
            return "没有找到或下载任何JS文件"
    except Exception as e:
        return str(e)

@mcp.tool()
def extract_routes(directory: str, output_file: str = None) -> str:
    """
    从指定目录中的JS文件提取路由信息
    参数：
        directory: 包含JS文件的目录路径
        output_file: 输出文件路径（可选，默认为'routes.json'）
    返回：提取结果的摘要信息
    """
    print(f"调试信息 - 开始提取路由，目标目录: {directory}")
    
    try:
        if not Path(directory).exists():
            return f"错误: 目录不存在 {directory}"
        
        # 如果未指定输出文件，则使用默认名称
        if not output_file:
            output_file = Path(directory) / "routes.json"
        
        # 处理JS文件并提取路由
        routes = process_js_files(directory)
        
        if not routes:
            return "未发现任何路由信息"
        
        # 保存路由信息到文件
        save_routes_to_file(routes, output_file)
        
        # 计算统计信息
        total_routes = sum(len(file_routes) for file_routes in routes.values())
        route_types = {}
        for file_routes in routes.values():
            for route in file_routes:
                route_type = route['type']
                route_types[route_type] = route_types.get(route_type, 0) + 1
        
        # 构建返回结果
        result = f"完成！发现的路由信息已保存到: {output_file}\n\n"
        result += f"统计信息:\n"
        result += f"处理的文件数: {len(routes)}\n"
        result += f"发现的路由数: {total_routes}\n\n"
        
        result += "路由类型分布:\n"
        for route_type, count in route_types.items():
            result += f"• {route_type}: {count}\n"
            
        return result
    except Exception as e:
        return f"提取路由时发生错误: {str(e)}"

@mcp.tool()
def test_routes(base_url: str, routes_file: str) -> str:
    """
    测试从JS文件中提取的路由是否可访问
    参数：
        base_url: 目标网站的基础URL，如 https://xxx.xxx.com
        routes_file: 包含路由信息的JSON文件路径
    返回：测试结果的摘要信息
    """
    print(f"调试信息 - 开始测试路由，目标URL: {base_url}, 路由文件: {routes_file}")
    
    try:
        # 加载路由文件
        if not Path(routes_file).exists():
            return f"错误: 路由文件不存在 {routes_file}"
            
        routes_data = load_routes(routes_file)
        
        # 提取所有路径
        all_paths = set()
        for route in routes_data:
            if 'path' in route:
                all_paths.add(route['path'])
                
        if not all_paths:
            return "路由文件中没有找到有效路径"
            
        # 测试所有路径
        results = []
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from tqdm import tqdm
        
        with tqdm(total=len(all_paths), desc="测试进度", ncols=80) as pbar:
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_path = {executor.submit(test_route, base_url, path): path for path in all_paths}
                for future in as_completed(future_to_path):
                    result = future.result()
                    results.append(result)
                    pbar.update(1)
        
        # 分析结果
        unique_pages, non_404_pages = analyze_results(results)
        
        # 保存完整测试结果到文件
        output_file = Path(routes_file).parent / "route_test_results.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
        # 构建返回结果
        result = f"测试完成！共测试 {len(all_paths)} 个路由，结果已保存到: {output_file}\n\n"
        
        # 差异化页面信息
        result += f"差异化页面列表（具有独特响应长度的页面）：共 {len(unique_pages)} 个\n"
        if unique_pages:
            result += f"{'URL':<70} {'状态码':<8} {'响应长度(bytes)':<15}\n"
            result += "-" * 90 + "\n"
            for page in unique_pages[:10]:  # 只显示前10个
                result += f"{page['url']:<70} {page['status_code']:<8} {page['content_length']:<15}\n"
            if len(unique_pages) > 10:
                result += f"... 还有 {len(unique_pages) - 10} 个页面 ...\n"
                
        # 非404页面信息
        result += f"\n所有非404页面统计：\n"
        for status_code, pages in non_404_pages.items():
            result += f"状态码 {status_code}: {len(pages)} 个页面\n"
            
        # 添加一些有用的页面示例
        if 200 in non_404_pages and non_404_pages[200]:
            result += f"\n状态码为200的页面示例（前5个）：\n"
            for page in non_404_pages[200][:5]:
                result += f"- {page['url']}\n"
                
        return result
    except Exception as e:
        return f"测试路由时发生错误: {str(e)}"

@mcp.tool()
def read_route_source(routes_file: str, route_path: str, context_lines: int = 20) -> str:
    """
    通过路由路径查找路由对应的js中包含的路由相关代码
    参数：
        routes_file: 包含路由信息的JSON文件路径
        route_path: 要查找的路由路径
        context_lines: 显示路由前后的代码行数，默认为20行
    返回：路由对应js中包含的路由相关代码的字符串
    """
    print(f"调试信息 - 开始查找路由源码，路由: {route_path}, 路由文件: {routes_file}")
    
    try:
        # 检查路由文件是否存在
        routes_file_path = Path(routes_file)
        if not routes_file_path.exists():
            return f"错误: 路由文件不存在 {routes_file}"
        
        # 加载路由信息
        with open(routes_file_path, 'r', encoding='utf-8') as f:
            routes_data = json.load(f)
        
        # 查找匹配的路由
        matching_routes = [route for route in routes_data if route.get('path') == route_path]
        
        if not matching_routes:
            return f"未找到路由: {route_path}"
        
        result = f"找到 {len(matching_routes)} 个匹配的路由:\n\n"
        
        # 获取路由文件所在目录
        base_dir = routes_file_path.parent
        
        # 处理每个匹配的路由
        for i, route in enumerate(matching_routes):
            source_file = route.get('source_file', '')
            route_type = route.get('type', '未知类型')
            
            result += f"[{i+1}] 路由: {route_path}\n"
            result += f"类型: {route_type}\n"
            result += f"源文件: {source_file}\n\n"
            
            # 处理可能有多个源文件的情况（以逗号分隔）
            source_files = [s.strip() for s in source_file.split(',')]
            
            for src_file in source_files:
                # 构建源文件的完整路径
                # 首先尝试相对路径
                js_file_path = base_dir /".."/ src_file
                
                try:
                    # 读取JS文件内容
                    with open(js_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        js_content = f.read()
                    
                    # 查找路由在JS文件中的位置
                    route_pattern = re.escape(route_path)
                    matches = list(re.finditer(route_pattern, js_content))
                    
                    if not matches:
                        result += f"在文件 {js_file_path.name} 中未找到路由 {route_path} 的精确匹配\n"
                        # 尝试更宽松的搜索
                        route_parts = route_path.split('/')
                        if len(route_parts) > 1:
                            last_part = route_parts[-1]
                            matches = list(re.finditer(re.escape(last_part), js_content))
                            if matches:
                                result += f"但找到了路由的最后部分 '{last_part}' 的匹配\n"
                            else:
                                result += "也未找到路由的任何部分\n\n"
                                continue
                        else:
                            result += "也未找到路由的任何部分\n\n"
                            continue
                    
                    # 获取文件的所有行
                    js_lines = js_content.splitlines()
                    total_lines = len(js_lines)
                    
                    # 对于每个匹配，显示上下文
                    for match_idx, match in enumerate(matches):
                        # 计算匹配位置所在的行号
                        line_number = js_content[:match.start()].count('\n') + 1
                        
                        # 计算上下文的起始和结束行
                        start_line = max(1, line_number - context_lines)
                        end_line = min(total_lines, line_number + context_lines)
                        
                        result += f"\n匹配 {match_idx+1}/{len(matches)} 在文件 {js_file_path.name} 的第 {line_number} 行:\n"
                        result += f"显示第 {start_line} 行到第 {end_line} 行的上下文:\n"
                        result += "```javascript\n"
                        
                        # 添加行号和代码
                        for i in range(start_line - 1, end_line):
                            line_prefix = "→ " if i + 1 == line_number else "  "
                            result += f"{line_prefix}{i+1:4d} | {js_lines[i]}\n"
                        
                        result += "```\n\n"
                        
                        # 如果有多个匹配，只显示第一个
                        if match_idx == 0 and len(matches) > 1:
                            result += f"还有 {len(matches)-1} 个匹配，仅显示第一个\n\n"
                            break
                
                except Exception as e:
                    result += f"读取文件 {js_file_path} 时发生错误: {str(e)}\n\n"
        
        return result
    
    except Exception as e:
        return f"查找路由源码时发生错误: {str(e)}"

if __name__ == "__main__":
    mcp.run(transport='stdio')