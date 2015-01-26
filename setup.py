import glob
import os
import subprocess
import sys

from distutils import ccompiler
from distutils.command.build import build
from setuptools import setup, Command
from setuptools.command.test import test

MAJOR = 0
MINOR = 2
MICRO = 0
VERSION = '%d.%d.%d' % (MAJOR, MINOR, MICRO)

with open('README.md') as readme:
    readme_lines = readme.readlines()

description = readme_lines[3].strip()
try:
    import pandoc
    doc = pandoc.Document()
    doc.markdown = ''.join(readme_lines)
    long_description = doc.rst.replace(r'\_\_', '__')
except ImportError:
    long_description = ''.join(readme_lines[4:])


class cara_build(build):
    def run(self):
        # Have to build the .capnp files into .py files before the packages are
        # checked, otherwise these would be sub_commands.
        self.run_command('build_generator')
        self.run_command('build_included_capnp')
        super().run()


class update_submodules(Command):
    """Inspired by IPython's UpdateSubmodules:
    https://github.com/ipython/ipython/blob/01a6d2384331e07a7e8249d75f4baa49aa85069c/setupbase.py#L532
    """
    description = "Update git submodules."
    user_options = []
    initialize_options = finalize_options = lambda self: None

    def run(self):
        capnp_generic_gen = os.path.join('gen', 'capnp_generic_gen')
        if not os.path.exists(capnp_generic_gen):
            # Clone capnp_generic_gen if it doesn't exist.
            self.spawn(
                ('git clone https://github.com/chainreactionmfg/'
                 'capnp_generic_gen.git %s' % capnp_generic_gen).split())
        elif os.path.exists('.git'):
            # If we're in git, then submodule init/update
            self.spawn('git submodule update --init'.split())


class build_generator(build):
    def run(self):
        self.run_command('update_submodules')

        compiler = ccompiler.new_compiler()
        if os.getenv('CC'):
            compiler.set_executable('compiler_cc', os.getenv('CC'))
            compiler.set_executable('compiler_cxx', (
                os.getenv('CXX') or os.getenv('CC')))
            compiler.set_executable('compiler_so', os.getenv('CC'))
            compiler.set_executable('linker_exe', os.getenv('CC'))
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

    def compile_file(self, filename, target_dir):
        self.execute([
            'capnp', 'compile', '-o', 'gen/capnpc-cara', filename,
            '--src-prefix', os.path.dirname(filename)])
        output = os.path.basename(filename).replace(b'.capnp', b'_capnp.py')
        output = output.replace(b'+', b'x').replace(b'-', b'_')
        self.move_file(output.decode('ascii'), target_dir)


class build_included_capnp(build_capnp_files):
    def run(self):
        # Find c++.capnp and friends first.
        capnp_dir = self.execute(
            'pkg-config --variable=includedir capnp'.split()).strip()
        self.mkpath(os.path.join(self.build_lib, 'cara', 'capnp'))
        for filename in glob.glob(capnp_dir + b'/capnp/*.capnp'):
            # Then run capnp compile -ocara filename --src-prefix=dirname
            self.compile_file(
                filename, os.path.join(self.build_lib, 'cara', 'capnp'))


class build_test_capnp(build_capnp_files):
    def run(self):
        for filename in glob.glob(os.path.join(b'tests', b'*.capnp')):
            self.compile_file(filename, os.path.join('tests'))


class pytest(test):
    user_options = [
        ('pytest-args=', None, "Arguments to pass to py.test"),
        ('pytest-cov=', None, "Enable coverage. Choose output type: "
         "term, html, xml, annotate, or multiple with comma separation"),
    ]
    def initialize_options(self):
        super().initialize_options()
        self.pytest_args = 'tests'
        self.pytest_cov = None

    def finalize_options(self):
        super().finalize_options()
        self.test_args = []
        self.test_suite = True

    def run(self):
        self.run_command('build_generator')
        self.run_command('build_test_capnp')
        import pytest
        cov = ''
        if self.pytest_cov is not None:
            outputs = ' '.join('--cov-report %s' % output
                               for output in self.pytest_cov.split(','))
            cov = ' --no-cov-on-fail --cov cara ' + outputs
        sys.exit(pytest.main(self.pytest_args + cov))

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
        'build_included_capnp': build_included_capnp,
        'build_test_capnp': build_test_capnp,
        'update_submodules': update_submodules,
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
        'pseud': ['pseud[Tornado]>=0.1.0'],
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
