import setuptools

with open("README.md", mode="r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="kbot-py-client",
    version="2.0.7",
    author="Konverso",
    author_email="contact@konverso.ai",
    description="Client for Konverso Kbot",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://www.konverso.ai",
    packages=setuptools.find_packages(),
    install_requires=["requests>=2.27.1"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)
