import os

from distutils import ccompiler
from distutils.command.build import build
from setuptools import setup

MAJOR = 0
MINOR = 2
MICRO = 0
VERSION = '%d.%d.%d' % (MAJOR, MINOR, MICRO)

with open('README.md') as readme:
    readme_lines = readme.readlines()

description = readme_lines[3].strip()
long_description = ''.join(readme_lines[4:])


class cara_build(build):
    sub_commands = build.sub_commands + [('build_generator', lambda _: True)]


class build_generator(build):
    def run(self):
        compiler = ccompiler.new_compiler()
        libs = ['kj', 'capnp', 'capnpc', 'stdc++', 'm']
        for lib in libs:
            compiler.add_library(lib)
        compiler.add_include_dir('gen/capnp_generic_gen')
        extra_args = '-std=c++14 -fpermissive -Wall'.split()
        # Optionally, install DeathHandler if you want segfault info.
        if os.path.exists('DeathHandler'):
            compiler.add_include_dir('DeathHandler')
            compiler.add_library('ld')
            compiler.define_macro('USE_DEATH_HANDLER', '1')
            extra_args.extend('-g -rdynamic'.split())
        objects = compiler.compile(
            ['gen/capnpc-cara.cpp'], extra_postargs=extra_args)
        [compiler.add_link_object(obj) for obj in objects]
        # Output the binary directly into the build_scripts folder
        self.mkpath(os.path.join(self.build_scripts, 'bin'))
        compiler.link_executable(
            [], 'capnpc-cara', output_dir='gen',
            extra_postargs=extra_args)

setup(
    name='cara',
    packages=['cara'],
    description=description,
    long_description=long_description,
    version=VERSION,
    license='Apache 2.0',
    author='Fahrzin Hemmati',
    author_email='fahhem@gmail.com',
    url='https://github.com/crmfg/cara',
    cmdclass={
        'build': cara_build,
        'build_generator': build_generator,
    },
    data_files=[
        ('bin', ['gen/capnpc-cara']),
    ],
    install_requires=[
        'crmfg-utils',
        'tornado',
    ],
    extras_require={
        'pseud': ['pseud[Tornado]'],
    },
    tests_require=[
        'pytest',
    ],
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: C++',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Topic :: Utilities',
        'Topic :: System :: Networking',
        'Topic :: Software Development :: Code Generators',
        'Topic :: Software Development :: Libraries',
    ]
)
