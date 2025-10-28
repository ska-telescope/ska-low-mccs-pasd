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
The smartbox health is determined by three factors:

1. The value of monitoring points in relation to their defined thresholds.
2. The status as reported in the Smartbox's SYS_STATUS register.
3. The status of the FEM port breakers.

**Threshold Evaluation**
Each monitoring point has four thresholds: [min_alarm, min_warning, max_warning, max_alarm]. These set on the attributes and the attributes
respond by moving through ``tango.AttrQuality.WARNING`` and ``tango.AttrQuality.ALARM`` respectively dependent on monitoring point value. The
``healthState`` then reflects this as ``HealthState.DEGRADED`` -> ``tango.AttrQuality.WARNING`` and ``HealthState.FAILED`` -> ``tango.AttrQuality.ALARM``

We can change the thresholds at run time on the smartbox by using the Tango API:

For example:

.. code-block:: python

    attribute_config = smartbox.get_attribute_config("InputVoltage")
    alarm_config = attribute_config.alarms
    alarm_config.max_warning = "49.5"
    alarm_config.max_alarm = "48.5"
    alarm_config.min_warning = "45.5"
    alarm_config.min_alarm = "41"
    attribute_config.alarms = alarm_config
    smartbox.set_attribute_config(attribute_config)

We can also change the thresholds at deploy time on the smartbox through the helm charts:

.. code-block:: yaml

    ska-tango-devices:
      deviceDefaults:
        MccsSmartbox:
          InputVoltage->max_alarm: 49.5
          InputVoltage->max_warning: 48.5
          InputVoltage->min_warning: 45.5
          InputVoltage->min_alarm: 41    

      devices:
        MccsSmartbox:
          low-mccs/smartbox/s8-1-sb11:
            InputVoltage->max_alarm: 51.2

**Status Register Evaluation**

The following translation of the Smartbox's SYS_STATUS register values to health states is applied:

- 'ALARM' or 'RECOVERY' indicates a health state of 'FAILED'.
- 'WARNING' indicates a health state of 'DEGRADED'.
- 'UNINITIALISED' or 'OK' indicates a health state of 'OK'.
- 'POWERDOWN' indicates a health state of 'UNKNOWN' (this state should not be used).

**Port Breaker Status**

The number of port breakers tripped is reflected through the ``numberOfPortBreakersTripped`` attribute,
this attribute can have thresholds configured as the other attributes above, by default it only has 
max alarm configured as such we go to ``HealthState.FAILED`` at a single port breaker tripped.
