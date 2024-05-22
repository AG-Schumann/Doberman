import setuptools

with open('requirements.txt','r') as f:
    requires = [l.strip().split('=')[0] for l in f.readlines()]

setuptools.setup(name='Doberman',
                 version='5.0.0',
                 description='Doberman slow control',
                 python_requires='>=3.7',
                 packages=setuptools.find_packages(),
                 install_requires=requires
                 )
