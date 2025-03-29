import asyncio
from bleak import BleakClient, BleakError
from tkinter import Tk, Label

BLE_NUS_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"  # BLE UUID
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"   # Write characteristic UUID
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"   # Notify characteristic UUID

BLE_GATT_WRITE_LEN = 20  # Max length for GATT write operations

class BLEConfigurator:
    """
    BLE Configurator for accelerometer calibration.
    """

    def __init__(self, address):
        self.address = address
        self.response_log = []
        self.commands = [
            "crt",                  
            "-f l",                 
            "-l 1 lal.bin",       
            "actse 52 100"          
        ]
        self.accel_ranges = [2, 4, 8]  # Accelerometer ranges to configure
        self.accel_accuracy = 0
        self.popup = None

    def show_popup(self, message):
        """
        Display a non-blocking popup with the specified message.
        """
        self.popup = Tk()
        self.popup.title("Calibration Instructions")
        Label(self.popup, text=message, padx=20, pady=20).pack()
        self.popup.after(100, self._poll_popup)
        self.popup.update()

    def _poll_popup(self):
        """
        Poll the popup to keep it responsive.
        """
        if self.popup is not None:
            self.popup.update()

    def close_popup(self):
        """
        Close the popup window.
        """
        if self.popup:
            self.popup.destroy()
            self.popup = None

    async def nus_data_rcv_handler(self, sender, data):
        """
        Handle incoming notifications from the BLE device.
        """
        decoded_data = data.decode('utf-8').strip()
        print(f"[Received from {sender}]: {decoded_data}")
        self.response_log.append(decoded_data)
        if "Accel Accuracy" in decoded_data:
            try:
                accuracy = int(decoded_data.split()[-1])
                if accuracy == 3:
                    print("Accelerometer calibration completed.")
                    self.accel_accuracy = accuracy
                    self.close_popup()
            except ValueError:
                pass

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

    async def wait_for_calibration(self):
        """
        Wait until the accelerometer calibration completes (Accel Accuracy reaches 3).
        """
        print("Waiting for accelerometer calibration to complete...")
        self.show_popup("Place each axis of the device flat on the table for 3-4 seconds to complete calibration.")
        while self.accel_accuracy < 3:
            await asyncio.sleep(1)
        print("Calibration completed!")

    async def configure_device(self, client):
        """
        Send configuration commands to the BLE device.
        """
        for command in self.commands:
            await self.send_command(client, command)
        print("Basic configuration commands sent.")
        await self.wait_for_calibration()
        for range_value in self.accel_ranges:
            command = f"aconf {range_value} 2 2"
            await self.send_command(client, command)
            await asyncio.sleep(2)
            expected_response = f"Accel Range set to {range_value}G"
            if any(expected_response in log for log in self.response_log):
                print(f"Response matched: {expected_response}")
            else:
                print(f"Expected response not received: {expected_response}")
                return
        print("Test case 5120_ImuX passed.")

    async def run(self):
        """
        Main function to connect to the BLE device, send commands, and verify responses.
        """
        client = BleakClient(self.address)
        try:
            await client.connect()
            if client.is_connected:
                print(f"Connected to {self.address[-5:]} ({self.address})")
                await client.start_notify(NUS_TX_UUID, self.nus_data_rcv_handler)
                print("Sending configuration commands...")
                await self.configure_device(client)
        except BleakError as e:
            print(f"Error connecting to {self.address}: {e}")
        finally:
            if client.is_connected:
                await client.stop_notify(NUS_TX_UUID)
                await client.disconnect()
                print(f"Disconnected from {self.address[-5:]}.")
            self.close_popup()

if __name__ == "__main__":
    # BLE device MAC address
    BLE_MAC_ADDRESS = "F3:D9:31:80:1B:0B"
    configurator = BLEConfigurator(BLE_MAC_ADDRESS)
    try:
        asyncio.run(configurator.run())
    except asyncio.CancelledError:
        print("Configuration process was interrupted.")
