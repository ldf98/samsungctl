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

        try:
            while True:
                command = input('help to get help\nPlease enter command:')

                if command == 'help':
                    for group in KEY_MAPPINGS:
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

                    print("brightness [value]")
                    print("    Sets the TV brightness to the entered value,\n")
                    print("    a value of -1 will display the brightness level")

                    print("contrast [value]")
                    print("    Sets the TV contrast to the entered value,\n")
                    print("    a value of -1 will display the contrast level")

                    print("sharpness [value]")
                    print("    Sets the TV sharpness to the entered value,\n")
                    print("    a value of -1 will display the sharpness level")

                    print("mute [off, on, state]")
                    print("    Sets the mute on or off (not a toggle),\n")
                    print("    state displays if the mute if on or off")

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
                    continue

                try:
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
                                    elif value in (source.name, source.label):
                                        source.activate()
                                        break

                            elif command == 'mute':
                                if value == 'state':
                                    print('on' if self.remote.mute else 'off')
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
            self.remote.close()
            sys.exit()
