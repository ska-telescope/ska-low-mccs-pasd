# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements a component manager for a ska-tango-base device."""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Generic, TypeVar

import tango
from ska_control_model import ResultCode, TaskStatus
from ska_tango_testing.context import DeviceProxy

AttributeTypeT = TypeVar("AttributeTypeT")


class MccsAttributeProxy(Generic[AttributeTypeT]):
    """A local proxy to a single remote device attribute."""

    def __init__(
        self: MccsAttributeProxy,
        device_name: str,
        attribute_name: str,
        callback: Callable[[AttributeTypeT | None, tango.AttrQuality], None] | None,
        device_proxy_factory: Callable[[str], tango.DeviceProxy] | None = None,
    ) -> None:
        """
        Initialise a new instance.

        :param device_name: name of the device
        :param attribute_name: name of the attribute
        :param logger: the logger to use
        :param device_proxy_factory: optional override for device proxy factory
        """
        self._attribute_name = attribute_name
        self._attribute_value: AttributeTypeT | None = None
        self._attribute_quality = tango.AttrQuality.ATTR_INVALID
        self._callback: Callable[
            [AttributeTypeT | None, tango.AttrQuality], None
        ] | None = callback

        _device_proxy_factory = device_proxy_factory or DeviceProxy
        self._device_proxy = _device_proxy_factory(device_name)
        self._subscription_id = self._device_proxy.subscribe_event(
            attribute_name,
            tango.EventType.CHANGE_EVENT,
            self._handle_attribute_changed,
        )

    def _handle_attribute_changed(self, *args, **kwargs):
        assert print(
            "IN _handle_attribute_changed(\n" f"\t{args}\n" f"\t{kwargs}\n" ")"
        )

    @property
    def value(self) -> tango.AttrQuality:
        return self._attribute_value

    @property
    def quality(self) -> tango.AttrQuality:
        return self._attribute_quality

    def __get__(self, obj: Any, obj_type: type | None = None) -> AttributeTypeT | None:
        return self._attribute_value

    def __set__(self, obj: Any, value: AttributeTypeT) -> None:
        setattr(self._device_proxy, self._attribute_name, self._attribute_value)


class MccsCommandProxy:  # pylint: disable=too-few-public-methods
    """
    A command proxy that understands the ska-low-mccs command variants.

    It hides the messy details of the device interface
    through which commands are monitored.

    The idea is that one can invoke a command on a device,
    and monitor its progress,
    simply by invoking a command on a proxy,
    and passing it a task_callback.
    The command proxy interacts with the device interface,
    hiding its details from the user,
    and calls the task_callback as appropriate.

    Note, however, that this is currently incomplete:
    Support for long-running commands has not been implemented.
    """

    def __init__(
        self: MccsCommandProxy,
        device_name: str,
        command_name: str,
        logger: logging.Logger,
        device_proxy_factory: Callable[[str], tango.DeviceProxy] | None = None,
    ) -> None:
        """
        Initialise a new instance.

        :param device_name: name of the device on which to invoke the command
        :param command_name: name of the command to invoke
        :param logger: the logger to use
        :param device_proxy_factory: optional override for device proxy factory
        """
        self._device_name = device_name
        self._command_name = command_name
        self._logger = logger
        self._device_proxy_factory = device_proxy_factory or DeviceProxy

    def __call__(  # noqa: C901
        self: MccsCommandProxy,
        arg: Any = None,
        *,
        task_callback: Callable | None = None,
    ) -> tuple[TaskStatus, str]:
        """
        Manage execution of the command.

        If the command returns a DevVarLongStringArray,
        it is assumed to return a standard response of the form
        `[[ResultCode], ["human-readable message"]]`:

        * If that `ResultCode` is `ResultCode.QUEUED` or `ResultCode.STARTED`,
          the command is taken to be a long-running command,
          and its progress and completion is monitored via the
          `longRunningCommandProgress`, `longRunningCommandStatus` and
          `longRunningCommandResult` attributes.
        * Otherwise, the command is either a short-running command,
          or a long-running command that finished immediately
          (e.g. immediate failure).

        If the command returns anything other than a DevVarLongStringArray,
        it is assumed to be a fast command that has run to completion
        and yielded an immediate result.

        :param arg: argument to the name, or None if no argument
        :param task_callback: callback to update with task status

        :return: the task status and a human-readable status message
        """
        # This lock prevents an unlikely but possible race condition
        # in which the response callback has already been called
        # before this method returns QUEUED.
        lock = threading.RLock()

        def _try_task_callback(**kwargs: Any) -> None:
            if task_callback is not None:
                try:
                    with lock:
                        task_callback(**kwargs)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    self._logger.error(
                        f"Could not invoke task callback: exception {repr(e)}."
                    )

        def _execute_command() -> None:
            try:
                # throwaway proxy so that we can isolate our event subscriptions
                proxy = self._device_proxy_factory(self._device_name)
                try:
                    args = [] if arg is None else [arg]
                    response = proxy.command_inout(self._command_name, *args)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    self._logger.error(
                        f"Error invoking command on device: exception {repr(e)}."
                    )
                    _try_task_callback(status=TaskStatus.FAILED)
                    return

                self._logger.debug(f"Command response was {response}")
                try:
                    [result_code_array, [message]] = response
                    result_code = ResultCode(result_code_array[0])
                except:  # pylint: disable=bare-except  # noqa: E722
                    self._logger.debug(
                        "Response is not a (result_code, message) tuple."
                        "Command is interpreted as completed."
                    )
                    _try_task_callback(status=TaskStatus.COMPLETED, result=response)
                    return

                if result_code in [ResultCode.QUEUED, ResultCode.STARTED]:
                    self._logger.debug(
                        f"Command is in state '{result_code.name}': "
                        "i.e long-running and incomplete."
                    )
                    # TODO: Big gap here -- handle long-running commands
                    #
                    #
                    #
                    #
                    #
                    #
                    self._logger.error(
                        "MccsCommandProxy cannot yet handle long-running commands."
                    )
                    _try_task_callback(status=TaskStatus.FAILED)
                    return

                self._logger.debug(
                    f"Command is in state '{result_code.name}': i.e already completed."
                )
                _try_task_callback(
                    status=TaskStatus.COMPLETED, result=(result_code, message)
                )
            # Catch and report everything because otherwise the thread crashes silently
            except Exception as e:  # pylint: disable=broad-exception-caught
                print(f"Exception on command execution thread: {repr(e)}")

        with lock:
            thread = threading.Thread(target=_execute_command)
            thread.start()

            _try_task_callback(status=TaskStatus.QUEUED)

            return (
                TaskStatus.QUEUED,
                "Task command has been invoked on the remote device.",
            )
