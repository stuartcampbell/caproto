import curio
import pytest
import trio
import sys

import caproto as ca

from . import conftest
from .conftest import default_setup_module as setup_module  # noqa
from .conftest import default_teardown_module as teardown_module  # noqa


# skip on windows - no motorsim ioc there just yet
@pytest.mark.skipif(sys.platform == 'win32',
                    reason='win32 motorsim IOC')
def test_curio_client_example():
    from caproto.examples.curio_client_simple import main
    with curio.Kernel() as kernel:
        kernel.run(main())


# skip on windows - no motorsim ioc there just yet
@pytest.mark.skipif(sys.platform == 'win32',
                    reason='win32 motorsim IOC')
def test_trio_client_example():
    from caproto.examples.trio_client_simple import main
    trio.run(main)


def test_thread_client_example(curio_server):
    from caproto.examples.thread_client_simple import main as example_main
    server_runner, prefix, caget_pvdb = curio_server

    @conftest.threaded_in_curio_wrapper
    def client():
        example_main(pvname1=prefix + 'pi',
                     pvname2=prefix + 'str')

    with curio.Kernel() as kernel:
        kernel.run(server_runner, client)


def test_curio_server_example(prefix):
    import caproto.curio.client as client
    from caproto.ioc_examples.type_varieties import (
        pvdb)
    from caproto.curio.server import ServerExit, start_server as server_main

    commands = []

    pvdb = {prefix + key: value
            for key, value in pvdb.items()}

    async def run_client():
        # Some user function to call when subscriptions receive data.

        def user_callback(command):
            print("Subscription has received data: {}".format(command))
            commands.append(command)

        pi_pv = prefix + 'pi'
        broadcaster = client.SharedBroadcaster()
        await broadcaster.register()
        ctx = client.Context(broadcaster)
        await ctx.search(pi_pv)
        print('done searching')
        chan1 = await ctx.create_channel(pi_pv)
        chan1.register_user_callback(user_callback)
        # ...and then wait for all the responses.
        await chan1.wait_for_connection()
        reading = await chan1.read()
        print('reading:', reading)
        sub_id = await chan1.subscribe()
        await curio.sleep(0.2)
        await chan1.unsubscribe(sub_id)
        await chan1.write((5,))
        reading = await chan1.read()
        expected = 5
        actual, = reading.data
        assert actual == expected
        print('reading:', reading)
        await chan1.write((6,))
        reading = await chan1.read()
        expected = 6
        actual, = reading.data
        assert actual == expected
        print('reading:', reading)

        # Test updating metadata...
        # _fields_ = [
        #     ('status', short_t),
        #     ('severity', short_t),
        #     ('secondsSinceEpoch', ctypes.c_uint32),
        #     ('nanoSeconds', ctypes.c_uint32),
        #     ('RISC_Pad', long_t),
        # ]
        metadata = (0, 0, ca.TimeStamp(4, 0), 0)  # set timestamp to 4 seconds
        await chan1.write((7,), data_type=ca.ChannelType.TIME_DOUBLE,
                          metadata=metadata)
        reading = await chan1.read(data_type=20)
        # check reading
        expected = 7
        actual, = reading.data
        assert actual == expected
        # check timestamp
        expected = 4

        print('timestamp is', reading.metadata.stamp.as_datetime())

        actual = reading.metadata.secondsSinceEpoch
        assert actual == expected
        print('reading:', reading)

        status, severity = ca.AlarmStatus.SCAN, ca.AlarmSeverity.MAJOR_ALARM
        server_alarm = pvdb[pi_pv].alarm

        await server_alarm.write(status=status, severity=severity)

        # test acknowledge alarm status/severity
        reading = await chan1.read(data_type=ca.ChannelType.TIME_DOUBLE)
        assert reading.metadata.status == status
        assert reading.metadata.severity == severity

        # acknowledge the severity
        metadata = (severity + 1, )
        await chan1.write((),
                          data_type=ca.ChannelType.PUT_ACKS,
                          metadata=metadata)

        assert server_alarm.severity_to_acknowledge == 0

        # now make a transient alarm and toggle the severity
        # now require transients to be acknowledged
        metadata = (1, )
        await chan1.write((),
                          data_type=ca.ChannelType.PUT_ACKT,
                          metadata=metadata)

        assert server_alarm.must_acknowledge_transient

        await server_alarm.write(severity=severity)
        await server_alarm.write(severity=ca.AlarmSeverity.NO_ALARM)

        assert server_alarm.severity_to_acknowledge == severity

        # acknowledge the severity
        metadata = (severity + 1, )
        await chan1.write((),
                          data_type=ca.ChannelType.PUT_ACKS,
                          metadata=metadata)

        assert server_alarm.severity_to_acknowledge == 0

        severity = ca.AlarmSeverity.NO_ALARM

        reading = await chan1.read(data_type=ca.ChannelType.TIME_DOUBLE)
        # check reading (unchanged since last time)
        expected = 7
        actual, = reading.data
        assert actual == expected
        # check status
        actual = reading.metadata.status
        assert actual == status
        # check severity
        actual = reading.metadata.severity
        assert actual == severity

        await chan1.disconnect()
        assert commands, 'subscription not called in client'
        # await chan1.circuit.socket.close()

        commands.clear()
        await ctx.search(prefix + 'str')
        await ctx.search(prefix + 'str2')
        print('done searching')
        chan2 = await ctx.create_channel(prefix + 'str')
        chan3 = await ctx.create_channel(prefix + 'str2')
        chan2.register_user_callback(user_callback)
        chan3.register_user_callback(user_callback)
        await chan2.wait_for_connection()
        await chan3.wait_for_connection()
        sub_id2 = await chan2.subscribe()
        sub_id3 = await chan3.subscribe()
        print('write...')
        await chan2.write(b'hell')
        await chan3.write(b'good')

        print('setting alarm status...')
        await pvdb[prefix + 'str'].alarm.write(
            severity=ca.AlarmSeverity.MAJOR_ALARM)

        await curio.sleep(0.5)

        await chan2.unsubscribe(sub_id2)
        await chan3.unsubscribe(sub_id3)
        # expecting that the subscription callback should get called:
        #   1. on connection (2)
        #   2. when chan2 is written to (1)
        #   3. when chan3 is written to (1)
        #   4. when alarm status is updated for both channels (2)
        # for a total of 6
        assert len(commands) == 2 + 2 + 2

    async def task():
        async def server_wrapper():
            try:
                await server_main(pvdb)
            except ServerExit:
                print('Server exited normally')

        try:
            server_task = await curio.spawn(server_wrapper)
            await curio.sleep(1)  # Give server some time to start up.
            await run_client()
            print('client is done')
        finally:
            try:
                await server_task.cancel()
                await server_task.join()
            except curio.KernelExit:
                print('Server exited normally')

    with curio.Kernel() as kernel:
        kernel.run(task)
    print('done')


# See test_ioc_example and test_flaky_ioc_examples, below.
def _test_ioc_examples(request, module_name, pvdb_class_name, class_kwargs,
                       prefix, async_lib='curio'):
    from .conftest import run_example_ioc
    from caproto.sync.client import get, put
    from caproto.server import PvpropertyReadOnlyData
    import subprocess

    module = __import__(module_name,
                        fromlist=(module_name.rsplit('.', 1)[-1], ))

    pvdb_class = getattr(module, pvdb_class_name)

    print(f'Prefix: {prefix} PVDB class: {pvdb_class}')
    pvdb = pvdb_class(prefix=prefix, **class_kwargs).pvdb
    pvs = list(pvdb.keys())
    pv_to_check = pvs[0]

    print(f'PVs:', pvs)
    print(f'PV to check: {pv_to_check}')

    stdin = (subprocess.DEVNULL if 'io_interrupt' in module_name
             else None)

    print('stdin=', stdin)
    run_example_ioc(module_name, request=request,
                    args=['--prefix', prefix, '--async-lib', async_lib],
                    pv_to_check=pv_to_check,
                    stdin=stdin)

    print(f'{module_name} IOC now running')

    put_values = [
        (PvpropertyReadOnlyData, None),
        (ca.ChannelNumeric, [1]),
        (ca.ChannelString, ['USD']),
    ]

    skip_pvs = [('ophyd', ':exit')]

    def find_put_value(pv):
        'Determine value to write to pv'
        for skip_ioc, skip_suffix in skip_pvs:
            if skip_ioc in module_name:
                if pv.endswith(skip_suffix):
                    return None

        for put_class, put_value in put_values:
            if isinstance(channeldata, put_class):
                return put_value
        else:
            raise Exception('Failed to set default value for channeldata:'
                            f'{channeldata.__class__}')

    for pv, channeldata in pvdb.items():
        value = find_put_value(pv)
        if value is None:
            print(f'Skipping write to {pv}')
            continue

        print(f'Writing {value} to {pv}')
        put(pv, value)

        value = get(pv)
        print(f'Read {pv} = {value}')


@pytest.mark.parametrize(
    'module_name, pvdb_class_name, class_kwargs',
    [('caproto.ioc_examples.custom_write', 'CustomWrite', {}),
     ('caproto.ioc_examples.inline_style', 'InlineStyleIOC', {}),
     ('caproto.ioc_examples.io_interrupt', 'IOInterruptIOC', {}),
     ('caproto.ioc_examples.macros', 'MacroifiedNames',
      dict(macros={'beamline': 'my_beamline', 'thing': 'thing'})),
     ('caproto.ioc_examples.random_walk', 'RandomWalkIOC', {}),
     ('caproto.ioc_examples.reading_counter', 'ReadingCounter', {}),
     ('caproto.ioc_examples.rpc_function', 'MyPVGroup', {}),
     ('caproto.ioc_examples.simple', 'SimpleIOC', {}),
     ('caproto.ioc_examples.subgroups', 'MyPVGroup', {}),
     ('caproto.ioc_examples.setpoint_rbv_pair', 'Group', {}),
     ('caproto.ioc_examples.all_in_one', 'MyPVGroup',
      dict(macros={'macro': 'expanded'})),
     ]
)
@pytest.mark.parametrize('async_lib', ['curio', 'trio', 'asyncio'])
def test_ioc_examples(request, module_name, pvdb_class_name, class_kwargs,
                      prefix, async_lib):
    skip_on_windows = (
        # no areadetector ioc
        'caproto.ioc_examples.areadetector_image',
        # no termios support
        'caproto.ioc_examples.io_interrupt',
    )

    if (module_name == 'caproto.ioc_examples.io_interrupt' and
            async_lib == 'asyncio'):
        # TODO FIX ME
        raise pytest.xfail(reason='known not to work on asyncio')
    elif sys.platform == 'win32' and module_name in skip_on_windows:
        raise pytest.skip('win32 TODO')

    return _test_ioc_examples(request, module_name, pvdb_class_name,
                              class_kwargs, prefix, async_lib)


# These tests require numpy.
@pytest.mark.skipif(sys.platform == 'win32',
                    reason='win32 AD IOC')
@pytest.mark.parametrize(
    'module_name, pvdb_class_name, class_kwargs',
    [('caproto.ioc_examples.caproto_to_ophyd', 'Group', {}),
     ('caproto.ioc_examples.areadetector_image', 'DetectorGroup', {}),
     ])
def test_special_ioc_examples(request, module_name, pvdb_class_name,
                              class_kwargs, prefix):
    pytest.importorskip('numpy')
    return _test_ioc_examples(request, module_name, pvdb_class_name,
                              class_kwargs, prefix)


# Use pytest-rerunfailures plugin to try these a couple times due to flaky
# Google API calls. Ultimately, xfail.
@pytest.mark.xfail()
@pytest.mark.flaky(reruns=5, reruns_delay=2)
@pytest.mark.parametrize(
    'module_name, pvdb_class_name, class_kwargs',
    [('caproto.ioc_examples.currency_conversion_polling', 'CurrencyPollingIOC',
      {}),
     ('caproto.ioc_examples.currency_conversion', 'CurrencyConversionIOC', {}),
     ]
)
def test_flaky_ioc_examples(request, module_name, pvdb_class_name,
                            class_kwargs, prefix):
    return _test_ioc_examples(request, module_name, pvdb_class_name,
                              class_kwargs, prefix)


# skip on windows - no areadetector ioc there just yet
@pytest.mark.skipif(sys.platform == 'win32',
                    reason='win32 AD IOC')
def test_areadetector_generate():
    pytest.importorskip('numpy')
    from caproto.ioc_examples import areadetector_image

    # smoke-test the generation code
    areadetector_image.generate_detector_code()


def test_typhon_example(request, prefix):
    pytest.importorskip('numpy')
    from .conftest import run_example_ioc
    run_example_ioc('caproto.ioc_examples.caproto_to_ophyd', request=request,
                    args=['--prefix', prefix], pv_to_check=f'{prefix}random1')

    from caproto.ioc_examples import caproto_to_typhon
    caproto_to_typhon.pydm = None

    caproto_to_typhon.run_typhon(prefix=prefix)


def test_mocking_records(request, prefix):
    from .conftest import run_example_ioc
    run_example_ioc('caproto.ioc_examples.mocking_records', request=request,
                    args=['--prefix', prefix], pv_to_check=f'{prefix}A')

    from caproto.sync.client import get, put

    # check that the alarm fields are linked
    b = f'{prefix}B'
    b_val = f'{prefix}B.VAL'
    b_stat = f'{prefix}B.STAT'
    b_severity = f'{prefix}B.SEVR'
    put(b_val, 0)
    assert list(get(b_val).data) == [0]
    assert list(get(b_stat).data) == [b'NO_ALARM']
    assert list(get(b_severity).data) == [b'NO_ALARM']

    # write a special value that causes it to fail
    with pytest.raises(ca.ErrorResponseReceived):
        put(b_val, 1)

    # status should be WRITE, MAJOR
    assert list(get(b_val).data) == [0]
    assert list(get(b_stat).data) == [b'WRITE']
    assert list(get(b_severity).data) == [b'MAJOR']

    # now a field that's linked back to the precision metadata:
    b_precision = f'{prefix}B.PREC'
    assert list(get(b_precision).data) == [3]
    assert put(b_precision, 4)
    assert list(get(b_precision).data) == [4]

    # does writing to .PREC update the ChannelData metadata?
    data = get(b, data_type=ca.ChannelType.CTRL_DOUBLE)
    assert data.metadata.precision == 4
