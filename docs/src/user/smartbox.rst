================
SMART Box device
================

The SMART Box Tango devices reflect the state of the individual FNSC (Field Node SMART Box
Controller) devices, including FEM port power status. The following attributes are exposed;
note all attributes are read-only with the exception of the alarm and warning thresholds,
and FEM current trip thresholds. All temperatures are in degrees Celsius.

+--------------------------------------+-------------+--------------------------------------------------------------------------+
| Tango attribute name                 | Register    | Register description                                                     |
|                                      |             |                                                                          |
|                                      | address(es) |                                                                          |
+======================================+=============+==========================================================================+
| ModbusRegisterMapRevisionNumber      | 1           | Modbus FNPC register map revision number, fixed at firmware compile time |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PcbRevisionNumber                    | 2           | FNCB revision number, fixed at firmware compile time                     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| CpuId                                | 3-4         | Microcontroller device ID                                                |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| ChipId                               | 5-12        | Microcontroller unique device ID                                         |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| FirmwareVersion                      | 13          | Firmware revision number, fixed at compile time                          |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| Uptime                               | 14-15       | Time, in seconds, since FNPC boot                                        |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| SysAddress                           | 16          | Modbus address                                                           |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| InputVoltage                         | 17          | Incoming 48Vdc voltage                                                   |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PowerSupplyOutputVoltage             | 18          | PSU output voltage                                                       |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PowerSupplyTemperature               | 19          | PSU temperature                                                          |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PcbTemperature                       | 20          | PCB temperature                                                          |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| FemAmbientTemperature                | 21          | Thermistor mounted on sensor board in the FEM package                    |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PasdStatus                           | 22          | SMART Box system status                                                  |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| LedPattern                           | 23          | Status of the service and status LEDs                                    |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| FemCaseTemperature1                  | 24          | FEM 6 temperature (thermistor mounted on top of FEM case)                |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| FemCaseTemperature2                  | 25          | FEM 12 temperature (thermistor mounted on top of FEM case)               |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| FemHeatsinkTemperature1              | 26          | Thermistor mounted on heatsink between FEMs 9 and 10                     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| FemHeatsinkTemperature2              | 27          | Thermistor mounted on heatsink between FEMs 3 and 4                      |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PortForcings                         | 36-47       | Port forcing status for each port ("ON", "OFF", or "NONE")               |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PortBreakersTripped                  | 36-47       | Firmware circuit breaker status for each port (True if trip has occurred)|
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PortsDesiredPowerOnline              | 36-47       | Desired state of each port when FNSC is ONLINE ("OFF, "ON" or "DEFAULT") |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PortsDesiredPowerOffline             | 36-47       | Desired state of each port when FNSC is OFFLINE ("OFF, "ON" or "DEFAULT")|
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PortsPowerSensed                     | 36-47       | Power sensed status for each port (True or False)                        |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PortsCurrentDraw                     | 48-59       | List of FEM current measurements (mA)                                    |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| InputVoltageThresholds               | 1001-1004   | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PowerSupplyOutputVoltageThresholds   | 1005-1008   | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PowerSupplyTemperatureThresholds     | 1009-1012   | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PcbTemperatureThresholds             | 1013-1016   | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| FemAmbientTemperatureThresholds      | 1017-1020   | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| FemCaseTemperature1Thresholds        | 1021-1024   | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| FemCaseTemperature2Thresholds        | 1025-1028   | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| FemHeatsinkTemperature1Thresholds    | 1029-1032   | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| FemHeatsinkTemperature2Thresholds    | 1033-1036   | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| FemCurrentTripThresholds             | 1069-1080   | 12 FEM current trip thresholds (mA)                                      |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| WarningFlags                         | 10130       | List of sensors in WARNING state                                         |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| AlarmFlags                           | 10132       | List of sensors in ALARM state                                           |
+--------------------------------------+-------------+--------------------------------------------------------------------------+

The SMART Box ``PasdStatus`` attribute should be interpreted as follows:

+---------------------------------+--------------------------------------------------+
| *PasdStatus* attribute value    | Meaning                                          |
+=================================+==================================================+
| OK                              | Initialised, system health OK                    |
+---------------------------------+--------------------------------------------------+
| WARNING                         | Initialised, and at least one sensor in WARNING  |
+---------------------------------+--------------------------------------------------+
| ALARM                           | Initialised, and at least one sensor in ALARM    |
+---------------------------------+--------------------------------------------------+
| RECOVERY                        | Initialised, and at least one sensor in RECOVERY |
+---------------------------------+--------------------------------------------------+
| UNINITIALISED                   | Not initialised, regardless of sensor states     |
+---------------------------------+--------------------------------------------------+
| POWERDOWN                       | Local tech initiated power-down sequence         |
+---------------------------------+--------------------------------------------------+

SMART Box commands
------------------
The SMART Box devices support the following commands:

+------------------------+-----------------------------+-----------------------------------------------------------------------+
| Command name           | Arguments                   | Description                                                           |
+========================+=============================+=======================================================================+
| PowerOnPort            | Port number                 | Request to power on the specified FEM port                            |
+------------------------+-----------------------------+-----------------------------------------------------------------------+
| PowerOffPort           | Port number                 | Request to power off the specified FEM port                           |
+------------------------+-----------------------------+-----------------------------------------------------------------------+
| SetPortPowers          | See: :ref:`set-port-powers` | Initialise the SMART Box and request the specified port power statuses|
+------------------------+-----------------------------+-----------------------------------------------------------------------+

Alarm recovery procedure
------------------------
When the SMART Box ``PasdStatus`` attribute indicates an ALARM, WARNING or RECOVERY state, the
``WarningFlags`` and ``AlarmFlags`` attributes can be interrogated to find out which
sensors have gone outside their threshold values. These registers need to be manually
cleared by issuing the :py:func:`~ska_low_mccs_pasd.pasd_bus.pasd_bus_device.MccsPasdBus.ResetSmartboxAlarms` and
:py:func:`~ska_low_mccs_pasd.pasd_bus.pasd_bus_device.MccsPasdBus.ResetSmartboxWarnings` commands after reading.

SMART Boxes automatically transition to the RECOVERY state when the relevant
sensor values return to within their alarm thresholds. To return a SMART Box to an operational
state after such an event, the :py:func:`~ska_low_mccs_pasd.pasd_bus.pasd_bus_device.MccsPasdBus.InitializeSmartbox` command must
be executed.

.. _smartbox-health-evaluation:

Smartbox health
---------------
The smartbox health is decided by comparing the values of the monitoring points against their configured thresholds. Each
monitoring point has four thresholds: [min_fault, min_warning, max_warning, max_fault]. If any value is less than the
min_fault or greater than the max_fault, it triggers a FAILED health status. If a value is between the min_fault and
min_warning, or between max_fault and max_warning, it triggers a DEGRADED health state.

We can change the thresholds at run time on the smartbox by setting the ``healthModelParams`` attribute.

For example:

.. code-block:: python

    desired_thresholds = {
        "pcb_temperature": [48.5, 48.3, 48.7, 48.6],
        "input_voltage": [10.2, 10.5, 9.8, 10.1],
    }

    smartbox.healthModelParams = json.dumps(desired_thresholds)
