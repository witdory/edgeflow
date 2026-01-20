#setup.py
from setuptools import setup, find_packages

setup(
    name="edgeflow",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,  # 템플릿 파일 포함 허용
    install_requires=[
        "redis",
        "kubernetes",
        "jinja2",
        "docker",
        "numpy",
        "opencv-python"
    ],
    entry_points={
        "console_scripts": [
            "edgeflow=edgeflow.__main__:main",  # 터미널에서 edgeflow 실행 시 호출
        ],
    },
)