# Copyright 2016-2017 IBM Corp. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
This package supports logging using the standard Python :mod:`py:logging`
module. The logging support provides two :class:`~py:logging.Logger` objects:

* 'zhmcclient.api' for user-issued calls to zhmcclient API functions, at the
  debug level. Internal calls to API functions are not logged.

* 'zhmcclient.hmc' for interactions between zhmcclient and the HMC, at the
  debug level.

In addition, there are loggers for each module with the module name, for
situations like errors or warnings.

For HMC operations and API calls that contain the HMC password, the password
is hidden in the log message by replacing it with a few '*' characters.

All these loggers have a null-handler (see :class:`~py:logging.NullHandler`)
and have no log formatter (see :class:`~py:logging.Formatter`).

As a result, the loggers are silent by default. If you want to turn on logging,
add a log handler (see :meth:`~py:logging.Logger.addHandler`, and
:mod:`py:logging.handlers` for the handlers included with Python) and set the
log level (see :meth:`~py:logging.Logger.setLevel`, and :ref:`py:levels` for
the defined levels).

If you want to change the default log message format, use
:meth:`~py:logging.Handler.setFormatter`. Its ``form`` parameter is a format
string with %-style placeholders for the log record attributes (see Python
section :ref:`py:logrecord-attributes`).

Examples:

* To output the log records for all HMC operations to ``stdout`` in a
  particular format, do this:

  ::

      import logging

      handler = logging.StreamHandler()
      format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
      handler.setFormatter(logging.Formatter(format_string))
      logger = getLogger('zhmcclient.hmc')
      logger.addHandler(handler)
      logger.setLevel(logging.DEBUG)

* This example uses the :func:`~py:logging.basicConfig` convenience function
  that sets the same format and level as in the previous example, but for the
  root logger. Therefore, it will output all log records, not just from this
  package:

  ::

      import logging

      format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
      logging.basicConfig(format=format_string, level=logging.DEBUG)
"""

import logging
import inspect
from decorator import decorate

from ._constants import API_LOGGER_NAME


def get_logger(name):
    """
    Return a :class:`~py:logging.Logger` object with the specified name.

    A :class:`~py:logging.NullHandler` handler is added to the logger if it
    does not have any handlers yet. This prevents the propagation of log
    requests up the Python logger hierarchy, and therefore causes this package
    to be silent by default.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger


def logged_api_call(func):
    """
    Function decorator that causes the decorated API function or method to log
    calls to itself to a logger.

    The logger's name is the dotted module name of the module defining the
    decorated function (e.g. 'zhmcclient._cpc').

    Parameters:

      func (function object): The original function being decorated.

    Returns:

      function object: The function wrappering the original function being
        decorated.

    Raises:

      TypeError: The @logged_api_call decorator must be used on a function or
        method (and not on top of the @property decorator).
    """

    # Note that in this decorator function, we are in a module loading context,
    # where the decorated functions are being defined. When this decorator
    # function is called, its call stack represents the definition of the
    # decorated functions. Not all global definitions in the module have been
    # defined yet, and methods of classes that are decorated with this
    # decorator are still functions at this point (and not yet methods).

    module = inspect.getmodule(func)
    if not inspect.isfunction(func) or not hasattr(module, '__name__'):
        raise TypeError("The @logged_api_call decorator must be used on a "
                        "function or method (and not on top of the @property "
                        "decorator)")

    try:
        # We avoid the use of inspect.getouterframes() because it is slow,
        # and use the pointers up the stack frame, instead.

        this_frame = inspect.currentframe()  # this decorator function here
        apifunc_frame = this_frame.f_back  # the decorated API function

        apifunc_owner = inspect.getframeinfo(apifunc_frame)[2]

    finally:
        # Recommended way to deal with frame objects to avoid ref cycles
        del this_frame
        del apifunc_frame

    # TODO: For inner functions, show all outer levels instead of just one.

    if apifunc_owner == '<module>':
        # The decorated API function is defined globally (at module level)
        apifunc_str = '{func}()'.format(func=func.__name__)
    else:
        # The decorated API function is defined in a class or in a function
        apifunc_str = '{owner}.{func}()'.format(owner=apifunc_owner,
                                                func=func.__name__)

    logger = get_logger(API_LOGGER_NAME)

    def log_api_call(func, *args, **kwargs):
        """
        Log entry to and exit from the decorated function, at the debug level.

        Note that this wrapper function is called every time the decorated
        function/method is called, but that the log message only needs to be
        constructed when logging for this logger and for this log level is
        turned on. Therefore, we do as much as possible in the decorator
        function, plus we use %-formatting and lazy interpolation provided by
        the log functions, in order to save resources in this function here.

        Parameters:

          func (function object): The decorated function.

          *args: Any positional arguments for the decorated function.

          **kwargs: Any keyword arguments for the decorated function.
        """

        # Note that in this function, we are in the context where the
        # decorated function is actually called.

        try:
            # We avoid the use of inspect.getouterframes() because it is slow,
            # and use the pointers up the stack frame, instead.

            this_frame = inspect.currentframe()  # this function here
            apifunc_frame = this_frame.f_back  # the decorated API function
            apicaller_frame = apifunc_frame.f_back  # caller of API function

            apicaller_module = inspect.getmodule(apicaller_frame)
            apicaller_module_name = apicaller_module.__name__
        finally:
            # Recommended way to deal with frame objects to avoid ref cycles
            del this_frame
            del apifunc_frame
            del apicaller_frame
            del apicaller_module

        # Log only if the caller is not from our package
        log_it = (apicaller_module_name.split('.')[0] != 'zhmcclient')

        if log_it:
            logger.debug("==> %s, args: %.500r, kwargs: %.500r",
                         apifunc_str, args, kwargs)
        result = func(*args, **kwargs)
        if log_it:
            logger.debug("<== %s, result: %.1000r", apifunc_str, result)
        return result

    return decorate(func, log_api_call)
