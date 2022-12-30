import os

from setuptools import setup, find_packages, Command


class CleanCommand(Command):
    """Custom clean command to tidy up the project root."""
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        os.system('rm -vrf ./build ./dist ./*.pyc ./*.tgz ./*.egg-info')


# Further down when you call setup()
setup(
    cmdclass={
        'clean': CleanCommand,
    },
    name="dingtou",
    version="1.0",
    description="dingtou",
    author="piginzoo",
    zip_safe=False,
    author_email="piginzoo@qq.com",
    url="https://github.com/piginzoo/quant_research.git",
    license="LGPL",
    packages=find_packages(where=".", exclude=('test', 'test.*', 'conf'), include=('*',))
)
