import asyncio
import os
import re
import subprocess
import pandas as pd
import plotly.graph_objects as go
from bleak import BleakClient, BleakError

BLE_NUS_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"  # BLE UUID
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # Write characteristic UUID
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # Notify characteristic UUID

BLE_GATT_WRITE_LEN = 20  # Max length for GATT write operations


class BLEFileHandler:
    def __init__(self, address):
        self.address = address
        self.output_dir = "output"
        os.makedirs(self.output_dir, exist_ok=True)

    async def send_command(self, client, command):
        """
        Send a command to the BLE device.
        """
        print(f"[Sending to {self.address[-5:]}]: {command}")
        if len(command) <= BLE_GATT_WRITE_LEN:
            await client.write_gatt_char(NUS_RX_UUID, (command + '\n').encode())
        else:
            for i in range(0, len(command), BLE_GATT_WRITE_LEN):
                await client.write_gatt_char(NUS_RX_UUID, command[i:i + BLE_GATT_WRITE_LEN].encode())
        await asyncio.sleep(0.5)

    async def read_large_binary_file(self, client, file_name, max_size_mb=10):
        """
        Read a large binary file (up to max_size_mb) from the BLE device via notifications.
        """
        max_size_bytes = max_size_mb * 1024 * 1024 
        local_path = os.path.join(self.output_dir, file_name)
        file_data = bytearray()

        def notification_handler(sender, data):
            nonlocal file_data
            decoded_data = data.decode(errors="ignore").strip()
            if not decoded_data.startswith(("rd", "Executing rd")):
                file_data.extend(data)
                print(f"Received {len(data)} bytes of file data. Total: {len(file_data)} bytes.")
            else:
                print(f"Filtered out log message: {decoded_data}")
        print(f"Requesting file {file_name} from BLE device...")
        await client.start_notify(NUS_TX_UUID, notification_handler)
        await client.write_gatt_char(NUS_RX_UUID, f"rd {file_name}\n".encode())
        timeout = 30 
        for _ in range(timeout):
            await asyncio.sleep(1)
            if len(file_data) >= max_size_bytes:
                print(f"File transfer limit of {max_size_mb} MB reached. Stopping...")
                break
        await client.stop_notify(NUS_TX_UUID)
        with open(local_path, "wb") as f:
            f.write(file_data)
        print(f"File saved to {local_path} ({len(file_data)} bytes received)")
        return local_path

    def clean_bin_file(self, bin_file):
        """
        Cleans the .bin file by removing all content before the valid data header.
        """
        print(f"Cleaning binary file: {bin_file}...")
        with open(bin_file, "rb") as f:
            content = f.read()
        decoded_content = content.decode(errors="ignore")
        match = re.search(
            r"1\.0\s+1: Accelerometer \(g\):.*?2: Gyroscope \(dps\):.*?3: IMU Temperature \(C\):", 
            decoded_content,
            re.DOTALL
        )
        if match:
            valid_start = match.start()
            valid_content = content[valid_start:]
            with open(bin_file, "wb") as f:
                f.write(valid_content)
            print("Binary file cleaned successfully.")
        else:
            raise ValueError("Valid header not found in the binary file. File might be corrupted.")

    def convert_bin_to_csv(self, bin_file):
        """
        Convert the binary file to CSV using udf2csv.exe.
        """
        csv_file = os.path.splitext(bin_file)[0] +".bin"+".csv"
        exe_path = os.path.join(os.getcwd(), "udf2csv.exe")
        if not os.path.exists(exe_path):
            raise FileNotFoundError(f"udf2csv.exe not found in {os.getcwd()}")
        print(f"Converting {bin_file} to CSV using {exe_path}...")
        try:
            # Use subprocess to run udf2csv.exe
            result = subprocess.run(
                [exe_path, bin_file],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                print(f"Error during conversion: {result.stderr}")
                raise RuntimeError("Failed to convert .bin to .csv")
            print(f"CSV file created: {csv_file}")
            return csv_file
        except Exception as e:
            print(f"Error during conversion: {e}")
            raise

    def validate_csv(self, csv_file):
        """
        Validate the contents of the CSV file by loading it into a DataFrame and printing the first few rows.
        """
        print(f"Reading {csv_file} into a dataframe...")
        df = pd.read_csv(csv_file)
        df.columns = df.columns.str.strip()
        columns = ["Accel Corrected 0.a","Gyro Corrected 0.a"]
        for column_name in columns:
            if column_name in df.columns:
                df[column_name] = pd.to_numeric(df[column_name], errors="coerce")
                print(f"Generating HTML plot for {column_name}...")
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                x=df.index, 
                y=df[column_name],
                mode='lines',
                name=column_name,
                line=dict(color='blue' if 'Accel' in column_name else 'red')))
                fig.update_layout(
                title=f"2D Plot of {column_name}",
                xaxis_title="Index",
                yaxis_title=column_name,
                template="plotly_white")
                first_reach_3 = df[df[column_name] == 3].index.min()
                if pd.isna(first_reach_3):
                    first_reach_3 = None
                accuracy_drops = False
                if first_reach_3 is not None:
                    accuracy_drops = df.loc[first_reach_3:, column_name].isin([0, 1, 2]).any()
                pass_status = "PASS" if first_reach_3 is not None and not accuracy_drops else "FAIL"
                html_file = f"{column_name.lower().replace(' ', '_')}_plot_2748.html"
                with open(html_file, "w") as f:
                    f.write(fig.to_html(full_html=True, include_plotlyjs='cdn'))
                    f.write(f"<h2>Test Status: {pass_status}</h2>")
                print(f"Plot saved as {html_file} with test result: {pass_status}.")
            else:
                print(f"Column '{column_name}' not found in the CSV file.")
        return df

    async def run(self):
        """
        Main function to connect to the BLE device, read the .bin file, and process it.
        """
        client = BleakClient(self.address)
        file_name = "616.bin"
        try:
            await client.connect()
            if client.is_connected:
                print(f"Connected to {self.address[-5:]} ({self.address})")
                bin_file = await self.read_large_binary_file(client, file_name)
                self.clean_bin_file(bin_file)
                csv_file = self.convert_bin_to_csv(bin_file)
                self.validate_csv(csv_file)
        except BleakError as e:
            print(f"Error connecting to {self.address}: {e}")
        finally:
            if client.is_connected:
                await client.disconnect()
                print(f"Disconnected from {self.address[-5:]}.")

if __name__ == "__main__":
    # BLE device MAC address
    BLE_MAC_ADDRESS = "FE:5F:42:38:8C:C0"

    handler = BLEFileHandler(BLE_MAC_ADDRESS)
    try:
        asyncio.run(handler.run())
    except asyncio.CancelledError:
        print("File transfer process was interrupted.")
