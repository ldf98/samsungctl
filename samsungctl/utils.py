# -*- coding: utf-8 -*-

import logging
import inspect
import sys
import time
from functools import update_wrapper

PY3 = sys.version_info[0] > 2
logger = logging.getLogger('samsungctl')
#
#
# def LogIt(func):
#     """
#     Logs the function call, if debugging log level is set.
#     """
#     if PY3:
#         if func.__code__.co_flags & 0x20:
#             raise TypeError("Can't wrap generator function")
#     else:
#         if func.func_code.co_flags & 0x20:
#             raise TypeError("Can't wrap generator function")
#
#     def wrapper(*args, **kwargs):
#         func_name, arg_string = func_arg_string(func, args, kwargs)
#         logger.debug(func_name + arg_string)
#         return func(*args, **kwargs)
#
#     return update_wrapper(wrapper, func)
#
#
# def LogItWithReturn(func):
#     """
#     Logs the function call and return, if debugging log level is set.
#     """
#
#     if PY3:
#         if func.__code__.co_flags & 0x20:
#             raise TypeError("Can't wrap generator function")
#     else:
#         if func.func_code.co_flags & 0x20:
#             raise TypeError("Can't wrap generator function")
#
#     def wrapper(*args, **kwargs):
#         func_name, arg_string = func_arg_string(func, args, kwargs)
#         logger.debug(func_name + arg_string)
#         result = func(*args, **kwargs)
#         logger.debug(func_name + " => " + repr(result))
#         return result
#
#     return update_wrapper(wrapper, func)
#
#
# def func_arg_string(func, args, kwargs):
#     class_name = ""
#     if PY3:
#         arg_names = inspect.getfullargspec(func)[0]
#     else:
#         arg_names = inspect.getargspec(func)[0]
#     start = 0
#     if arg_names:
#         if arg_names[0] == "self":
#             class_name = args[0].__class__.__name__ + "."
#             start = 1
#
#     res = []
#     append = res.append
#
#     for key, value in list(zip(arg_names, args))[start:]:
#         append(str(key) + "=" + repr(value))
#
#     for key, value in kwargs.items():
#         append(str(key) + "=" + repr(value))
#
#     f_name = class_name + func.__name__
#     return f_name, "(" + ", ".join(res) + ")"
#

def LogIt(func):
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
        return func(*args, **kwargs)

    return update_wrapper(wrapper, func)


def LogItWithReturn(func):
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

        result = func(*args, **kwargs)
        lgr.debug('{0} => {1}'.format(func_name, repr(result)))

        return result

    return update_wrapper(wrapper, func)


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
                func_path.insert(0, item.frame.f_locals['self'].__class__.__name__)

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
                func_path.insert(0, item[0].f_locals['self'].__class__.__name__)

            func_path.insert(0, item[3])

    func_path += [func.__name__]

    for key, value in list(zip(arg_names, args))[start:]:
        append(str(key) + "=" + repr(value).replace('.<locals>.', '.'))

    for key, value in kwargs.items():
        append(str(key) + "=" + repr(value).replace('.<locals>.', '.'))

    f_name = class_name + '.'.join(func_path)

    return f_name, "(" + ", ".join(res) + ")"
