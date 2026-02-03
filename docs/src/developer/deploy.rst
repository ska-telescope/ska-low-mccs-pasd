=========
Deploying
=========

As a component of the MCCS subsystem,
ska-low-mccs-pasd would not normally be deployed directly,
except for development purposes.
This guidance is aimed at developers,
and should be read in conjunction with the MCCS subsystem documentation
on deploying the MCCS subsystem as a whole.

``ska-low-mccs-pasd`` uses helmfile to configure helm values files.

---------------------
Deploy using helmfile
---------------------
To deploy ``ska-low-mccs-pasd`` onto a k8s cluster, use the command
``helmfile --environment <environment_name> sync``.
To see what environments are supported,
see the ``environments`` section of ``helmfile.d/helmfile.yaml``.

(Although helmfile supports k8s context switching, this has not yet
been set up. You must manually set your k8s context for the platform
you are targetting, before running the above command.)

To tear down a release that has been deployed by helmfile,
use the command ``helmfile <same arguments> destroy``.
It is important that the arguments to the ``destroy`` command
be the same as those used with the ``sync`` command.
For example, if the release was deployed with ``helmfile --environment gmrt sync``,
then it must be torn down with ``helmfile --environment gmrt destroy``.
If arguments are omitted from the ``helmfile destroy`` command,
the release may not be fully torn down.

--------------------------------
Deploy using the .make submodule
--------------------------------
The ``ska-low-mccs-pasd`` repo includes the ``ska-cicd-makefile`` submodule,
and thus supports the SKA-standard ``make install-chart`` and ``make uninstall-chart`` targets.
When using this approach,
use the ``K8S_HELMFILE_ENV``environment variable to specify the environment.
For example, ``make K8S_HELMFILE_ENV=aavs3 install-chart`` and
``make K8S_HELMFILE_ENV=aavs3 uninstall-chart``.

-----------------
Device properties
-----------------

The following properties are supported for each device type:

MccsPasdBus
~~~~~~~~~~~

- **Host**: IP address of the host
- **Port**: Communications port
- **PollingRate**: Polling period, in seconds
- **DevicePollingRate**: Minimum time between polls of a device, in seconds
- **PollDelayAfterFailure**: Time to wait after a failed poll, in seconds
- **AttributeReadDelay**: Time to wait after writing an attribute before reading it again, in seconds
- **PortStatusReadDelay**: Time to wait after setting port status before reading it again, in seconds
- **Timeout**: Communication timeout, in seconds
- **LowPassFilterCutoff**: Low-pass filter cutoff frequency, in Hz
- **FEMCurrentTripThreshold**: Current trip threshold for all FEMs, in Amps
- **SBInputVoltageThresholds**: List of smartbox input voltage thresholds, in Volts
- **SimulationConfig**: Set to 1 to enable simulation mode
- **AvailableSmartboxes**: List of available smartbox IDs
- **SmartboxIDs**: List of smartbox (Modbus) IDs associated with each FNDH port.
  Should be of length ``no_of_fndh_ports`` (see note below)
- **EnablePyModbusLogging**: Set to True to enable pymodbus logging
- **PyModbusLogDir**: Optional path to a directory to create pymodbus log file in

To only poll smartboxes that are powered on, set the ``SmartboxIDs`` property to the list
of smartbox IDs associated with each FNDH port, and use 0 for any port with no smartbox
attached. For example, to indicate that smartboxes 5, 6 and 7 are attached to FNDH ports
1, 2 and 4 respectively, and that port 3 has no smartbox attached, set the property to:
``[5, 6, 0, 7]``. The ``AvailableSmartboxes`` property is ignored if this is set.

To poll all smartboxes regardless of power state, leave the ``SmartboxIDs`` property unset
and list all smartbox IDs in the ``AvailableSmartboxes`` property.


MccsFNDH
~~~~~~~~

- **PasdFQDN**: Tango FQDN of the associated PaSD bus device
- **PortsWithSmartbox**: List of FNDH ports that have an associated smartbox
- **UseAttributesForHealth**: Set to ``True`` to use attribute quality factor in health evaluation

MccsSmartbox
~~~~~~~~~~~~

- **PasdFQDN**: Tango FQDN of the associated PaSD bus device
- **FieldStationName**: Field station identifier
- **SmartBoxNumber**: Smartbox Modbus ID
- **PortsWithAntennas**: List of ports that have an antenna attached
- **AntennaNames**: List of antenna names attached to ports
- **FndhPort**: FNDH port number this smartbox is connected to
- **UseAttributesForHealth**: Set to ``True`` to use attribute quality factor in health evaluation

MccsFncc
~~~~~~~~

- **PasdFQDN**: Tango FQDN of the associated PaSD bus device
  
MccsFieldStation
~~~~~~~~~~~~~~~~

- **StationName**: Station identifier
- **FndhFQDN**: Tango FQDN of the associated FNDH device
- **SmartboxFQDNs**: List of Tango FQDNs of associated smartbox devices

------------
How it works
------------
The ``environments`` section of ``helmfile.d/helmfile.yaml`` specifies
a sequence of helmfile values files for each environment.
The first file will generally be a specification of the target platform.
This file should only change when the platform itself changes.

For example, the platform specification for AAVS3 specifies an array
with a single station cluster containing a single station.
The specification for that station contains a ``pasd`` key as follows:

.. code-block:: yaml

   pasd:
     fndh:
       gateway:
           host: 10.137.0.129
           port: 502
           timeout: 10.0
       controller:
           modbus_id: 101
       smartboxes:
       "1":
           fndh_port: 1
           modbus_id: 1
       "2":
           fndh_port: 2
           modbus_id: 2
       "3":
           fndh_port: 3
           modbus_id: 3
       "4":
           fndh_port: 4
           modbus_id: 4
       "5":
           fndh_port: 5
           modbus_id: 5
       "6":
           fndh_port: 6
           modbus_id: 6
       "7":
           fndh_port: 7
           modbus_id: 7
       "8":
           fndh_port: 8
           modbus_id: 8
       "9":
           fndh_port: 9
           modbus_id: 9
       "10":
           fndh_port: 10
           modbus_id: 10
       "11":
           fndh_port: 11
           modbus_id: 11
       "12":
           fndh_port: 12
           modbus_id: 12
       "13":
           fndh_port: 13
           modbus_id: 13
       "14":
           fndh_port: 14
           modbus_id: 14
       "15":
           fndh_port: 15
           modbus_id: 15
       "16":
           fndh_port: 16
           modbus_id: 16
       "17":
           fndh_port: 17
           modbus_id: 17
       "18":
           fndh_port: 18
           modbus_id: 18
       "19":
           fndh_port: 19
           modbus_id: 19
       "20":
           fndh_port: 20
           modbus_id: 20
       "21":
           fndh_port: 21
           modbus_id: 21
       "22":
           fndh_port: 22
           modbus_id: 22
       "23":
           fndh_port: 23
           modbus_id: 23
       "24":
           fndh_port: 24
           modbus_id: 24

Subsequent files specify default values and overrides.
There are two keys:

* The ``defaults`` key specifies default values that are
  available to all helmfile templates.
  Currently the only supported default value is ``logging_level_default``.
  For example, to specify that the ``LoggingLevelDefault`` property
  of all Tango devices should be ``DEBUG`` (``5``):

  .. code-block:: yaml

     defaults:
       logging_level_default: 5

* The ``overrides`` key allows to set and override values
  at any place in the platform specification.
  It follows the structure of the platform specification,
  but with values to override or augment that specification.
  For example, to set the ``logging_level_default`` for a single smartbox:

  .. code-block:: yaml

     overrides:
       array:
         station_clusters:
           "p1":
             stations:
               "1":
                 pasd:
                   smartboxes:
                     "10":
                       logging_level_default: 5

  Two special keys are supported:

  * The ``enabled`` key can be applied to any device instance,
    to enable or disable deployment of that device.
    For example, to disable deployment of a smartbox:

    .. code-block:: yaml

     overrides:
       array:
         station_clusters:
           "p1":
             stations:
               "1":
                 pasd:
                   smartboxes:
                     "10":
                       enabled: false

    One can also disable an entire station, and then enable only certain
    devices:

    .. code-block:: yaml

       overrides:
         array:
           station_clusters:
             "p1":
               stations:
                 "1":
                   enabled: false
                   pasd:
                     fndh:
                       enabled: true
                     smartboxes:
                       "1":
                         enabled: true

  * The ``simulated`` key indicates that devices should run against a simulator,
    or should simulate their interactions with hardware.
    It is not possible to simulate the FNDH or individual smartboxes,
    but the PaSD as a whole can be simulated,
    by setting the PaSD communication gateway in simulated mode:

    .. code-block:: yaml

       overrides:
         array:
           station_clusters:
             "p1":
               stations:
                 "1":
                   pasd:
                     fndh:
                       gateway:
                         simulated: true

--------------------------------
Direct deployment of helm charts
--------------------------------
The `ska-low-mccs-pasd` helm chart uses `ska-tango-devices`
to configure and deploy its Tango devices. 
For details on `ska-tango-devices`,
see its `README <hhttps://gitlab.com/ska-telescope/ska-tango-devices/-/blob/main/README.md>`_

Defining devices
~~~~~~~~~~~~~~~~
Devices are defined under `ska-tango-devices.devices`,
as a nested dictionary in which the bottom-level key is the name of a device class,
the next is the name of a device TRL,
and the last is device property names and values.
For example:

.. code-block:: yaml

  ska-tango-devices:
    devices:
      MccsSmartbox:
        low-mccs/smartbox/ci-1-sb01:
          SmartboxNumber: 1
          FndhFQDN: low-mccs/fndh/ci-1
          FndhPort: 1
          PasdbusFQDN: low-mccs/pasdbus/ci-1

It is also possible to specify default values for a device class
in the `deviceDefaults` key:

.. code-block:: yaml

  ska-tango-devices:
    deviceDefaults:
     MccsSmartbox:
       LoggingLevelDefault: 5

Defaults are applied to all devices of the specified class,
but any device-specific value provided under the `devices` key takes precedence.

Defining device servers
~~~~~~~~~~~~~~~~~~~~~~~
Device servers are specified under the `ska-tango-devices.deviceServers` key.
This contains configuration specific to the device server,
and the kubernetes pod in which it runs.

The key hierarchy is:

.. code-block:: yaml

  ska-tango-devices:
    <device_server_type>:
      <device_server_instance>:
        <property_name>: <property_value>

For example:

.. code-block:: yaml

  ska-tango-devices:
    pasd:
      smartbox-ci-1-sb01:
        expose: false
        devices:
          MccsSmartbox:
          - low-mccs/smartbox/ci-1-sb01
      pasdbus-ci-1:
        devices:
          MccsPasdBus:
          - low-mccs/pasdbus/ci-1

The device server type `pasd` is already defined by the `ska-low-mccs-pasd` chart,
and it is the only device server type available;
so all your device instances should sit under this.

Most of the keys that specify a device server instance are optional,
but one is mandatory:
the `devices` key specifies the devices to be run by the device server instance,
and is a list of device TRLs, grouped by device class.
These device TRLs must refer to an entry in the `devices` key.
That is, first we specify the devices that we want under the `device` key,
and then we allocate those devices to device servers under the `deviceServers` key.

It is possible to add device server types, or modify the existing one,
via the `deviceServerTypes` key,
but this should not normally be done.
If it should be necessary to do so,
that indicates a problem with the `ska-low-mccs-pasd` chart
that should be fixed.
