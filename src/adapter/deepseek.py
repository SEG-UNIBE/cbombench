#!/usr/bin/env python3
"""
DeepSeek CBOM adapter for cbombench
Generates CBOMs using the DeepSeek API.
"""
import os
import time
import json
import threading
from openai import OpenAI
from util import spinner_animation


class DeepSeekClient:
    """
    Client for interacting with the DeepSeek API to generate CBOMs.
    """
    def __init__(self, api_key=None):
        """
        Initializes the DeepSeek Client.

        Args:
            api_key: DeepSeek API key (optional, can also be set as an environment variable)
        """
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError(
                "DeepSeek API key required. Set DEEPSEEK_API_KEY environment variable or pass api_key parameter."
            )

        # Initialize DeepSeek API Client
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com"
        )


    def generate_cbom(self, git_url, branch="main"):
        """
        Generates a CBOM for a Git repository using the DeepSeek API.

        Args:
            git_url: URL of the Git repository
            branch: Branch to scan (default: main)

        Returns:
            tuple: (cbom_data, duration) - CBOM as dict and execution time in seconds
        """
        start_time = time.time()

        # Spinner thread setup
        stop_spinner = threading.Event()
        spinner_thread = threading.Thread(target=spinner_animation, args=(stop_spinner,))
        spinner_thread.start()

        try:
            # System prompt for CBOM generation
            system_prompt = """You are a cryptographic component analyzer. Your task is to analyze a GitHub project and generate a Cryptographic Bill of Materials (CBOM) following the official CycloneDX standard.

Identify all cryptographic components including:
- Cryptographic algorithms (AES, RSA, SHA256, etc.)
- Key management functions
- Hashing functions
- Digital signatures
- Certificates and TLS/SSL usage
- Random number generation
- Encoding/decoding functions

Generate the CBOM in valid CycloneDX JSON format with:
- bomFormat: "CycloneDX"
- specVersion: "1.6"
- Proper component types
- Comprehensive cryptoProperties for each cryptographic component

Please only return the formatted JSON without any additional text or markdown. If there is nothing to report return an empty CBOM."""

            # User prompt with repository and branch
            user_prompt = (
                f"Please generate me a CBOM json for this project, following the official CycloneDX standard on CBOMs.\n"
                f"Project: {git_url}\n"
                f"Branch: {branch}\n"
                f"Please only return the formatted JSON."
            )

            # API call
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                stream=False
            )

            # Process response
            content = response.choices[0].message.content

            # Try to extract JSON (in case response is in markdown blocks)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            # Parse JSON
            try:
                cbom_data = json.loads(content)

                # If CBOM is a list, wrap it in a dict
                if not isinstance(cbom_data, dict):
                    if isinstance(cbom_data, list):
                        cbom_data = {"components": cbom_data}

                # Add missing standard fields if necessary
                if "bomFormat" not in cbom_data:
                    cbom_data["bomFormat"] = "CycloneDX"
                if "specVersion" not in cbom_data:
                    cbom_data["specVersion"] = "1.6"

                duration = time.time() - start_time
                return cbom_data, duration

            except json.JSONDecodeError as e:
                print(f"Error parsing JSON response: {e}")
                print(f"Response: {content[:500]}...")  # Show first 500 characters for debugging
                return None, time.time() - start_time

        except Exception as e:
            print(f"Error during CBOM generation: {e}")
            return None, time.time() - start_time

        finally:
            # Stop the spinner animation
            stop_spinner.set()
            spinner_thread.join()
