from __future__ import print_function
import os
import sys
import time
import threading
import traceback
import platform

import warnings
warnings.simplefilter("ignore")

if platform.system() == 'Windows':
    version = platform.win32_ver()

elif 'Darwin' in platform.system():
    version = platform.mac_ver()
    version = list(str(itm) for itm in version)

else:
    version = platform.linux_distribution()
    version = list(str(itm) for itm in version)


TEMPLATE = '''\
OS: {system} {version}
Python: {python_version}
Python Compiler: {compiler}
Processor: {processor}
Architecture: {architecture}
'''

PY_VERSION_STR = '.'.join(str(itm) for itm in sys.version_info[:2])


if sys.platform.startswith('win'):
    DATA_PATH = r'C:\tests'
else:
    DATA_PATH = r'/tests'


INTRO = '''\
This is going to test the functionality of the TV.
It will log all tests to the screen as well as to a series of files.
The files will be located in {0} on your HDD. If you can please Zip
the contents of that folder and attach it to a post here

https://github.com/kdschlosser/samsungctl/issues/106

it would be appreciated


I added CEC support to the library. so if you are running this from a 
Raspberry Pi and you have the HDMI plugged in and libcec installed on the Pi.
drop me a line on github and I will tell you how to get it going.

Features are Power on for legacy TV's, Source list for 2016+ TV's, 
volume and mute direct input will use CEC instead of UPNP.

press any key to continue...
'''

try:
    raw_input(INTRO.format(DATA_PATH))
except NameError:
    input(INTRO.format(DATA_PATH))

print()
print()


with open(os.path.join(DATA_PATH, 'system.log'), 'w') as f:
    f.write(
        TEMPLATE.format(
            system=platform.system(),
            version=' '.join(version),
            python_version=platform.python_version(),
            compiler=platform.python_compiler(),
            processor=platform.machine(),
            architecture=platform.architecture()[0]
        )
    )

SSDP_FILENAME = os.path.join(DATA_PATH, 'ssdp_output' + PY_VERSION_STR + '.log')

if not os.path.exists(DATA_PATH):
    try:
        answer = raw_input(
            'The test directory\n' +
            DATA_PATH + '\n' +
            'does not exist..\n'
            'Would you like to create it? (y/n):'
        )
    except NameError:
        answer = input(
            'The test directory\n' +
            DATA_PATH + '\n' +
            'does not exist..\n'
            'Would you like to create it? (y/n):'
        )

    if answer.lower().startswith('y'):
        os.mkdir(DATA_PATH)
    else:
        sys.exit(1)

    print()
    print()


WRITE_LOCK = threading.RLock()


log_file = open(SSDP_FILENAME, 'w')


def print(*args):
    output = ' '.join(str(arg) for arg in args)
    sys.stdout.write(output + '\n')


class STD:
    def __init__(self, std):
        self._std = std

    def write(self, data):
        with WRITE_LOCK:
            try:
                if '\n' in data:
                    for line in data.split('\n'):
                        line = line.rstrip() + '\n'
                        log_file.write(line)
                else:
                    log_file.write(data)
                    log_file.flush()
            except:
                pass

            self._std.write(data)
            self._std.flush()

    def __getattr__(self, item):
        if item in self.__dict__:
            return self.__dict__[item]

        return getattr(self._std, item)


sys.stdout = STD(sys.stdout)
sys.stderr = STD(sys.stderr)

sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), '..')))

import samsungctl # NOQA
from samsungctl.upnp.discover import auto_discover # NOQA
import logging # NOQA

sam_logger = logging.getLogger('samsungctl')
upnp_logger = logging.getLogger('UPNP_Device')

sam_logger.setLevel(logging.DEBUG)
upnp_logger.setLevel(logging.DEBUG)

event = threading.Event()
THREADS = []

ignore_tv = []

tests_to_run = []


def discover_callback(cfg):
    if (cfg.model, cfg.host) in ignore_tv:
        return

    print('DISCOVER CALLBACK CALLED')

    tests_to_run.append(cfg)
    ignore_tv.append((cfg.model, cfg.host))
    event.set()


print('TESTING DISCOVER')
print('REGISTERING DISCOVER CALLBACK')
auto_discover.register_callback(discover_callback)
print('STARTING DISCOVER')
auto_discover.logging = True
auto_discover.start()


def run_test(config):
    global log_file

    auto_discover.logging = False
    log_path = os.path.join(DATA_PATH, config.uuid + '.' + PY_VERSION_STR + '.log')
    with WRITE_LOCK:
        log_file.close()
        log_file = open(log_path, 'w')

    print('FOUND TV')
    print(config)
    try:
        answer = raw_input('Run tests on TV ' + str(config.model) + '? ((y/n):')
    except:
        answer = input('Run tests on TV ' + str(config.model) + '? ((y/n):')

    if not answer.lower().startswith('y'):
        with WRITE_LOCK:
            log_file.close()
            log_file = open(SSDP_FILENAME, 'a')

        auto_discover.logging = True
        return

    print()
    print()

    config_file = os.path.join(DATA_PATH, config.uuid + '.config')
    if os.path.exists(config_file):
        config = samsungctl.Config.load(config_file)
    else:
        config.path = config_file
        config.save()

    config.log_level = logging.DEBUG

    POWER_ON = []
    POWER_OFF = []

    def power_callback(conf, state):
        if state:
            for c in POWER_OFF[:]:
                if c == conf:
                    POWER_ON.append(conf)
                    POWER_OFF.remove(conf)
                    print('Power Test Callback')
                    print(conf)
                    print('state =', state)
                    break
            else:
                for c in POWER_ON[:]:
                    if c == conf:
                        break
                else:
                    POWER_ON.append(conf)
                    print('Power Test Callback')
                    print(conf)
                    print('state =', state)
            return

        for c in POWER_ON[:]:
            if c == conf:
                POWER_OFF.append(conf)
                POWER_ON.remove(conf)
                print('Power Test Callback')
                print(conf)
                print('state =', state)
                break
        else:
            for c in POWER_OFF[:]:
                if c == conf:
                    break
            else:
                POWER_OFF.append(conf)
                print('Power Test Callback')
                print(conf)
                print('state =', state)

    auto_discover.register_callback(power_callback, uuid=config.uuid)

    if config.method == 'encrypted':
        print('Testing PIN get function')
        _old_get_pin = config.get_pin

        def get_pin():
            with WRITE_LOCK:
                pin = _old_get_pin()
                print('PIN function test complete')
                return pin

        config.get_pin = get_pin

    print('SETTING UP REMOTE')

    try:
        remote = samsungctl.Remote(config)
        remote.open()
        config.save()
    except:
        traceback.print_exc()
        sys.exit(1)

    print('Remote created')

    def run_method(method, ret_val_names, *args):
        print(method)
        try:
            ret_vals = getattr(remote, method)(*args)

            if ret_val_names:
                if ret_vals == [None] * len(ret_val_names):
                    print(method + ': UNSUPPORTED')
                    return [None] * len(ret_val_names)
                for i, name in enumerate(ret_val_names):
                    print(name, '=', repr(ret_vals[i]))

                return ret_vals

            print('return value:', repr(ret_vals))

            return ret_vals
        except:
            traceback.print_exc()
            if ret_val_names:
                return [None] * len(ret_val_names)
            return None

        finally:
            print('\n')

    def get_property(property_name, ret_val_names):
        print(property_name)
        try:
            ret_vals = getattr(remote, property_name)

            if ret_val_names:
                if ret_vals == [None] * len(ret_val_names):
                    print(property_name + ': UNSUPPORTED')
                    return [None] * len(ret_val_names)

                for i, name in enumerate(ret_val_names):
                    print(name, '=', repr(ret_vals[i]))

                return ret_vals

            print('Returned Value:', repr(ret_vals))

            return ret_vals
        except:
            traceback.print_exc()

            if ret_val_names:
                return [None] * len(ret_val_names)

            return None

        finally:
            print('\n')

    def set_property(property_name, value):
        print(property_name)
        try:
            setattr(remote, property_name, value)
        except:
            traceback.print_exc()

        print('\n')

    print('\nMISC TESTS\n')

    get_property('tv_options', [])
    get_property('dtv_information', [])
    get_property('operating_system', [])
    get_property('frame_tv_support', [])
    get_property('game_pad_support', [])
    get_property('dmp_drm_playready', [])
    get_property('dmp_drm_widevine', [])
    get_property('dmp_available', [])
    get_property('eden_available', [])
    get_property('apps_list_available', [])
    get_property('ime_synced_support', [])
    get_property('remote_four_directions', [])
    get_property('remote_touch_pad', [])
    get_property('voice_support', [])
    get_property('firmware_version', [])
    get_property('network_type', [])
    get_property('resolution', [])
    get_property('token_auth_support', [])
    get_property('wifi_mac', [])
    get_property('device_id', [])
    get_property('panel_technology', [])
    get_property('panel_type', [])
    get_property('panel_size', [])
    get_property('model', [])
    get_property('year', [])
    get_property('region', [])
    get_property('tuner_count', [])
    get_property('dtv_support', [])
    get_property('pvr_support', [])
    get_property('current_time', [])
    get_property('network_information', [])
    get_property('service_capabilities', [])
    get_property('stopped_reason', [])
    get_property('banner_information', [])
    get_property('schedule_list_url', [])
    get_property('acr_current_channel_name', [])
    get_property('acr_current_program_name', [])
    get_property('acr_message', [])
    get_property('ap_information', [])
    get_property('available_actions', [])
    get_property('hts_speaker_layout', [])
    get_property('mbr_device_list', [])
    get_property('mbr_dongle_status', [])
    get_property('tv_location', [])
    get_property('antenna_modes', [])
    get_property('bluetooth_support', [])
    get_property('stream_support', [])
    run_method('list_presets', [])

    get_property(
        'watching_information',
        ['tv_mode', 'information']
    )
    get_property(
        'device_capabilities',
        ['play_media', 'rec_media', 'rec_quality_modes']
    )
    get_property(
        'protocol_info',
        ['source', 'sink']
    )
    get_property(
        'byte_position_info',
        ['track_size', 'relative_byte', 'absolute_byte']
    )
    get_property(
        'position_info',
        ['track', 'track_duration', 'track_metadata', 'track_uri',
            'relative_time', 'absolute_time', 'relative_count', 'absolute_count']
    )
    get_property(
        'media_info',
        ['num_tracks', 'media_duration', 'current_uri', 'current_uri_metadata',
            'next_uri', 'next_uri_metadata', 'play_medium', 'record_medium',
            'write_status']
    )

    get_property(
        'caption_state',
        ['captions', 'enabled_captions']
    )
    get_property(
        'transport_info',
        ['current_transport_state', 'current_transport_status', 'current_speed']
    )
    get_property(
        'transport_settings',
        ['play_mode', 'rec_quality_mode']
    )
    get_property('current_transport_actions', [])
    get_property(
        'video_selection',
        ['video_pid', 'video_encoding']
    )

    _program_information_url = get_property('program_information_url', [])
    if _program_information_url is not None:
        with open(os.path.join(DATA_PATH, config.uuid + '-program_information_url.' + PY_VERSION_STR + '.log'), 'w') as f:
            f.write(repr(_program_information_url))

    _current_connection_ids = get_property('current_connection_ids', [])
    if _current_connection_ids is not None:
        run_method(
            'current_connection_info',
            ['rcs_id', 'av_transport_id', 'protocol_info', 'peer_connection_manager',
                'peer_connection_id', 'direction', 'status'],
            int(_current_connection_ids[0])
        )

    _current_show_state, _current_theme_id, _total_theme_number = get_property(
        'tv_slide_show',
        ['current_show_state', 'current_theme_id', 'total_theme_number']
    )
    # set_property('tv_slide_show', (_current_show_state, _current_theme_id))

    _aspect_ratio = get_property('aspect_ratio', [])

    if _aspect_ratio is not None:
        if _aspect_ratio == 'Default':
            set_property('aspect_ratio', 'FitScreen')
        else:
            set_property('aspect_ratio', 'Default')

        time.sleep(0.5)
        get_property('aspect_ratio', [])
        time.sleep(0.5)
        set_property('aspect_ratio', _aspect_ratio)

    _play_mode = get_property('play_mode', [])

    print('\nSPEAKER TESTS\n')

    _max_distance, _all_speaker_distance = get_property(
        'hts_all_speaker_distance',
        ['max_distance', 'all_speaker_distance']
    )
    if _max_distance is not None:
        set_property('hts_all_speaker_distance', _max_distance)
        get_property(
            'hts_all_speaker_distance',
            ['max_distance', 'all_speaker_distance']
        )
        set_property('hts_all_speaker_distance', _all_speaker_distance)

    _max_level, _all_speaker_level = get_property(
        'hts_all_speaker_level',
        ['max_level', 'all_speaker_level']
    )
    if _all_speaker_level is not None:
        set_property('hts_all_speaker_level', _all_speaker_level - 1)
        get_property('hts_all_speaker_level', ['max_level', 'all_speaker_level'])
        set_property('hts_all_speaker_level', _all_speaker_level + 1)

    _sound_effect, _sound_effect_list = get_property(
        'hts_sound_effect',
        ['sound_effect', 'sound_effect_list']
    )
    if _sound_effect is not None:
        set_property('hts_sound_effect', _sound_effect)

    _speaker_channel, _speaker_lfe = get_property(
        'hts_speaker_config',
        ['speaker_channel', 'speaker_lfe']
    )

    print('\nIMAGE TESTS\n')

    _brightness = get_property('brightness', [])
    if _brightness is not None:
        set_property('brightness', 0)
        time.sleep(0.5)
        get_property('brightness', [])
        time.sleep(0.5)
        set_property('brightness', _brightness)

    _color_temperature = get_property('color_temperature', [])
    if _color_temperature is not None:
        set_property('color_temperature', 0)
        time.sleep(0.5)
        get_property('color_temperature', [])
        time.sleep(0.5)
        set_property('color_temperature', _color_temperature)

    _contrast = get_property('contrast', [])
    if _contrast is not None:
        set_property('contrast', 0)
        time.sleep(0.5)
        get_property('contrast', [])
        time.sleep(0.5)
        set_property('contrast', _contrast)

    _sharpness = get_property('sharpness', [])
    if _sharpness is not None:
        set_property('sharpness', 0)
        time.sleep(0.5)
        get_property('sharpness', [])
        time.sleep(0.5)
        set_property('sharpness', _sharpness)

    print('\nVOLUME TESTS\n')

    _mute = get_property('mute', [])
    if _mute is not None:
        set_property('mute', not _mute)
        time.sleep(0.5)
        get_property('mute', [])
        time.sleep(0.5)
        set_property('mute', _mute)

    _volume = get_property('volume', [])
    if _volume is not None:
        set_property('volume', _volume + 1)
        time.sleep(0.5)
        get_property('volume', [])
        time.sleep(0.5)
        set_property('volume', _volume - 1)
        print('VOLUME ADJUST WITH REMOTE COMMANDS')
        print('PLEASE WATCH THE TV')
        time.sleep(3)
        remote.control('KEY_VOLUP')
        time.sleep(0.5)
        try:
            response = raw_input('Did the volume go up? (y/n):')

        except:
            response = input('Did the volume go up? (y/n):')

        if response.lower().startswith('y'):
            response = True
        else:
            response = False

        print()
        print()

        print('KEY_VOLUP: ' + str(response))

        remote.control('KEY_VOLDOWN')
        time.sleep(0.5)
        try:
            response = raw_input('Did the volume go down? (y/n):')

        except:
            response = input('Did the volume go down? (y/n):')

        if response.lower().startswith('y'):
            response = True
        else:
            response = False

        print()
        print()

        print('KEY_VOLDOWN: ' + str(response))

    print('\nSOURCE TESTS\n')

    _source = get_property('source', [])
    _sources = get_property('sources', [])

    if _source is not None:
        print('source.name: ' + _source.name)
        print('source.label: ' + _source.label)
        set_property('source', 'PC')
        time.sleep(0.5)
        _source_2 = get_property('source', [])
        print('source.name: ' + _source_2.name)
        print('source.label: ' + _source_2.label)
        time.sleep(0.5)
        set_property('source', _source)

    if _sources is not None:
        for source in _sources:
            print('-' * 40)
            print('source.id: ' + str(source.id))
            print('source.name: ' + source.name)
            print('source.is_viewable: ' + str(source.is_viewable))
            print('source.is_editable: ' + str(source.is_editable))
            print('source.is_connected: ' + str(source.is_connected))
            print('source.label: ' + source.label)
            # source.label = 'TEST LABEL'
            print('source.device_name: ' + str(source.device_name))
            print('source.is_active: ' + str(source.is_active))
            print('-' * 40)

    print('\nCHANNEL TESTS\n')

    _channels = get_property('channels', [])
    _channel = get_property('channel', [])
    (
        _channel_list_version,
        _support_channel_list,
        _channel_list_url,
        _channel_list_type,
        _satellite_id,
        _sort
    ) = get_property(
        'channel_list_url',
        ['channel_list_version', 'support_channel_list', 'channel_list_url',
            'channel_list_type', 'satellite_id', 'sort']
    )

    if _channels is not None:
        for channel in _channels:
            print('channel.number: ' + str(_channel.number))
            print('channel.name: ' + str(_channel.name))
            print('channel.channel_type: ' + str(_channel.channel_type))
            # print('channel.is_recording: ' + str(_channel.is_recording))
            print('channel.is_active: ' + str(_channel.is_active))
            for content in channel:
                print('    start_time', content.start_time)
                print('    end_time', content.end_time)
                print('    title', content.title)
                print('    genre', content.genre)
                print('    series_id', content.series_id)
                print('    detail_info', content.detail_info)
                print('    detail_information', content.detail_information)

    if _channel is not None:
        print('\n')
        print('channel.number: ' + str(_channel.number))
        print('channel.name: ' + str(_channel.name))
        # print('channel.is_recording: ' + str(_channel.is_recording))
        print('channel.is_active: ' + str(_channel.is_active))

    print('\nICON TESTS\n')

    icon = get_property('icon', [])
    if icon is not None:
        print(icon)

    print('\nBROWSER TESTS\n')

    run_method('run_browser', [], 'www.microsoft.com')
    get_property('browser_mode', [])
    get_property('browser_url', [])
    run_method('stop_browser', [])

    if remote.config.method == 'websocket':
        apps = remote.applications
        for app in apps:
            print('app.name:', app.name)
            print('app.id:', app.id)
            print('app.is_running:', app.is_running)
            print('app.version:', app.version)
            print('app.is_visible:', app.is_visible)
            print('app.app_type:', app.app_type)
            print('app.position:', app.position)
            print('app.app_id:', app.app_id)
            print('app.launcher_type:', app.launcher_type)
            print('app.action_type:', app.action_type)
            print('app.mbr_index:', app.mbr_index)
            print('app.source_type_num:', app.source_type_num)
            print('app.mbr_source:', app.mbr_source)
            print('app.is_lock:', app.is_lock)
            for group in app:
                print('   ', group.title)
                for content in group:
                    print('       content.title:', content.title)
                    print('       content.app_type:', content.app_type)
                    print('       content.mbr_index:', content.mbr_index)
                    print('       content.live_launcher_type:', content.live_launcher_type)
                    print('       content.action_play_url:', content.action_play_url)
                    print('       content.service_id:', content.service_id)
                    print('       content.launcher_type:', content.launcher_type)
                    print('       content.source_type_num:', content.source_type_num)
                    print('       content.action_type:', content.action_type)
                    print('       content.app_id:', content.app_id)
                    print('       content.display_from:', content.display_from)
                    print('       content.display_until:', content.display_until)
                    print('       content.mbr_source:', content.mbr_source)
                    print('       content.id:', content.id)
                    print('       content.is_playable:', content.is_playable)
                    print('       content.subtitle:', content.subtitle)
                    print('       content.subtitle2:', content.subtitle2)
                    print('       content.subtitle3:', content.subtitle3)
    if remote.year > 2013:
        print('\nPOWER TESTS\n')
        _power = get_property('power', [])
        set_property('power', False)
        time.sleep(5)
        get_property('power', [])
        set_property('power', True)
        time.sleep(5)
        get_property('power', [])

    auto_discover.unregister_callback(power_callback, uuid=config.uuid)
    with WRITE_LOCK:
        log_file.close()
        log_file = open(SSDP_FILENAME, 'a')

    auto_discover.logging = True


start = time.time()
while time.time() - start < 10:
    event.wait(10.0)
    event.clear()
    while tests_to_run:
        run_test(tests_to_run.pop(0))
        start = time.time()


auto_discover.stop()
log_file.close()
