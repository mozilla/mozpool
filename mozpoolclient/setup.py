from distutils.core import setup

setup(
    name='mozpoolclient',
    version='0.1.0',
    author='Zambrano, Armen',
    author_email='armenzg@mozilla.com',
    packages=['mozpoolclient'],
    scripts=[],
    url='http://pypi.python.org/pypi/MozpoolClient/',
    license='MPL',
    description='It allows you to interact with devices managed by Mozpool.',
    long_description=open('README.txt').read(),
    install_requires=[
        'requests >= 1.0.0',
    ],
)
