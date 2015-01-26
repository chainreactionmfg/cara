import glob
import os
import subprocess
import sys

from distutils import ccompiler
from distutils.command.build import build
from setuptools import setup
from setuptools.command.test import test

MAJOR = 0
MINOR = 2
MICRO = 0
VERSION = '%d.%d.%d' % (MAJOR, MINOR, MICRO)

with open('README.md') as readme:
    readme_lines = readme.readlines()

description = readme_lines[3].strip()
long_description = ''.join(readme_lines[4:])


class cara_build(build):
    def run(self):
        # Have to build the .capnp files into .py files before the packages are
        # checked, otherwise these would be sub_commands.
        self.run_command('build_generator')
        self.run_command('build_capnp_files')
        super().run()


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
        # capnp has .c++ as the extension, so to fit that world, we use .c++ as
        # well, but not that many people do so here we tell the compiler to
        # trust us that it can handle .c++.
        compiler.src_extensions = list(compiler.src_extensions) + ['.c++']
        objects = compiler.compile(
            ['gen/capnpc-cara.c++'], extra_postargs=extra_args)
        [compiler.add_link_object(obj) for obj in objects]
        compiler.link_executable(
            [], 'capnpc-cara', output_dir='gen',
            extra_postargs=extra_args)


class build_capnp_files(build):
    def execute(self, cmd):
        return subprocess.check_output(cmd)

    def run(self):
        # Find c++.capnp and friends first.
        capnp_dir = self.execute(
            'pkg-config --variable=includedir capnp'.split()).strip()
        for filename in glob.glob(capnp_dir + b'/capnp/*.capnp'):
            output = os.path.basename(filename).replace(b'.capnp', b'.py')
            output = output.replace(b'+', b'x').replace(b'-', b'_')
            # Then run capnp compile -ocara filename --src-prefix=dirname
            self.execute([
                'capnp', 'compile', '-o', 'gen/capnpc-cara', filename,
                '--src-prefix', os.path.dirname(filename)])
            self.mkpath(os.path.join(self.build_lib, 'cara', 'capnp'))
            self.move_file(
                output.decode('ascii'),
                os.path.join(self.build_lib, 'cara', 'capnp'))


class pytest(test):
    user_options = [('pytest-args=', 'a', "Arguments to pass to py.test")]
    def initialize_options(self):
        super().initialize_options()
        self.pytest_args = ['tests']

    def finalize_options(self):
        super().finalize_options()
        self.test_args = []
        self.test_suite = True

    def run(self):
        import pytest
        sys.exit(pytest.main(self.pytest_args))

setup(
    name='cara',
    packages=['cara', 'cara.capnp'],
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
        'build_capnp_files': build_capnp_files,
        'test': pytest,
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
