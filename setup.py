from distutils.core import setup
import setuptools  # noqa F401
import versioneer


classifiers = [
    'Development Status :: 3 - Alpha',
    'Intended Audience :: Science/Research',
    'Programming Language :: Python',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.6',
    'Topic :: Scientific/Engineering :: Visualization',
    'License :: OSI Approved :: BSD License'
]


extras_require = {
    'standard': ['netifaces', 'numpy'],
    'async': ['asks', 'curio', 'trio'],
}
extras_require['complete'] = sorted(set(sum(extras_require.values(), [])))


setup(name='caproto',
      version=versioneer.get_version(),
      cmdclass=versioneer.get_cmdclass(),
      author='Daniel Allan',
      description='a sans-I/O implementation of the EPICS Channel Access '
                  'protocol',
      packages=['caproto',
                'caproto.benchmarking',
                'caproto.curio',
                'caproto.examples',
                'caproto.ioc_examples',
                'caproto.server',
                'caproto.sync',
                'caproto.tests',
                'caproto.threading',
                'caproto.trio',
                ],
      entry_points={
          'console_scripts': [
              'caproto-get = caproto.sync.client:get_cli',
              'caproto-put = caproto.sync.client:put_cli',
              'caproto-monitor = caproto.sync.client:monitor_cli',
              'caproto-repeater = caproto.sync.client:repeater_cli',
              'caproto-defaultdictserver = caproto.examples.defaultdictserver:main',
              'caproto-spoof-beamline = caproto.examples.spoof_beamline:main',
          ],
      },
      python_requires='>=3.6',
      classifiers=classifiers,
      extras_require=extras_require
      )
