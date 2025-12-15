from setuptools import setup
from Cython.Build import cythonize
from setuptools.extension import Extension
import os

# 定义扩展模块
# name="src.ui.app" 指定了生成的 pyd 文件应该对应的包路径
# sources=["src/ui/app.py"] 指定源文件
extensions = [
    Extension(
        name="src.ui.app",
        sources=["src/ui/app.py"],
    )
]

setup(
    ext_modules=cythonize(
        extensions, 
        compiler_directives={'language_level': "3"}
    ),
)
