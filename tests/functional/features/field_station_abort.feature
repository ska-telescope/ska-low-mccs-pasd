Feature: FieldStation abort during power on

    @stations(ci-1)
    Scenario: FieldStation ON command is aborted mid-flight
        Given all PaSD devices are ready and initialised
        And the FieldStation is in the OFF state
        When I start turning the FieldStation ON
        And smartboxes 1 to 6 reach STANDBY
        And I abort the FieldStation
        Then the FieldStation does not reach the ON state
        And the On commands were aborted and Abort commands completed OK
