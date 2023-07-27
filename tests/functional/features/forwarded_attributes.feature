Feature: Forwarded attributes.

    Scenario: FieldStation forwarded attributes.
        Given A MCCS-for-PaSD which is ready
        And A MccsFndh which is ready
        And A MccsFieldStation which is ready
        When we query their outsideTemperature attributes
        Then they agree on the outsideTemperature