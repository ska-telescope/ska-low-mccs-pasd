Feature: Forwarded attributes.

    # This is marked as xfail since forwarded attributes are not supported
    # by Multidevicetestcontext
    @xfail
    Scenario: FieldStation forwarded attributes.
        Given we have a fndh device
        And we have a fieldstation device
        When we query their outsideTemperature attributes
        Then they agree on the outsideTemperature