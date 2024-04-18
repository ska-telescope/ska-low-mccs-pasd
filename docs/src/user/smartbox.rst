================
SMART Box device
================

The SMART Box Tango devices reflect the state of the individual FNSC (Field Node SMART Box
Controller) devices, including FEM port power status. The following attributes are exposed;
note all attributes are read-only with the exception of the alarm and warning thresholds,
and all temperatures are in degrees Celsius:

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
| FemCaseTemperatures                  | 24-25       | Thermistors mounted on top and bottom of FEM case                        |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| FemHeatsinkTemperatures              | 26-27       | Thermistors mounted on heatsink                                          |
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
| Fem1CurrentTripThreshold             | 1069        | FEM1 current trip threshold (mA)                                         |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| Fem2CurrentTripThreshold             | 1070        | FEM2 current trip threshold (mA)                                         |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| Fem3CurrentTripThreshold             | 1071        | FEM3 current trip threshold (mA)                                         |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| Fem4CurrentTripThreshold             | 1072        | FEM4 current trip threshold (mA)                                         |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| Fem5CurrentTripThreshold             | 1073        | FEM5 current trip threshold (mA)                                         |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| Fem6CurrentTripThreshold             | 1074        | FEM6 current trip threshold (mA)                                         |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| Fem7CurrentTripThreshold             | 1075        | FEM7 current trip threshold (mA)                                         |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| Fem8CurrentTripThreshold             | 1076        | FEM8 current trip threshold (mA)                                         |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| Fem9CurrentTripThreshold             | 1077        | FEM9 current trip threshold (mA)                                         |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| Fem10CurrentTripThreshold            | 1078        | FEM10 current trip threshold (mA)                                        |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| Fem11CurrentTripThreshold            | 1079        | FEM11 current trip threshold (mA)                                        |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| Fem12CurrentTripThreshold            | 1080        | FEM12 current trip threshold (mA)                                        |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| WarningFlags                         | 10130       | List of sensors outside their warning thresholds                         |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| AlarmFlags                           | 10132       | List of sensors outside their alarm thresholds                           |
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
