"""Custom pymodbus implementation (temporary)."""
import struct
from array import ArrayType

from pymodbus.register_read_message import ReadHoldingRegistersResponse


class CustomReadHoldingRegistersResponse(ReadHoldingRegistersResponse):
    """Class to override the handling of the Modbus response.

    A bug in the current PaSD firmware means that a ReadHoldingRegisters
    request incorrectly returns the number of registers being read instead
    of the number of bytes. This class temporarily fixes that.
    """

    def decode(self, data: ArrayType) -> None:
        """Decode a register response packet.

        :param data: The request to decode
        """
        byte_count = int(data[0]) * 2  # Multiply this by 2 as a temporary fix
        self.registers = []
        for i in range(1, byte_count + 1, 2):
            self.registers.append(struct.unpack(">H", data[i : i + 2])[0])
