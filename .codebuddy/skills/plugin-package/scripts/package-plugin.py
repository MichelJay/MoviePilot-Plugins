import os
import zipfile
import shutil
import sys
import subprocess
import argparse

def find_command(cmd):
    candidates = [cmd]
    if sys.platform == "win32":
        candidates.extend([f"{cmd}.cmd", f"{cmd}.exe", f"{cmd}.ps1"])
    for candidate in candidates:
        try:
            subprocess.run([candidate, "--version"], capture_output=True, text=True, check=True)
            return candidate
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    return None

def build_frontend(plugin_dir):
    frontend_dir = os.path.join(plugin_dir, "frontend")
    if not os.path.exists(frontend_dir):
        print("  未找到 frontend 目录，跳过前端构建")
        return
    
    package_json = os.path.join(frontend_dir, "package.json")
    if not os.path.exists(package_json):
        print("  未找到 package.json，跳过前端构建")
        return
    
    print("  开始前端构建...")
    
    npm_cmd = "npm"
    yarn_path = os.path.join(frontend_dir, "yarn.lock")
    if os.path.exists(yarn_path):
        yarn_cmd = find_command("yarn")
        if yarn_cmd:
            npm_cmd = yarn_cmd
        else:
            print("  yarn 不可用，回退到 npm")
    
    npm_cmd = find_command(npm_cmd) or find_command("npm")
    if not npm_cmd:
        print("  错误：npm 和 yarn 都不可用，无法构建前端")
        sys.exit(1)
    
    env = os.environ.copy()
    proxy_vars = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "NO_PROXY", "no_proxy"]
    for var in proxy_vars:
        if var in env:
            del env[var]
    
    try:
        if "yarn" in npm_cmd.lower():
            subprocess.run([npm_cmd, "build"], cwd=frontend_dir, check=True, capture_output=True, text=True, env=env)
        else:
            subprocess.run([npm_cmd, "run", "build"], cwd=frontend_dir, check=True, capture_output=True, text=True, env=env)
        print("  前端构建成功")
    except subprocess.CalledProcessError as e:
        print(f"  前端构建失败: {e.stderr}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="打包 MoviePilot 插件")
    parser.add_argument("--plugin", default="subscribeassistantenhancedpro", help="插件名称")
    parser.add_argument("--skip-frontend", action="store_true", help="跳过前端构建")
    args = parser.parse_args()
    
    plugin_name = args.plugin
    plugin_dir = os.path.join("plugins.v2", plugin_name)
    
    if not os.path.exists(plugin_dir):
        print(f"错误：插件目录不存在: {plugin_dir}")
        sys.exit(1)
    
    version = "0.6.11"
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    
    zip_path = os.path.join(output_dir, f"{plugin_name}_{version}.zip")
    
    if os.path.exists(zip_path):
        os.remove(zip_path)
    
    dist_dir = os.path.join(plugin_dir, "dist")
    frontend_dist_dir = os.path.join(plugin_dir, "frontend", "dist")
    
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir)
        print(f"已清理: {dist_dir}")
    
    if os.path.exists(frontend_dist_dir):
        shutil.rmtree(frontend_dist_dir)
        print(f"已清理: {frontend_dist_dir}")
    
    if not args.skip_frontend:
        build_frontend(plugin_dir)
    
    def should_skip(file_path):
        rel_path = os.path.relpath(file_path, plugin_dir)
        skip_patterns = [
            "__pycache__",
            ".git",
            ".DS_Store",
            "node_modules",
            ".vscode",
            "*.log",
            "frontend/src",
            "frontend/node_modules",
            "frontend/.git",
            "frontend/package.json",
            "frontend/package-lock.json",
            "frontend/yarn.lock",
            "frontend/vite.config.ts",
            "frontend/tsconfig.json",
            "frontend/README.md",
            "frontend/dist",
        ]
        
        for pattern in skip_patterns:
            if pattern.startswith("*."):
                if file_path.endswith(pattern[1:]):
                    return True
            elif pattern in rel_path or pattern in file_path:
                return True
        
        return False
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(plugin_dir):
            for f in files:
                full_path = os.path.join(root, f)
                if should_skip(full_path):
                    continue
                rel_path = os.path.relpath(full_path, plugin_dir)
                arcname = os.path.join(plugin_name, rel_path).replace('\\', '/')
                zf.write(full_path, arcname)
    
    file_size = os.path.getsize(zip_path) / 1024 / 1024
    print(f"打包完成！")
    print(f"文件: {zip_path}")
    print(f"大小: {file_size:.2f} MB")

if __name__ == "__main__":
    main()