# -*- coding: utf-8 -*-

import warnings
import logging
import inspect
import traceback
import sys
import time
from functools import update_wrapper

PY3 = sys.version_info[0] > 2
logger = logging.getLogger('samsungctl')


# noinspection PyPep8Naming
def LogIt(func):
    if PY3:
        if func.__code__.co_flags & 0x20:
            return func
    else:
        if func.func_code.co_flags & 0x20:
            return func

    lgr = logging.getLogger(func.__module__)

    def wrapper(*args, **kwargs):
        func_name, arg_string = _func_arg_string(func, args, kwargs)
        lgr.debug(func_name + arg_string)
        return func(*args, **kwargs)

    return update_wrapper(wrapper, func)


# noinspection PyPep8Naming
def LogItWithReturn(func):
    if PY3:
        if func.__code__.co_flags & 0x20:
            return func
    else:
        if func.func_code.co_flags & 0x20:
            return func

    lgr = logging.getLogger(func.__module__)

    def wrapper(*args, **kwargs):
        func_name, arg_string = _func_arg_string(func, args, kwargs)
        lgr.debug(func_name + arg_string)

        result = func(*args, **kwargs)
        lgr.debug('{0} => {1}'.format(func_name, repr(result)))

        return result

    return update_wrapper(wrapper, func)


# noinspection PyPep8Naming
def LogItWithTimer(func):

    if PY3:
        if func.__code__.co_flags & 0x20:
            return func
    else:
        if func.func_code.co_flags & 0x20:
            return func

    def wrapper(*args, **kwargs):
        lgr = logging.getLogger(func.__module__)

        func_name, arg_string = _func_arg_string(func, args, kwargs)
        lgr.debug(func_name + arg_string)

        start = time.time()
        result = func(*args, **kwargs)
        stop = time.time()

        resolutions = (
            (1, 'sec'),
            (1000, 'ms'),
            (1000000, u'us'),
            (1000000000, 'ns'),
        )

        for divider, suffix in resolutions:
            duration = int(round((stop - start) / divider))
            if duration > 0:
                break
        else:
            duration = 'unknown'
            suffix = ''

        lgr.debug(
            'duration: {0} {1} - {2} => {3}'.format(
                duration,
                suffix,
                func_name,
                repr(result)
            )
        )

    return update_wrapper(wrapper, func)


def _func_arg_string(func, args, kwargs):
    class_name = ""

    if PY3:
        # noinspection PyUnresolvedReferences
        arg_names = inspect.getfullargspec(func)[0]
    else:
        arg_names = inspect.getargspec(func)[0]

    start = 0
    if arg_names:
        if arg_names[0] == "self":
            class_name = args[0].__class__.__name__ + "."
            start = 1

    res = []
    append = res.append

    stack = inspect.stack()

    func_path = []

    # iterate over the stack to check for functions being
    # nested inside of functions or methods.

    for item in stack:
        # this is where we want to stop so we do not include any of the
        # internal path information.

        if PY3:
            if item.function == '_func_arg_string':
                break
            if item.function == 'wrapper':
                continue
            # this is where the check gets done to see if a function
            # is nested inside of a method. and if it is this is
            # where we obtain the class name
            if 'self' in item.frame.f_locals:
                func_path.insert(
                    0,
                    item.frame.f_locals['self'].__class__.__name__
                )

            func_path.insert(0, item.function)
        else:
            if item[3] == '_func_arg_string':
                break
            if item[3] == 'wrapper':
                continue
            # this is where the check gets done to see if a function
            # is nested inside of a method. and if it is this is
            # where we obtain the class name
            if 'self' in item[0].f_locals:
                func_path.insert(
                    0,
                    item[0].f_locals['self'].__class__.__name__
                )

            func_path.insert(0, item[3])

    func_path += [func.__name__]

    for key, value in list(zip(arg_names, args))[start:]:
        append(str(key) + "=" + repr(value).replace('.<locals>.', '.'))

    for key, value in kwargs.items():
        append(str(key) + "=" + repr(value).replace('.<locals>.', '.'))

    f_name = class_name + '.'.join(func_path)

    return f_name, "(" + ", ".join(res) + ")"


# noinspection PyPep8Naming
def Deprecated(obj, msg=None):

    """This is a decorator which can be used to mark functions
    as deprecated. It will result in a warning being emitted
    when the function is used."""

    if isinstance(obj, property):
        class FSetWrapper(object):

            def __init__(self, fset_object):
                self._fset_object = fset_object

            def __call__(self, *args, **kwargs):

                # turn off filter
                warnings.simplefilter('always', DeprecationWarning)
                f_name = _func_arg_string(self._fset_object, args, kwargs)[0]

                if msg is None:
                    message = "deprecated set property [{0}.{1}].".format(
                        self._fset_object.__module__,
                        f_name
                    )
                else:
                    message = "deprecated set property [{0}.{1}].\n{2}".format(
                        self._fset_object.__module__,
                        f_name,
                        msg
                    )

                warnings.warn(
                    message,
                    category=DeprecationWarning,
                    stacklevel=2
                )
                # reset filter

                warnings.simplefilter('default', DeprecationWarning)
                return self._fset_object(*args, **kwargs)


        class FGetWrapper(object):

            def __init__(self, fget_object):
                self._fget_object = fget_object

            def __call__(self, *args, **kwargs):

                # turn off filter
                warnings.simplefilter('always', DeprecationWarning)
                f_name = _func_arg_string(self._fget_object, args, kwargs)[0]

                if msg is None:
                    message = "deprecated get property [{0}.{1}].".format(
                        self._fget_object.__module__,
                        f_name
                    )
                else:
                    message = "deprecated get property [{0}.{1}].\n{2}".format(
                        self._fget_object.__module__,
                        f_name,
                        msg
                    )

                warnings.warn(
                    message,
                    category=DeprecationWarning,
                    stacklevel=2
                )
                # reset filter

                warnings.simplefilter('default', DeprecationWarning)
                return self._fget_object(*args, **kwargs)

        # noinspection PyBroadException,PyPep8
        try:
            if obj.fset is not None:
                fset = FSetWrapper(obj.fset)
                fget = obj.fget
                return property(fget, fset)

            elif obj.fget is not None:
                fget = FGetWrapper(obj.fget)
                fset = obj.fset
                return property(fget, fset)
        except:
            traceback.print_exc()
            return obj

    elif inspect.isfunction(obj):
        def wrapper(*args, **kwargs):
            # turn off filter
            warnings.simplefilter('always', DeprecationWarning)
            f_name = _func_arg_string(obj, args, kwargs)[0]

            if PY3:
                # noinspection PyUnresolvedReferences
                arg_names = inspect.getfullargspec(obj)[0]
            else:
                arg_names = inspect.getargspec(obj)[0]

            if arg_names and arg_names[0] == "self":
                call_type = 'method'
            else:
                call_type = 'function'

            if msg is None:
                message = "deprecated {0} [{1}.{2}].".format(
                    call_type,
                    obj.__module__,
                    f_name
                )
            else:
                message = "deprecated {0} [{1}.{2}].\n{3}".format(
                    call_type,
                    obj.__module__,
                    f_name,
                    msg
                )

            warnings.warn(
                message,
                category=DeprecationWarning,
                stacklevel=2
            )
            # reset filter

            warnings.simplefilter('default', DeprecationWarning)
            return obj(*args, **kwargs)

        return update_wrapper(wrapper, obj)

    elif inspect.isclass(obj):
        def wrapper(*args, **kwargs):
            # turn off filter
            warnings.simplefilter('always', DeprecationWarning)

            if msg is None:
                message = "deprecated class [{0}.{1}].".format(
                    obj.__module__,
                    obj.__name__
                )
            else:
                message = "deprecated class [{0}.{1}].\n{2}".format(
                    obj.__module__,
                    obj.__name__,
                    msg
                )

            warnings.warn(
                message,
                category=DeprecationWarning,
                stacklevel=2
            )
            # reset filter

            warnings.simplefilter('default', DeprecationWarning)
            return obj(*args, **kwargs)

        return update_wrapper(wrapper, obj)
    else:
        # noinspection PyProtectedMember
        frame = sys._getframe().f_back
        source = inspect.findsource(frame)[0]

        line_no = frame.f_lineno - 1

        if msg:
            while (
                '=deprecated' not in source[line_no] and
                '= deprecated' not in source[line_no] and
                '=utils.deprecated' not in source[line_no] and
                '= utils.deprecated' not in source[line_no]
            ):
                line_no -= 1

        symbol = source[line_no].split('=')[0].strip()

        def wrapper(*_, **__):
            # turn off filter
            warnings.simplefilter('always', DeprecationWarning)
            if msg is None:
                message = "deprecated symbol [{0}.{1}.{2}].".format(
                    frame.f_locals['__module__'],
                    frame.f_locals['__qualname__'],
                    symbol
                )
            else:
                message = "deprecated symbol [{0}.{1}.{2}].\n{3}".format(
                    frame.f_locals['__module__'],
                    frame.f_locals['__qualname__'],
                    symbol,
                    msg
                )

            warnings.warn(
                message,
                category=DeprecationWarning,
                stacklevel=2
            )
            # reset filter

            warnings.simplefilter('default', DeprecationWarning)
            return obj

        return property(wrapper)


# This is rather odd to see.
# I am using sys.excepthook to alter the displayed traceback data.
# The reason why I am doing this is to remove any lines that are generated
# from any of the code in this file. It adds a lot of complexity to the
# output traceback when any lines generated from this file do not really need
# to be displayed.

def trace_back_hook(tb_type, tb_value, tb):
    tb = "".join(
        traceback.format_exception(
            tb_type,
            tb_value,
            tb,
            limit=None
        )
    )
    if tb_type == DeprecationWarning:
        sys.stderr.write(tb)
    else:
        new_tb = []
        skip = False
        for line in tb.split('\n'):
            if line.strip().startswith('File'):
                if __file__ in line:
                    skip = True
                else:
                    skip = False
            if skip:
                continue

            new_tb += [line]

        sys.stderr.write('\n'.join(new_tb))


sys.excepthook = trace_back_hook
