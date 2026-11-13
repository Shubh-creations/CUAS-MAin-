from setuptools import setup, find_packages

setup(
    name="cuas",
    version="2.5.0",
    description="Counter-Unmanned Aerial System (AI-Native Autonomous Defense)",
    author="Shubham Pawar",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "torch",
        "torchvision",
        "opencv-python",
        "numpy",
        "PyQt5",
        "pyyaml",
        "psutil"
    ],
    entry_points={
        "console_scripts": [
            "cuas-cli=cli:main",
            "cuas-c2=main:main",
        ]
    }
)
