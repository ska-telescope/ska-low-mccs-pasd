===============
PaSD bus device
===============

The PaSD bus Tango device is responsible for funnelling all communications
between MCCS and the PaSD hardware. It ensures that only one request is sent on
the bus at any one time, and handles the prioritization of requests. It also
supports the following commands:

+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| Command name              | Arguments                           | Description                                                                                     |
+===========================+=====================================+=================================================================================================+
| InitializeFndh            | None                                | Request to transition to operational state. This is needed after power-up and alarm conditions. |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| InitializeSmartbox        | SMART Box device ID                 | Request to transition to operational state. This is needed after power-up and alarm conditions. |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| ResetFnccStatus           | None                                | Reset an FNCC communications error                                                              |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| SetFndhPortPowers         | See: :ref:`set-port-powers`         | Request to set multiple FNDH port powers in a single command                                    |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| SetFndhLedPattern         | See: `Setting LED patterns`_        | Control the FNDH service LED                                                                    |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| SetFndhLowPassFilters     | See: `Setting filter constants`_    | Set the low pass filters for the FNDH                                                           |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| ResetFndhAlarms           | None                                | Clear the FNDH's alarm flags register                                                           |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| ResetFndhWarnings         | None                                | Clear the FNDH's warning flags register                                                         |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| SetSmartboxPortPowers     | See: :ref:`set-port-powers`         | Request to set multiple SMART Box port powers in a single command                               |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| SetSmartboxLedPattern     | See: `Setting LED patterns`_        | Control the SMART Box's service LED                                                             |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| SetSmartboxLowPassFilters | See: `Setting filter constants`_    | Set the low pass filters for a SMART Box                                                        |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| ResetSmartboxPortBreaker  | See: `Resetting breakers`_          | Reset a SMART Box's port breaker                                                                |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| ResetSmartboxAlarms       | SMART Box device ID                 | Clear the SMART Box's alarm flags register                                                      |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| ResetSmartboxWarnings     | SMART Box device ID                 | Clear the SMART Box's warning flags register                                                    |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+

Initialization
--------------
When the :py:func:`~ska_low_mccs_pasd.pasd_bus.pasd_bus_device.MccsPasdBus.InitializeSmartbox` or
:py:func:`~ska_low_mccs_pasd.pasd_bus.pasd_bus_device.MccsPasdBus.InitializeFndh` command is called, the PaSD bus device will attempt to
initialize the specified SMART Box / FNDH. This involves:

1. Setting the FEM current trip thresholds and input voltage thresholds to the values specified in the device properties (SMART Boxes only)
2. Writing to the device's SYS_STATUS register to request it to enter normal operation
3. Setting the low-pass filter constant to the value specified in the device properties
4. Requesting the device to update all its static attributes e.g. firmware version, CPU ID etc.


Setting filter constants
------------------------
The :py:func:`~ska_low_mccs_pasd.pasd_bus.pasd_bus_device.MccsPasdBus.SetFndhLowPassFilters` command accepts a JSON object with the following keys:

- *cutoff* - Cut-off frequency to use for the low-pass filtering (between 0.1 and 1000.0)
- *extra_sensors* (optional) - Write the filter constant to the extra sensors' registers after the LED status register (default: False)

The target cut-off frequency is used to calculate a filter decay constant which is written to the
FNDH telemetry registers to enable low-pass filtering. If *extra_sensors* is set to True, the
constant is also written to the extra sensors' registers. 

The :py:func:`~ska_low_mccs_pasd.pasd_bus.pasd_bus_device.MccsPasdBus.SetSmartboxLowPassFilters` command works as above to set the filtering on a given SMART Box with
the additional required key:

- *smartbox_number* - Device ID of the SMART Box being addressed

**IMPORTANT NOTE**: The specified cut-off frequency is persisted to the Tango database (overwriting the value in
the deployment configuration) and the calculated constant is automatically written to *ALL* sensor registers
of the FNDH and SMART Boxes after MccsPasdBus is initialised and set ONLINE, and after any of them are
powered on (regardless of which command was used).

Resetting breakers
------------------
The :py:func:`~ska_low_mccs_pasd.pasd_bus.pasd_bus_device.MccsPasdBus.ResetSmartboxPortBreaker` command accepts a JSON object with the following keys:

- *smartbox_number* - The device ID of the SMART Box being addressed
- *port_number* - Number of the port whose breaker is to be reset

.. _set-port-powers:

Setting port powers
-------------------
The MccsPasdBus :py:func:`~ska_low_mccs_pasd.pasd_bus.pasd_bus_device.MccsPasdBus.SetFndhPortPowers`, 
MccsFNDH :py:func:`~ska_low_mccs_pasd.fndh.fndh_device.MccsFNDH.SetPortPowers` and
MccsSmartBox :py:func:`~ska_low_mccs_pasd.smart_box.smart_box_device.MccsSmartBox.SetPortPowers` commands accept
a JSON object with the following keys:

- *port_powers* - An array of desired power states (True for 'On', False for 'Off', None for no change)
- *stay_on_when_offline* - Whether to stay on when the FNPC is offline

Each port is powered one at a time in sequence, such that the overall power curve is ramped. 
The time between each port being powered is dictated by the PortPowerDelay device property on MccsPasdBus.

The MccsPasdBus :py:func:`~ska_low_mccs_pasd.pasd_bus.pasd_bus_device.MccsPasdBus.SetSmartboxPortPowers` command accepts a JSON object with the following keys:

- *smartbox_number* - The device ID of the SMART Box being addressed
- *port_powers* - An array of desired power states (True for 'On', False for 'Off', None for no change)
- *stay_on_when_offline* - Whether to stay on when the FNSC is offline

All requested changes of state are issued in a single Modbus command.

Setting LED patterns
--------------------
The :py:func:`~ska_low_mccs_pasd.pasd_bus.pasd_bus_device.MccsPasdBus.SetFndhLedPattern` command controls the FNDH service LED and accepts a JSON object
with the following keys:

- *pattern* - One of the following strings:

    - "OFF"
    - "ON"
    - "VFAST"
    - "FAST"
    - "SLOW"
    - "VSLOW"

The :py:func:`~ska_low_mccs_pasd.pasd_bus.pasd_bus_device.MccsPasdBus.SetSmartboxLedPattern` controls the SMART Box service LEDs and accepts a JSON object
with the following keys:

- *smartbox_number* - The device ID of the SMART Box being addressed.
- *pattern* - One of the following strings:

    - "OFF"
    - "ON"
    - "VFAST"
    - "FAST"
    - "SLOW"
    - "VSLOW"

.. _pasdbus-health-evaluation:

PaSD bus health evaluation
--------------------------

The health of the PaSD bus device is determined by three attributes:

1. ``fnccFailedPollsInWindow``: number of failed FNCC polls in the last ``FailedPollWindow`` seconds
2. ``fndhFailedPollsInWindow``: number of failed FNDH polls in the last ``FailedPollWindow`` seconds
3. ``smartboxFailedPollsInWindow``: number of failed polls for each smartbox in the last ``FailedPollWindow`` seconds, indexed by smartbox_id-1

``FailedPollWindow`` is a configurable device property which defines the size of the sliding window.

Cumulative counts since the devices were restarted are also available in the following attributes:

* ``fnccFailedPollCount``
* ``fndhFailedPollCount``
* ``smartboxFailedPollCount``


**Alarm Evaluation**

Whenever one of these attributes exceeds its Tango max_warning threshold, it will be put into ``tango.AttrQuality.WARNING`` state
and the device will reflect this as ``HealthState.DEGRADED``.

Whenever one of these attributes exceeds its Tango max_alarm threshold, it will be put into ``tango.AttrQuality.ALARM`` state
and the device will reflect this as ``HealthState.FAILED``.

We can change the alarm thresholds at run time on the PaSD bus device by using the Tango API:

For example:

.. code-block:: python

    attribute_config = pasdbus.get_attribute_config("smartboxFailedPollsInWindow")
    alarm_config = attribute_config.alarms
    alarm_config.max_warning = "10"
    alarm_config.max_alarm = "20"
    attribute_config.alarms = alarm_config
    pasdbus.set_attribute_config(attribute_config)

We can also change the thresholds at deploy time on the pasdbus through the helm charts:

.. code-block:: yaml

    ska-tango-devices:
      deviceDefaults:
        MccsPasdBus:
          SmartboxFailedPollsInWindow->max_alarm: 20
          SmartboxFailedPollsInWindow->max_warning: 10
          FNDHFailedPollsInWindow->max_alarm: 10
          FNDHFailedPollsInWindow->max_warning: 5
          FNCCFailedPollsInWindow->max_alarm: 10
          FNCCFailedPollsInWindow->max_warning: 5

      devices:
        MccsPasdBus:
          low-mccs/pasdbus/s8-1:
            SmartboxFailedPollsInWindow->max_alarm: 30
            SmartboxFailedPollsInWindow->max_warning: 15
            FNDHFailedPollsInWindow->max_alarm: 10
            FNDHFailedPollsInWindow->max_warning: 5
            FNCCFailedPollsInWindow->max_alarm: 10
            FNCCFailedPollsInWindow->max_warning: 5