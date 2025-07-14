#!/usr/bin/env python3
import websocket
import json
import requests
import re
from datetime import datetime
from threading import Event
from tqdm import tqdm
from typing import Optional, Tuple, Dict, Any

class CBOMkitClient:
    """
        Client for generating CBOM (Component Bill of Materials) via WebSocket communication.
        Handles scan requests, progress reporting, timing, and CBOM retrieval.
        """

    # --- Configuration: Class Constants ---
    DEFAULT_WS_URL = "ws://localhost:8081/v1/scan/cbombench"
    CBOM_API_URL = "http://localhost:8081/api/v1/cbom/last/1"
    PROGRESS_PATTERNS = {
        "Receiving": r"Receiving objects (\d+)\%",
        "Resolving": r"Resolving deltas (\d+)\%",
        "Checking out": r"Checking out files (\d+)\%"
    }
    PROGRESS_POSITIONS = {
        "Receiving": 0,
        "Resolving": 1,
        "Checking out": 2
    }
    PROGRESS_CATEGORIES = ["Receiving", "Resolving", "Checking out"]


    def __init__(self, ws_url=DEFAULT_WS_URL):
        """
            Initialize the CBOMkitClient.

            Args:
                ws_url (str): The WebSocket server URL.
            """
        self.ws_url = ws_url                   # WebSocket server URL
        self.ws = None                         # WebSocketApp instance
        self.start_time = None                 # Timing: scan start
        self.end_time = None                   # Timing: scan end
        self.finished_event = Event()          # Event flag for scan completion
        self.cbom_data = None                  # Stores final CBOM data
        self.success = False                   # Success flag for CBOM generation
        self.old_message = ""                  # Track last LABEL message to avoid repeats
        self.duration = None                   # Duration in seconds
        self.progress_bars= {
            category: None for category in self.PROGRESS_CATEGORIES
        }


    def generate_cbom(self, repo_url, branch="main"):
        """
        Open the WebSocket, send a scan request, wait for CBOM, then close.

        Args:
            repo_url (str): The repository URL to scan.
            branch (str): The branch to scan.

        Returns:
            Tuple[Optional[Dict], Optional[float]]: (CBOM data, duration in seconds) if successful, (None, None) otherwise.
        """
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=lambda ws: self._send_scan_request(ws, repo_url, branch),
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )

        print("Opening WebSocket connection and sending scan request...")
        self.ws.run_forever()  # Blocking: waits until scan is done

        if self.success:
            return self.cbom_data, self.duration
        else:
            return None, None


    def _send_scan_request(self, ws, repo_url, branch):
        """
        Send a scan request to the server for the given repository and branch.

        Args:
            ws (websocket.WebSocketApp): The WebSocket connection.
            repo_url (str): The repository URL.
            branch (str): The branch to scan.
        """
        scan_request = {
            "scanUrl": repo_url,
            "branch": branch
        }
        ws.send(json.dumps(scan_request))
        print("Scan request sent. Waiting for CBOM...")


    def _on_message(self, ws, message):
        """
           Handle incoming WebSocket messages for scan progress and completion.

           Args:
               ws (websocket.WebSocketApp): The WebSocket connection.
               message (str): The received message.
           """
        try:
            msg = json.loads(message)
            text = msg.get("message", "")

            # Only show unique LABEL messages
            if msg.get("type") == "LABEL" and text != self.old_message:
                self.old_message = text
                self._handle_progress_message(text)

            # Start timing on checkout completion
            if text == "Cloning git repository: Checking out files done":
                self.start_time = datetime.now()
                print(f"Timing started at: {self.start_time.strftime('%H:%M:%S')}")

            # On scan finish, try to get the CBOM and close websocket
            elif text == "Finished":
                print("Scan finished. Retrieving CBOM...")
                self._close_progress_bars()
                self.success = self._get_cbom()
                self.finished_event.set()
                ws.close()

        except json.JSONDecodeError as e:
            print(f"Error decoding JSON message: {e}")
            self._close_progress_bars()
            self.finished_event.set()
            ws.close()
        except Exception as e:
            print(f"Error processing message: {e}")
            self._close_progress_bars()
            self.finished_event.set()
            ws.close()


    def _handle_progress_message(self, text):
        """
        Display progress bars for known progress messages, or print message otherwise.

        Args:
            text (str): Progress message text.
        """
        for key, pattern in self.PROGRESS_PATTERNS.items():
            match = re.search(pattern, text)
            if match:
                percent = int(match.group(1))
                self._update_progress_bar(key, percent)
                return

        print(text)  # Print non-progress messages


    def _update_progress_bar(self, category, percent):
        """
        Update or create a tqdm progress bar for a scan stage.

        Args:
            category (str): The progress category.
            percent (int): Completion percentage.
        """
        bar = self.progress_bars.get(category)
        position = self.PROGRESS_POSITIONS.get(category, 0)
        if bar is None:
            bar = tqdm(
                total=100,
                desc=category,
                position=position,
                leave=False,
                ncols=80
            )
            self.progress_bars[category] = bar

        bar.n = percent
        bar.refresh()

        if percent == 100:
            bar.close()
            self.progress_bars[category] = None


    def _close_progress_bars(self):
        """
        Close all progress bars and reset tracking.
        """
        for bar in self.progress_bars.values():
            if bar:
                bar.close()
        self.progress_bars = {category: None for category in self.PROGRESS_CATEGORIES}


    def _on_error(self, ws, error):
        """
        Handle WebSocket errors.
        """
        print(f"WebSocket error: {error}")
        self._close_progress_bars()
        self.finished_event.set()
        ws.close()


    def _on_close(self, ws, close_status_code, close_msg):
        print("WebSocket connection closed.")


    def _measure_time(self):
        """
        Compute and print the duration of CBOM generation in seconds and milliseconds.
        """
        self.end_time = datetime.now()
        duration_ms = (self.end_time - self.start_time).total_seconds() * 1000
        self.duration = duration_ms / 1000
        print(f"Total CBOM generation time: {self.duration:.2f} seconds ({int(duration_ms)} ms)")


    def _get_cbom(self):
        """
        Fetch the CBOM from the API.

        Returns:
            bool: True on success, False on error.
        """
        try:
            response = requests.get(self.CBOM_API_URL)
            response.raise_for_status()
            self.cbom_data = response.json()
            print("CBOM successfully retrieved.")
            if self.start_time:
                self._measure_time()
            return True
        except requests.RequestException as e:
            print(f"HTTP error retrieving CBOM: {e}")
            return False
        except json.JSONDecodeError:
            print("Invalid JSON in CBOM response")
            return False
