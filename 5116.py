import asyncio
from bleak import BleakClient, BleakError

BLE_NUS_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"  # BLE UUID
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"   # Write characteristic UUID
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"   # Notify characteristic UUID

BLE_GATT_WRITE_LEN = 20  # Max length for GATT write operations


class BLEConfigurator:
    """
    BLE Configurator for accelerometer and gyroscope calibration.
    """

    def __init__(self, address):
        self.address = address
        self.response_log = []
        self.gyro_accuracy = 0
        self.accel_accuracy = 0
        self.commands = [
            "crt",     
            "-f l",                
            "imux iq 1",           
            "-l 1 16.bin",      
            "actse 9 100"         
        ]

    async def nus_data_rcv_handler(self, sender, data):
        """
        Handle incoming notifications from the BLE device
        """
        decoded_data = data.decode('utf-8').strip()
        print(f"[Received from {sender}]: {decoded_data}")
        self.response_log.append(decoded_data)
        if "InvertQuaternion = 1" in decoded_data:
            print("Invert quaternion has been enabled successfully.")
        if "Gyro Accuracy" in decoded_data:
            try:
                self.gyro_accuracy = int(decoded_data.split()[-1])
            except ValueError:
                pass
        if "Accel Accuracy" in decoded_data:
            try:
                self.accel_accuracy = int(decoded_data.split()[-1])
            except ValueError:
                pass
        if self.gyro_accuracy == 1 and self.accel_accuracy == 1:
            print("Gyro calibration started. Keep device stable for 15 seconds")
            print("Accel calibration started. Place each side of the device flat for 3-4 seconds")
        if self.gyro_accuracy == 3 and self.accel_accuracy == 3:
            print("Gyro and Accel calibration completed.")
            await asyncio.sleep(5)
            await self.disconnect_device()

    async def send_command(self, client, command):
        """
        Send a single command to the BLE device.
        """
        print(f"[Sending to {self.address[-5:]}]: {command}")
        if len(command) <= BLE_GATT_WRITE_LEN:
            await client.write_gatt_char(NUS_RX_UUID, (command + '\n').encode())
        else:
            for i in range(0, len(command), BLE_GATT_WRITE_LEN):
                await client.write_gatt_char(NUS_RX_UUID, command[i:i + BLE_GATT_WRITE_LEN].encode())
        await asyncio.sleep(0.5)

    async def configure_device(self, client):
        """
        Send configuration commands to the BLE device.
        """
        for command in self.commands:
            await self.send_command(client, command)

    async def disconnect_device(self):
        """
        Disconnect from the BLE device, ensuring stop_notify is handled correctly.
        """
        if self.client and self.client.is_connected:
            try:
                await self.client.stop_notify(NUS_TX_UUID)
            except Exception as e:
                print(f"Error stopping notifications: {e}")
            try:
                await self.client.disconnect()
                print(f"Disconnected from {self.address[-5:]}.")
            except Exception as e:
                print(f"Error disconnecting: {e}")
            self.client = None

    async def run(self):
        """
        Main function to connect to the BLE device, send commands, and stream data.
        """
        self.client = BleakClient(self.address)
        try:
            await self.client.connect()
            if self.client.is_connected:
                print(f"Connected to {self.address[-5:]} ({self.address})")
                await self.client.start_notify(NUS_TX_UUID, self.nus_data_rcv_handler)
                print("Sending configuration commands...")
                await self.configure_device(self.client)
                while True:
                    await asyncio.sleep(1)
        except BleakError as e:
            print(f"Error connecting to {self.address}: {e}")
        except asyncio.CancelledError:
            print("Configuration process was interrupted.")
        finally:
            if self.client and self.client.is_connected:
                await self.disconnect_device()

if __name__ == "__main__":
    BLE_MAC_ADDRESS = "C4:13:E5:CD:37:72"
    configurator = BLEConfigurator(BLE_MAC_ADDRESS)
    try:
        asyncio.run(configurator.run())
    except asyncio.CancelledError:
        print("Configuration process was interrupted.")
