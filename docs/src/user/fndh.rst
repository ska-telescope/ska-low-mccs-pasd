===========
FNDH device
===========

The FNDH Tango device reflects the state of the Field Node Peripheral Controller (FNPC),
including the status of the Power and Data Over Coax (PDOC) ports which are used to power the SMART Boxes. 
The following attributes are exposed; note that all temperatures are in degrees Celsius and all
attributes are read-only with the exception of the alarm and warning thresholds which
are read/write.

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
| Psu48vVoltage1                       | 17          | 48Vdc COSEL SMPS 1 output voltage                                        |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| Psu48vVoltage2                       | 18          | 48Vdc COSEL SMPS 2 output voltage (not implemented in h/w)               |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| Psu48vCurrent                        | 19          | 48Vdc COSEL SMPS output current                                          |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| Psu48vTemperature1                   | 20          | Thermistor mounted on the top of the COSEL SMPS base plate               |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| Psu48vTemperature2                   | 21          | Thermistor mounted on the bottom of the COSEL SMPS base plate            |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PanelTemperature                     | 22          | *NOT IMPLEMENTED IN HARDWARE*                                            |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| FncbTemperature                      | 23          | Field Node Controller Board temperature                                  | 
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| FncbHumidity                         | 24          | Field Node Controller Board humidity (%)                                 |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PasdStatus                           | 25          | FNDH System status (see below)                                           |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| LedPattern                           | 26          | Status of the service and status LEDs                                    |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| CommsGatewayTemperature              | 27          | Thermistor mounted on the external surface of the Comms Gateway          |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PowerModuleTemperature               | 28          | Thermistor mounted on the external surface of the Power Module enclosure |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| OutsideTemperature                   | 29          | Thermistor mounted on the floor of the FNDH EP Enclosure                 |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| InternalAmbientTemperature           | 30          | Thermistor mounted on the roof of the FNDH EP Enclosure                  |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PortForcings                         | 36-64       | Port forcing status for each port ("ON", "OFF", or "NONE")               |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PortsDesiredPowerOnline              | 36-64       | Desired state of each port when FNPC is ONLINE ("OFF, "ON" or "DEFAULT") |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PortsDesiredPowerOffline             | 36-64       | Desired state of each port when FNPC is OFFLINE ("OFF, "ON" or "DEFAULT")|
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PortsPowerSensed                     | 36-64       | Power sensed status for each port (True or False)                        |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PortsPowerControl                    | 36-64       | Power control line ON/OFF status (True if port can be turned on)         |                                                              
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| Psu48vVoltage1Thresholds             | 1001-1004   | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| Psu48vVoltage2Thresholds             | 1005-1008   | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| Psu48vCurrentThresholds              | 1009-1012   | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| Psu48vTemperature1Thresholds         | 1013-1016   | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| Psu48vTemperature2Thresholds         | 1017-1020   | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PanelTemperatureThresholds           | 1021-1024   | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| FncbTemperatureThresholds            | 1025-1028   | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| FncbHumidityThresholds               | 1029-1032   | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| CommsGatewayTemperatureThresholds    | 1033-1036   | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| PowerModuleTemperatureThresholds     | 1037-1040   | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| OutsideTemperatureThresholds         | 1041-1044   | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| InternalAmbientTemperatureThresholds | 1045-1048   | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| WarningFlags                         | 10129       | List of sensors outside their warning thresholds                         |
+--------------------------------------+-------------+--------------------------------------------------------------------------+
| AlarmFlags                           | 10131       | List of sensors outside their alarm thresholds                           |
+--------------------------------------+-------------+--------------------------------------------------------------------------+

The FNDH ``PasdStatus`` attribute should be interpreted as follows:

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
| POWERUP                         | Local tech initiated powerup sequence            |
+---------------------------------+--------------------------------------------------+

FNDH commands
-------------
The FNDH device supports the following commands:

+------------------------+-----------------------------+-------------------------------------------------------------------+
| Command name           | Arguments                   | Description                                                       |
+========================+=============================+===================================================================+
| PowerOnPort            | Port number                 | Request to power on the specified port                            |                   
+------------------------+-----------------------------+-------------------------------------------------------------------+
| PowerOffPort           | Port number                 | Request to power off the specified port                           |                    
+------------------------+-----------------------------+-------------------------------------------------------------------+
| SetPortPowers          | See: :ref:`set-port-powers` | Initialise the FNDH and request the specified port power statuses |
+------------------------+-----------------------------+-------------------------------------------------------------------+                    


Alarm recovery procedure
------------------------
When the FNDH ``PasdStatus`` attribute indicates an ALARM, WARNING or RECOVERY state, the
``WarningFlags`` and ``AlarmFlags`` attributes can be interrogated to find out which
sensors have gone outside their threshold values. These registers need to be manually
cleared by issuing the :py:func:`~ska_low_mccs_pasd.pasd_bus.pasd_bus_device.MccsPasdBus.ResetFndhAlarms` 
and :py:func:`~ska_low_mccs_pasd.pasd_bus.pasd_bus_device.MccsPasdBus.ResetFndhWarnings` commands after
reading.

The PaSD automatically transitions to the RECOVERY state when the relevant
sensor values return to within their alarm thresholds. To return the FNDH to an operational
state after such an event, the :py:func:`~ska_low_mccs_pasd.pasd_bus.pasd_bus_device.MccsPasdBus.InitializeFndh` command must be executed.
