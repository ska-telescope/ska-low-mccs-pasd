Feature: fndh tests
    Scenario: Fndh can change port power
        Given A MCCS-for-PaSD which is ready
        And A MccsFndh which is ready
        And they both agree on the power state of port 2
        When I ask the MccsFndh device to change the power state of port 2
        Then MCCS-for-PaSD reports that port 2 has changed
        And they both agree on the power state of port 2