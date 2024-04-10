==================
PaSD Tango Devices
==================
  
The PaSD (Power and Signal Distribution) system is controlled and monitored via
a number of Tango devices, described below.

---------------------
PaSD Bus
---------------------
The PaSD Bus Tango device is responsible for funneling all communications
between MCCS and the PaSD hardware. It ensures that only one request is sent on
the bus at any one time, and handles the prioritization of requests. It also
supports the following commands:

**TODO**

---------------------
FNDH
---------------------
The FNDH Tango device reflects the state of the Field Node Peripheral Controller (FNPC),
including the status of the PDOC ports which are used to power the Smartboxes. The
following attributes are exposed; note that all temperatures are in deg C and all
attributes are read-only with the exception of the alarm and warning thresholds which
are read/write.

+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Tango Attribute name                 | Register address(es)   | Register description                                                     |
+======================================+========================+==========================================================================+
| ModbusRegisterMapRevisionNumber      | 1                      | Modbus FNPC register map revision number, fixed at firmware compile time |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PcbRevisionNumber                    | 2                      | FNCB revision number, fixed at firmware compile time                     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| CpuId                                | 3-4                    | Microcontroller device ID                                                |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| ChipId                               | 5-12                   | Microcontroller unique device ID                                         |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| FirmwareVersion                      | 13                     | Firmware revision number, fixed at compile time                          |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Uptime                               | 14-15                  | Time, in seconds, since FNPC boot                                        |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| SysAddress                           | 16                     | Modbus address                                                           |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Psu48vVoltages                       | 17-18                  | 48Vdc COSEL SMPS 1 output voltage                                        |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Psu48vCurrent                        | 19                     | 48Vdc COSEL SMPS output current                                          |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Psu48vTemperatures                   | 20-21                  | Thermistors mounted on the COSEL SMPS base plate                         |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PanelTemperature                     | 22                     | *NOT IMPLEMENTED IN HARDWARE*                                            |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| FncbTemperature                      | 23                     | Field Node Controller Board temperature                                  | 
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| FncbHumidity                         | 24                     | Field Node Controller Board humidity (%)                                 |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Status                               | 25                     | PaSD System status (see below)                                           |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| LedPattern                           | 26                     | Status of the service and status LEDs                                    |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| CommsGatewayTemperature              | 27                     | Thermistor mounted on the external surface of the Comms Gateway          |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PowerModuleTemperature               | 28                     | Thermistor mounted on the external surface of the Power Module enclosure |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| OutsideTemperature                   | 29                     | Thermistor mounted on the floor of the FNDH EP Enclosure                 |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| InternalAmbientTemperature           | 30                     | Thermistor mounted on the roof of the FNDH EP Enclosure                  |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PortForcings                         | 36-64                  | Port forcing status for each port ("ON", "OFF", or "NONE")               |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PortsDesiredPowerOnline              | 36-64                  | Desired state of each port when FNPC is ONLINE ("OFF, "ON" or "DEFAULT") |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PortsDesiredPowerOffline             | 36-64                  | Desired state of each port when FNPC is OFFLINE ("OFF, "ON" or "DEFAULT")|
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PortsPowerSensed                     | 36-64                  | Power sensed status for each port (True or False)                        |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PortsPowerControl                    | 36-64                  | Power control line ON/OFF status (True if port can be turned on)         |                                                              
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Psu48vVoltage1Thresholds             | 1001-1004              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Psu48vVoltage2Thresholds             | 1005-1008              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Psu48vCurrentThresholds              | 1009-1012              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Psu48vTemperature1Thresholds         | 1013-1016              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Psu48vTemperature2Thresholds         | 1017-1020              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PanelTemperatureThresholds           | 1021-1024              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| FncbTemperatureThresholds            | 1025-1028              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| HumidityThresholds                   | 1029-1032              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| CommsGatewayTemperatureThresholds    | 1033-1036              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PowerModuleTemperatureThresholds     | 1037-1040              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| OutsideTemperatureThresholds         | 1041-1044              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| InternalAmbientTemperatureThresholds | 1045-1048              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| WarningFlags                         | 10129                  | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| AlarmFlags                           | 10131                  | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+

The ``PasdStatus`` attribute should be interpreted as follows:

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


Alarm recovery procedure
------------------------
When the ``PasdStatus`` attribute indicates an alarm, warning or recovery state, the
``WarningFlags`` and ``AlarmFlags`` attributes can be interrogated to find out which
sensors have gone outside their threshold values. These registers need to be manually
cleared by issuing the ``ResetFndhAlarms()`` and ``ResetFndhWarnings()`` commands after
reading.

The PaSD automatically transitions to the RECOVERY state when the relevant
sensor values drop within their alarm thresholds. To return the FNDH to an operational
state after such an event, the ``initialiseFNDH`` command should be executed.

---------------------
Smartboxes
---------------------
The Smartbox Tango devices reflect the state of the individual Smartboxes,
including port power status. The following attributes are exposed; note
all attributes are read-only with the exception of the alarm and warning
thresholds:

**TODO**

---------------------
FNCC
---------------------
The FNCC Tango device reflects the state of the Field Node Communications
Controller. The following read-only attributes are exposed:

+---------------------------------+------------------------+--------------------------------------------------------------------------+
| Tango Attribute name            | Register address(es)   | Register description                                                     |
+=================================+========================+==========================================================================+
| ModbusRegisterMapRevisionNumber | 1                      | Modbus FNCC register map revision number, fixed at firmware compile time |
+---------------------------------+------------------------+--------------------------------------------------------------------------+
| PcbRevisionNumber               | 2                      | FNCB revision number, fixed at firmware compile time                     |
+---------------------------------+------------------------+--------------------------------------------------------------------------+
| CpuId                           | 3-4                    | Microcontroller device ID                                                |
+---------------------------------+------------------------+--------------------------------------------------------------------------+
| ChipId                          | 5-12                   | Microcontroller unique device ID                                         |
+---------------------------------+------------------------+--------------------------------------------------------------------------+
| FirmwareVersion                 | 13                     | Firmware revision number, fixed at compile time                          |
+---------------------------------+------------------------+--------------------------------------------------------------------------+
| Uptime                          | 14-15                  | Time, in seconds, since FNCC boot                                        |
+---------------------------------+------------------------+--------------------------------------------------------------------------+
| SysAddress                      | 16                     | Modbus address                                                           |
+---------------------------------+------------------------+--------------------------------------------------------------------------+
| PasdStatus                      | 17                     | Communications status (see below)                                        |
+---------------------------------+------------------------+--------------------------------------------------------------------------+
| FieldNodeNumber                 | 18                     | Field node unique ID (set using rotary switch)                           |
+---------------------------------+------------------------+--------------------------------------------------------------------------+

The ``PasdStatus`` attribute should be interpreted as follows:

+---------------------------------+-------------------------------------------------+
| *PasdStatus* attribute value    | Meaning                                         |
+=================================+=================================================+
| OK                              | System operating normally, all comms links open |
+---------------------------------+-------------------------------------------------+
| RESET                           | WIZNet converter being reset                    |
+---------------------------------+-------------------------------------------------+
| FRAME_ERROR                     | UART3 framing error                             |
+---------------------------------+-------------------------------------------------+
| MODBUS_STUCK                    | Timer circuit on FNCB tripped                   |
+---------------------------------+-------------------------------------------------+
| FRAME_ERROR_MODBUS_STUCK        | Both framing error and timeout have occurred    |
+---------------------------------+-------------------------------------------------+

After an error has occurred, the status register can be reset by issuing the ``ResetFnccStatus()`` command on the PaSD bus device.