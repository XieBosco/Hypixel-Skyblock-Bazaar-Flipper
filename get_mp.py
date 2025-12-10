"""
This script gets the x y coordinates of the mouse inside a minecraft window
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), 'system', 'lib'))

import minescript
import pyautogui as py
import keyboard

def on_key_event(event):
    if event.name == "c" and event.event_type == keyboard.KEY_DOWN:
        x, y = py.position()

        print(f"x: {x}, y: {y}")


# Hook all events
keyboard.on_press(on_key_event)

print("Listening for the button 'c' on press. Press 'x' to stop.")

# Keep the script running until 'x' is pressed
keyboard.wait('x')

# Unhook all events when done
keyboard.unhook_all()

print("Mouse position recorder has ended.")

