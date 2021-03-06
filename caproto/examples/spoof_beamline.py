#!/usr/bin/env python3

import curio
from collections import defaultdict
import caproto.curio.server as ccs
from caproto import ChannelData, ChannelString, ChannelEnum
import re


PLUGIN_TYPE_PVS = [
    (re.compile('image\\d:'), 'NDPluginStdArrays'),
    (re.compile('Stats\\d:'), 'NDPluginStats'),
    (re.compile('CC\\d:'), 'NDPluginColorConvert'),
    (re.compile('Proc\\d:'), 'NDPluginProcess'),
    (re.compile('Over\\d:'), 'NDPluginOverlay'),
    (re.compile('ROI\\d:'), 'NDPluginROI'),
    (re.compile('Trans\\d:'), 'NDPluginTransform'),
    (re.compile('netCDF\\d:'), 'NDFileNetCDF'),
    (re.compile('TIFF\\d:'), 'NDFileTIFF'),
    (re.compile('JPEG\\d:'), 'NDFileJPEG'),
    (re.compile('Nexus\\d:'), 'NDPluginNexus'),
    (re.compile('HDF\\d:'), 'NDFileHDF5'),
    (re.compile('Magick\\d:'), 'NDFileMagick'),
    (re.compile('TIFF\\d:'), 'NDFileTIFF'),
    (re.compile('HDF\\d:'), 'NDFileHDF5'),
    (re.compile('Current\\d:'), 'NDPluginStats'),
    (re.compile('SumAll'), 'NDPluginStats'),
]


class ReallyDefaultDict(defaultdict):
    def __contains__(self, key):
        return True

    def __missing__(self, key):
        if (key.endswith('-SP') or key.endswith('-I') or
                key.endswith('-RB') or key.endswith('-Cmd')):
            key, *_ = key.rpartition('-')
            return self[key]
        if key.endswith('_RBV') or key.endswith(':RBV'):
            return self[key[:-4]]
        ret = self[key] = self.default_factory(key)
        return ret


def fabricate_channel(key):
    if 'PluginType' in key:
        for pattern, val in PLUGIN_TYPE_PVS:
            if pattern.search(key):
                return ChannelString(value=val)
    elif 'ArrayPort' in key:
        return ChannelString(value=key)
    elif 'EnableCallbacks' in key:
        return ChannelEnum(value=0, enum_strings=['Disabled', 'Enabled'])
    elif 'BlockingCallbacks' in key:
        return ChannelEnum(value=0, enum_strings=['No', 'Yes'])
    return ChannelData(value=0)


def main():
    print('''
*** WARNING ***
This script spawns an EPICS IOC which responds to ALL caget, caput, camonitor
requests.  As this is effectively a PV black hole, it may affect the
performance and functionality of other IOCs on your network.
*** WARNING ***

Press return if you have acknowledged the above, or Ctrl-C to quit.''')

    try:
        input()
    except KeyboardInterrupt:
        print()
        return

    curio.run(ccs.start_server(ReallyDefaultDict(fabricate_channel),
                               bind_addr='127.0.0.1'))


if __name__ == '__main__':
    main()
