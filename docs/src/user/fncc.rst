===========
FNCC device
===========

The FNCC Tango device reflects the state of the Field Node Communications
Controller. The following read-only attributes are exposed:

+---------------------------------+-------------+--------------------------------------------------------------------------+
| Tango attribute name            | Register    | Register description                                                     |
|                                 |             |                                                                          |
|                                 | address(es) |                                                                          |
+=================================+=============+==========================================================================+
| ModbusRegisterMapRevisionNumber | 1           | Modbus FNCC register map revision number, fixed at firmware compile time |
+---------------------------------+-------------+--------------------------------------------------------------------------+
| PcbRevisionNumber               | 2           | FNCB revision number, fixed at firmware compile time                     |
+---------------------------------+-------------+--------------------------------------------------------------------------+
| CpuId                           | 3-4         | Microcontroller device ID                                                |
+---------------------------------+-------------+--------------------------------------------------------------------------+
| ChipId                          | 5-12        | Microcontroller unique device ID                                         |
+---------------------------------+-------------+--------------------------------------------------------------------------+
| FirmwareVersion                 | 13          | Firmware revision number, fixed at compile time                          |
+---------------------------------+-------------+--------------------------------------------------------------------------+
| Uptime                          | 14-15       | Time, in seconds, since FNCC boot                                        |
+---------------------------------+-------------+--------------------------------------------------------------------------+
| SysAddress                      | 16          | Modbus address                                                           |
+---------------------------------+-------------+--------------------------------------------------------------------------+
| PasdStatus                      | 17          | Communications status (see below)                                        |
+---------------------------------+-------------+--------------------------------------------------------------------------+
| FieldNodeNumber                 | 18          | Field node unique ID (set using rotary switch)                           |
+---------------------------------+-------------+--------------------------------------------------------------------------+

The FNCC ``PasdStatus`` attribute should be interpreted as follows:

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

After an error has occurred, the status register can be reset by issuing the ``ResetFnccStatus()`` command on the MccsPasdBus.