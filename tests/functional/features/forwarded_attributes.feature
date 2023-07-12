Feature: Forwarded attributes.

    # This is marked as xfail since forwarded attributes are not supported
    # by Multidevicetestcontext
    @xfail
    Scenario: FieldStation forwarded attributes.
        Given A MCCS-for-PaSD which is ready
        And A MccsFndh which is ready
        And A MccsFieldStation which is ready
        When we query their outsideTemperature attributes
        Then they agree on the outsideTemperature