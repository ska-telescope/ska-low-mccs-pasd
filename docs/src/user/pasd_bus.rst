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