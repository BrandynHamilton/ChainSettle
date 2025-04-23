from setuptools import setup, find_packages

setup(
    name="chainsettle",  
    version="0.1.0", 
    packages=find_packages(),
    install_requires=[
        "pandas",
        "numpy",
        "dotenv",
        "flask[async]",
        "web3"
    ],
    author="Brandyn Hamilton",
    author_email="brandynham1120@gmail.com",
    description="Python Library for ChainSettle Nodes.",
    long_description=" ",
    long_description_content_type="text/markdown",
    url=" ",  
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",  
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
)
