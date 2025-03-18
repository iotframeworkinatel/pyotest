from setuptools import setup, find_packages

setup(
    name='pyotest',
    version='0.1.0',
    description='Framework de testes de segurança para dispositivos IoT baseado no pytest',
    author='Pyotest Framework',
    author_email='pyotest@pyotest.com',
    packages=find_packages(),
    install_requires=[
        'pytest==7.1.2',
        'scapy==2.4.5',
        'python-nmap==0.7.1',
        'requests==2.27.1',
        'binwalk==2.3.3',
        'paho-mqtt==1.6.1'
    ],
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
)
