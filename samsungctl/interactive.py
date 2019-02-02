# -*- coding: utf-8 -*-

import sys

from .key_mappings import KEY_MAPPINGS

try:
    input = raw_input
except NameError:
    pass


class Interactive(object):

    def __init__(self, remote):
        self.remote = remote

    def run(self):
        print('"help" to get a list of available commands')
        print('"quit" or ctrl+c to exit the interactive mode')
        print()

        try:
            while True:
                command = input('Please enter command:')

                if command == 'quit':
                    raise KeyboardInterrupt

                if command == 'help':

                    for group in KEY_MAPPINGS:
                        print()
                        print(group[0])
                        for description, key in group[1]:
                            print(
                                '   ',
                                description,
                                ':',
                                key,
                                'or',
                                key.split('_', 1)[-1]
                            )

                    print("volume [value]")
                    print("    Sets the TV volume to the entered value,\n")
                    print("    a value of -1 will display the volume level")
                    print()
                    print("brightness [value]")
                    print("    Sets the TV brightness to the entered value,\n")
                    print("    a value of -1 will display the brightness level")
                    print()
                    print("contrast [value]")
                    print("    Sets the TV contrast to the entered value,\n")
                    print("    a value of -1 will display the contrast level")
                    print()
                    print("sharpness [value]")
                    print("    Sets the TV sharpness to the entered value,\n")
                    print("    a value of -1 will display the sharpness level")
                    print()
                    print("mute [off, on, state]")
                    print("    Sets the mute on or off (not a toggle),\n")
                    print("    state displays if the mute if on or off")
                    print()
                    print("source [source name/label]")
                    print(
                        "    Changes the input source to the one specified.\n"
                        "      eg: HDMI1 HDMI2, USB, PC....\n"
                        "    You also have the option of entering the OSD \n"
                        "    label for the source.\n"
                        "    If you enter 'state' for the source name it\n"
                        "    will print out the currently active source name\n"
                        "    and label.\n"
                    )

                    print()
                    print('"quit" or ctrl+c to exit the interactive mode')
                    print()
                    print(
                        'To set the logging level:\n'
                        '    LOG_OFF, LOG_CRITICAL, LOG_ERROR,\n'
                        '    LOG_WARNING, LOG_INFO, LOG_DEBUG'
                    )
                    print()
                    continue

                try:
                    if command.upper().startswith('LOG'):
                        logging_commands = (
                            'LOG_OFF',
                            'LOG_CRITICAL',
                            'LOG_ERROR',
                            'LOG_WARNING',
                            'LOG_INFO',
                            'LOG_DEBUG'
                        )

                        for log_level in logging_commands:
                            if command.upper() == log_level:
                                self.remote.config.log_level = getattr(
                                    self.remote.config,
                                    log_level
                                )
                                break
                        else:
                            print('Invalid log level')
                        continue
                        
                    commands = (
                        'volume'
                        'brightness'
                        'contrast'
                        'sharpness'
                        'mute'
                        'source'
                    )

                    for com in commands:
                        if command.startswith(com):
                            value = command.replace(com, '')
                            command = com

                            if command == 'source':
                                for source in self.remote.sources:
                                    if value == 'state':
                                        if source.is_active:
                                            print(
                                                source.name,
                                                ':',
                                                source.label
                                            )
                                            break
                                    elif value in (
                                        source.name,
                                        source.label
                                    ):
                                        source.activate()
                                        break

                            elif command == 'mute':
                                if value == 'state':
                                    print(
                                        'on' if self.remote.mute else 'off'
                                    )
                                else:
                                    self.remote.mute = (
                                        True if value == 'on' else False
                                    )

                            else:
                                if value == '-1':
                                    print(getattr(self.remote, command))
                                else:
                                    value = int(value)
                                    setattr(self.remote, command, value)

                            break
                    else:
                        for group in KEY_MAPPINGS:
                            for _, key in group[1]:
                                if command.upper() == key:
                                    self.remote.control(command)
                                    break

                                if command.upper() == key.split('_', 1)[-1]:
                                    self.remote.control(key)
                                    break
                            else:
                                continue

                            break
                        else:
                            print('command not found')
                except:
                    import traceback
                    traceback.print_exc()

        except KeyboardInterrupt:
            print('closing remote connection')
            self.remote.close()
            sys.exit()
