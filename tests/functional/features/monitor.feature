@SP-1931
Feature: Monitoring and control of PaSD
    Test that MCCS subsystem can monitor and control a PaSD system.

    Scenario: Monitor PaSD
        Given a PaSD bus Tango device
        And the PaSD bus Tango device is offline
        When I put the PaSD bus Tango device online
        Then the PaSD bus Tango device reports the state of the PaSD system
        And the PaSD bus Tango device reports the health of the PaSD system
