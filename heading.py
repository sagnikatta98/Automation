import asyncio
from bleak import BleakClient, BleakError
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor

BLE_NUS_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"  # BLE UUID
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # Write characteristic UUID
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # Notify characteristic UUID

BLE_GATT_WRITE_LEN = 20  # Max length for GATT write operations

class BLEConfigurator:
    """
    BLE Configurator for accelerometer and gyroscope calibration and heading deviation test.
    """

    def __init__(self, address):
        self.address = address
        self.response_log = []
        self.commands = [
            "crt",                  
            "-f l",                 
            "-l 1 777.bin",       
            "actse 13 100"         
        ]
        self.gyro_calibration_start_time = None
        self.gyro_calibration_end_time = None
        self.popup_active = False
        self.popup_root = None
        self.heading_test_started = False
        self.executor = ThreadPoolExecutor()
        self.loop = None
        self.client = None

    def show_popup(self):
        """
        Display a pop-up to guide the user for heading deviation test.
        """
        self.popup_active = True
        self.popup_root = tk.Tk()
        self.popup_root.title("Heading Deviation Test Check")
        self.popup_root.geometry("400x200")
        label = tk.Label(self.popup_root, text="Keep BLE device at a reference point for 10 secs.\nPress start button below.\n Perform necessary movements. Once done, press the stop button", wraplength=350, justify="center")
        label.pack(pady=20)
        self.start_button = tk.Button(self.popup_root, text="Start", command=self.start_heading)
        self.start_button.pack(pady=10)
        self.stop_button = tk.Button(self.popup_root, text="Stop", command=self.stop_heading, state="disabled")
        self.stop_button.pack(pady=10)
        self.popup_root.mainloop()

    def start_heading(self):
        """
        Send the 'lab start_heading' command when the start button is pressed.
        """
        print("Sending 'lab start_heading' command to BLE device...")
        if self.client:
            asyncio.run_coroutine_threadsafe(self.send_command(self.client, "lab start_heading"), self.loop)
            self.start_button.config(state="disabled")
            self.stop_button.config(state="normal")

    def stop_heading(self):
        """
        Send the 'lab end_heading' command when the stop button is pressed and close the pop-up.
        """
        print("Sending 'lab end_heading' command to BLE device...")
        if self.client:
            asyncio.run_coroutine_threadsafe(self.send_command(self.client, "lab end_heading"), self.loop)
            self.stop_button.config(state="disabled")
            self.close_popup()

    def close_popup(self):
        """
        Close the pop-up after stopping the heading test.
        """
        if self.popup_active and self.popup_root:
            self.popup_root.destroy()
            self.popup_active = False

    async def nus_data_rcv_handler(self, sender, data):
        """
        Handle incoming notifications from the BLE device.
        """
        decoded_data = data.decode('utf-8').strip()
        print(f"Received: {decoded_data}")
        self.response_log.append(decoded_data)
        if "Gyro Accuracy" in decoded_data:
            accuracy = int(decoded_data.split()[-1])
            if accuracy == 1 and self.gyro_calibration_start_time is None:
                self.gyro_calibration_start_time = time.time()
                print("Gyroscope calibration started...")
            elif accuracy == 3 and self.gyro_calibration_start_time is not None:
                self.gyro_calibration_end_time = time.time()
                calibration_time = self.gyro_calibration_end_time - self.gyro_calibration_start_time
                print(f"Gyroscope calibration completed. Time taken: {calibration_time:.2f} seconds.")
                self.gyro_calibration_start_time = None
        if "Accel Accuracy" in decoded_data:
            accuracy = int(decoded_data.split()[-1])
            if accuracy == 3:
                print("Accelerometer calibration completed.")
                if not self.popup_active:
                    self.executor.submit(self.show_popup)

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

    async def continuous_stream(self, client):
        """
        Enter continuous streaming mode and handle incoming data indefinitely.
        """
        print(f"Entering continuous receive mode for {self.address[-5:]}")
        try:
            while True:
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            print("Continuous receive mode interrupted.")

    async def run(self):
        """
        Main function to connect to the BLE device, send commands, and stream data.
        """
        self.loop = asyncio.get_running_loop()
        self.client = BleakClient(self.address)
        try:
            # Connecting to the BLE device
            await self.client.connect()
            if self.client.is_connected:
                print(f"Connected to {self.address[-5:]} ({self.address})")
                await self.client.start_notify(NUS_TX_UUID, self.nus_data_rcv_handler)
                print("Sending configuration commands...")
                await self.configure_device(self.client)
                await self.continuous_stream(self.client)
        except BleakError as e:
            print(f"Error connecting to {self.address}: {e}")
        finally:
            if self.client.is_connected:
                await self.client.stop_notify(NUS_TX_UUID)
                await self.client.disconnect()
                print(f"Disconnected from {self.address[-5:]}.")
            if self.popup_active:
                self.close_popup()


if __name__ == "__main__":
    BLE_MAC_ADDRESS = "E4:6E:C1:3A:91:F8"
    configurator = BLEConfigurator(BLE_MAC_ADDRESS)
    try:
        asyncio.run(configurator.run())
    except asyncio.CancelledError:
        print("Configuration process was interrupted.")
