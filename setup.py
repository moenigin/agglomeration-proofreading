import setuptools

authors = [
    'Nila Moenig',
]

description = 'package to proofread and recnstruct neurons in an agglomerated ' \
              'segmentation volume using neuroglancer'

setuptools.setup(
    name='agglomeration_proofreading',
    version='0.0.1',
    author=authors,
    packages=setuptools.find_packages(),
    description=description,
    long_description=open('README.md').read(),
    install_requires=[
        'selenium',
        'neuroglancer'
    ],
    extras_require={'brainmaps_api_fcn': [
        'git+https://github.com/moenigin/brainmaps_api_fcn.git@master']}
)
