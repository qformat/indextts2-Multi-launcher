import os
import subprocess
import sys
import shutil
import glob
import json

def run_command(cmd, ignore_errors=False):
    print(f"Executing: {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0 and not ignore_errors:
        print(f"Error executing command: {cmd}")
        # 不直接退出，允许后续步骤尝试修复或继续
        return result.returncode
    return result.returncode

def update_version_file():
    """
    读取 version.json，增加补丁版本号，并写回。
    返回新的版本号字符串。
    """
    version_file = "version.json"
    if not os.path.exists(version_file):
        print(f"Warning: {version_file} not found. Skipping version update.")
        return None

    try:
        with open(version_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        current_version = data.get("version", "1.0.0")
        print(f"Current version: {current_version}")
        
        parts = current_version.split(".")
        if len(parts) >= 3:
            # Increment patch version
            try:
                parts[-1] = str(int(parts[-1]) + 1)
                new_version = ".".join(parts)
            except ValueError:
                print("Error: Could not parse version number.")
                return current_version
        else:
            new_version = current_version + ".1"
            
        data["version"] = new_version
        print(f"New version: {new_version}")
        
        with open(version_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        return new_version
    except Exception as e:
        print(f"Error updating version file: {e}")
        return None

def main():
    print("=== 开始一键更新流程 (Git 深度同步版) ===")

    skip_build = input("是否跳过版本更新和编译打包? (y/n) [默认 n]: ").strip().lower() == 'y'
    
    new_version = None
    if not skip_build:
        # 0. 自动增加版本号
        print("\n[0/4] 检查并更新版本号...")
        new_version = update_version_file()
        if new_version:
            print(f"版本号已更新为: {new_version}")
        else:
            print("版本号更新跳过或失败。")

        # 1. 自动生成 build_app.py
        print("\n[1/4] 生成编译脚本 build_app.py...")
        build_script_content = """from setuptools import setup
from Cython.Build import cythonize
from setuptools.extension import Extension
import os

extensions = [
    Extension(
        name=\"src.ui.app\",
        sources=[\"src/ui/app.py\"],
    ),
    Extension(
        name=\"src.ui.launcher_ui\",
        sources=[\"src/ui/launcher_ui.py\"],
    ),
    Extension(
        name=\"indextts.infer_v2\",
        sources=[\"indextts/infer_v2.py\"],
    ),
]

setup(
    ext_modules=cythonize(
        extensions,
        compiler_directives={\"language_level\": \"3\"},
    ),
)
"""
        try:
            with open("build_app.py", "w", encoding="utf-8") as f:
                f.write(build_script_content)
            print("build_app.py 生成成功。")
        except Exception as e:
            print(f"生成 build_app.py 失败: {e}")
            sys.exit(1)

        # 2. 编译 app.py 为 .pyd
        print("\n[2/4] 正在编译 app.py...")
        try:
            import Cython
        except ImportError:
            print("检测到未安装 Cython，正在自动安装...")
            run_command(f"{sys.executable} -m pip install Cython")

        c_files = [
            os.path.join("src", "ui", "app.c"),
            os.path.join("src", "ui", "launcher_ui.c"),
            os.path.join("indextts", "infer_v2.c"),
        ]
        for c_file in c_files:
            if os.path.exists(c_file):
                try:
                    os.remove(c_file)
                except Exception:
                    pass
        
        compile_cmd = f"{sys.executable} build_app.py build_ext --inplace"
        run_command(compile_cmd)

        expected = {
            "app": glob.glob(os.path.join("src", "ui", "app*.pyd")),
            "launcher_ui": glob.glob(os.path.join("src", "ui", "launcher_ui*.pyd")),
            "infer_v2": glob.glob(os.path.join("indextts", "infer_v2*.pyd")),
        }
        missing = [k for k, v in expected.items() if not v]
        if missing:
            print(f"警告：编译可能失败，未找到生成的 .pyd 文件：{', '.join(missing)}")
        else:
            print("编译成功：")
            print(f"- {expected['app'][0]}")
            print(f"- {expected['launcher_ui'][0]}")
            print(f"- {expected['infer_v2'][0]}")

        # 清理临时文件
        if os.path.exists("build"):
            shutil.rmtree("build", ignore_errors=True)
        for c_file in c_files:
            if os.path.exists(c_file):
                try:
                    os.remove(c_file)
                except Exception:
                    pass
    else:
        print("\n[提示] 已跳过版本更新和编译打包步骤。")

    # 3. 深度同步 Git 状态
    print("\n[3/4] 同步本地状态到暂存区...")
    
    # 3.1 添加所有变更（包括修改、新文件、删除的文件）
    # git add --all 会自动处理本地删除的文件，将其标记为删除
    print("正在执行 git add --all (处理新增、修改和删除)...")
    run_command("git add --all")
    
    # 3.2 检查并移除已追踪但被 .gitignore 忽略的文件
    # 这步是为了处理那些“之前提交过，但现在加入了 .gitignore”的文件
    print("正在检查已追踪但应被忽略的文件...")
    try:
        # git ls-files -i --exclude-standard 列出所有在索引中但匹配忽略规则的文件
        # -c (cached) 是 -i 的必须参数
        ignored_tracked_files = subprocess.check_output(
            ["git", "ls-files", "-i", "-c", "--exclude-standard"],
            text=True
        ).strip().splitlines()
        
        if ignored_tracked_files:
            print(f"发现 {len(ignored_tracked_files)} 个文件应被忽略但仍在版本控制中，正在移除...")
            for f in ignored_tracked_files:
                print(f"  - 移除缓存: {f}")
                # --cached 仅从暂存区移除，保留本地文件
                run_command(f'git rm --cached "{f}"', ignore_errors=True)
        else:
            print("没有发现需要清理的已忽略文件。")
            
    except subprocess.CalledProcessError:
        print("检查忽略文件时出错，跳过此步骤。")

    # 4. 提交并推送
    print("\n[4/4] 检查变更并推送...")
    status_cmd = "git status --porcelain"
    result = subprocess.run(status_cmd, shell=True, capture_output=True, text=True)
    
    if result.stdout.strip():
        print("检测到变更，正在提交...")
        commit_msg = f"Auto update v{new_version}: sync with .gitignore rules" if new_version else "Auto update: sync with .gitignore rules"
        run_command(f'git commit -m "{commit_msg}"')
        
        print("正在推送到远程仓库...")
        push_result = run_command("git push")
        if push_result == 0:
            print("\n=== 更新完成！已成功推送到 GitHub ===")
        else:
            print("\n=== 推送失败，请检查网络或权限 ===")
    else:
        print("\n没有检测到代码变更，无需提交。")
        print("=== 流程结束 ===")

if __name__ == "__main__":
    main()
