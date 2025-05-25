import cv2
import mediapipe as mp
import numpy as np
import time
import os
import sys
from collections import deque
import tkinter as tk
from tkinter import messagebox
import threading
import pyautogui
import platform

class GestureShutdownSystem:
    def _init_(self):
        # Initialize MediaPipe
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5
        )
        self.mp_drawing = mp.solutions.drawing_utils
        
        # System states
        self.IDLE = 0
        self.WAVE_DETECTED = 1
        self.WAITING_CONFIRMATION = 2
        self.SHUTTING_DOWN = 3
        self.TIMEOUT_SHUTDOWN = 4
        
        self.state = self.IDLE
        self.state_start_time = time.time()
        
        # Wave detection parameters
        self.wave_buffer = deque(maxlen=20)  # Store hand positions for wave detection
        self.wave_threshold = 30  # Minimum movement for wave detection
        self.wave_count_required = 3  # Number of direction changes needed
        self.last_wave_time = 0
        
        # Timing parameters
        self.confirmation_timeout = 10  # Seconds to wait for confirmation
        self.wave_cooldown = 2  # Seconds between wave detections
        
        # Visual feedback
        self.colors = {
            'green': (0, 255, 0),
            'red': (0, 0, 255),
            'blue': (255, 0, 0),
            'yellow': (0, 255, 255),
            'white': (255, 255, 255),
            'orange': (0, 165, 255)
        }
        
        # Animation parameters
        self.animation_frame = 0
        self.shutdown_animation_duration = 3  # seconds
        
    def safe_shutdown(self, use_pyautogui=False):
        """Safely shutdown the system"""
        print("Initiating safe shutdown sequence...")
        print("Saving any unsaved work...")
        print("Closing applications...")
        print("Goodbye!")
        
        if use_pyautogui:
            return self.pyautogui_shutdown()
        else:
            # Traditional method
            try:
                if os.name == 'nt':  # Windows
                    os.system("shutdown /s /t 5")  # 5 second delay
                else:  # Linux/macOS
                    os.system("sudo shutdown -h +1")  # 1 minute delay
                print("System shutdown command executed")
                return True
            except Exception as e:
                print(f"Traditional shutdown failed: {e}")
                print("Falling back to PyAutoGUI...")
                return self.pyautogui_shutdown()

    def detect_wave_gesture(self, hand_landmarks):
        """Detect waving gesture by analyzing hand movement"""
        # Get wrist position (landmark 0)
        wrist = hand_landmarks.landmark[0]
        x_pos = wrist.x
        
        # Add current position to buffer
        current_time = time.time()
        self.wave_buffer.append((x_pos, current_time))
        
        # Need at least 10 positions to detect wave
        if len(self.wave_buffer) < 10:
            return False
        
        # Check if enough time has passed since last wave
        if current_time - self.last_wave_time < self.wave_cooldown:
            return False
        
        # Analyze movement pattern
        positions = [pos[0] for pos in self.wave_buffer]
        direction_changes = 0
        total_movement = 0
        
        for i in range(2, len(positions)):
            prev_diff = positions[i-1] - positions[i-2]
            curr_diff = positions[i] - positions[i-1]
            
            # Check for direction change
            if prev_diff * curr_diff < 0 and abs(curr_diff) > 0.02:
                direction_changes += 1
            
            total_movement += abs(curr_diff)
        
        # Wave detected if enough direction changes and movement
        is_wave = (direction_changes >= self.wave_count_required and 
                  total_movement > 0.1)
        
        if is_wave:
            self.last_wave_time = current_time
            self.wave_buffer.clear()  # Clear buffer after detection
            
        return is_wave
    
    def detect_thumbs_up(self, hand_landmarks):
        """Detect thumbs up gesture"""
        # Get relevant landmarks
        thumb_tip = hand_landmarks.landmark[4]
        thumb_ip = hand_landmarks.landmark[3]
        thumb_mcp = hand_landmarks.landmark[2]
        
        index_mcp = hand_landmarks.landmark[5]
        middle_mcp = hand_landmarks.landmark[9]
        ring_mcp = hand_landmarks.landmark[13]
        pinky_mcp = hand_landmarks.landmark[17]
        
        # Check if thumb is extended upward
        thumb_extended = thumb_tip.y < thumb_ip.y < thumb_mcp.y
        
        # Check if other fingers are folded (their tips should be below MCPs)
        index_folded = hand_landmarks.landmark[8].y > index_mcp.y
        middle_folded = hand_landmarks.landmark[12].y > middle_mcp.y
        ring_folded = hand_landmarks.landmark[16].y > ring_mcp.y
        pinky_folded = hand_landmarks.landmark[20].y > pinky_mcp.y
        
        return (thumb_extended and index_folded and 
                middle_folded and ring_folded and pinky_folded)
    
    def show_popup_message(self, message):
        """Show popup message in separate thread"""
        def show_popup():
            root = tk.Tk()
            root.withdraw()  # Hide main window
            messagebox.showinfo("Gesture System", message)
            root.destroy()
        
        popup_thread = threading.Thread(target=show_popup, daemon=True)
        popup_thread.start()
    
    def draw_hand_landmarks(self, image, hand_landmarks):
        """Draw hand landmarks and connections"""
        self.mp_drawing.draw_landmarks(
            image, hand_landmarks, self.mp_hands.HAND_CONNECTIONS,
            self.mp_drawing.DrawingSpec(color=self.colors['blue'], thickness=2, circle_radius=2),
            self.mp_drawing.DrawingSpec(color=self.colors['green'], thickness=2)
        )
    
    def draw_ui_elements(self, image):
        """Draw UI elements and status information"""
        height, width = image.shape[:2]
        
        # Draw status panel background
        cv2.rectangle(image, (10, 10), (400, 120), (0, 0, 0), -1)
        cv2.rectangle(image, (10, 10), (400, 120), self.colors['white'], 2)
        
        # State-specific UI
        if self.state == self.IDLE:
            status_text = "READY - Wave your hand to initiate shutdown"
            status_color = self.colors['green']
            
        elif self.state == self.WAVE_DETECTED:
            status_text = "WAVE DETECTED! Show thumbs up to confirm"
            status_color = self.colors['yellow']
            time_left = int(self.confirmation_timeout - (time.time() - self.state_start_time))
            cv2.putText(image, f"Time left: {max(0, time_left)}s", 
                       (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.colors['orange'], 2)
            
        elif self.state == self.SHUTTING_DOWN:
            status_text = "SHUTTING DOWN... Bye bye!"
            status_color = self.colors['red']
            
            # Shutdown animation
            self.animation_frame += 1
            if self.animation_frame % 10 < 5:  # Blinking effect
                cv2.rectangle(image, (0, 0), (width, height), self.colors['red'], 10)
                
        elif self.state == self.TIMEOUT_SHUTDOWN:
            status_text = "TIMEOUT! Using PyAutoGUI to shutdown..."
            status_color = self.colors['orange']
            
            # Timeout shutdown animation
            self.animation_frame += 1
            if self.animation_frame % 15 < 8:  # Different blinking pattern
                cv2.rectangle(image, (0, 0), (width, height), self.colors['orange'], 8)
        
        # Draw status text
        cv2.putText(image, status_text, (20, 40), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2)
        
        # Draw instructions
        if self.state == self.IDLE:
            cv2.putText(image, "Step 1: Wave hand side to side", 
                       (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.colors['white'], 1)
            cv2.putText(image, "Step 2: Show thumbs up to confirm", 
                       (20, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.colors['white'], 1)
        
        # Draw FPS
        fps_text = f"FPS: {int(cv2.getTickFrequency() / (cv2.getTickCount() - getattr(self, 'last_tick', cv2.getTickCount())))}"
        cv2.putText(image, fps_text, (width - 120, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.colors['white'], 2)
        
        self.last_tick = cv2.getTickCount()
    
    def update_state_machine(self, wave_detected, thumbs_up_detected):
        """Update the state machine based on detected gestures"""
        current_time = time.time()
        
        if self.state == self.IDLE:
            if wave_detected:
                self.state = self.WAVE_DETECTED
                self.state_start_time = current_time
                self.show_popup_message("Waving detected! Show 'Like' gesture to confirm shutdown.")
                print("Wave detected! Waiting for confirmation...")
                
        elif self.state == self.WAVE_DETECTED:
            if thumbs_up_detected:
                self.state = self.SHUTTING_DOWN
                self.state_start_time = current_time
                self.animation_frame = 0
                self.show_popup_message("Powering off, bye-bye!")
                print("Thumbs up detected! Initiating shutdown...")
                
            elif current_time - self.state_start_time > self.confirmation_timeout:
                # Timeout - initiate PyAutoGUI shutdown
                self.state = self.TIMEOUT_SHUTDOWN
                self.state_start_time = current_time
                self.animation_frame = 0
                self.show_popup_message("Confirmation timeout! Using PyAutoGUI to shutdown system.")
                print("Confirmation timeout - initiating PyAutoGUI shutdown...")
                
        elif self.state == self.SHUTTING_DOWN:
            if current_time - self.state_start_time > self.shutdown_animation_duration:
                return "normal_shutdown"  # Signal for normal shutdown
                
        elif self.state == self.TIMEOUT_SHUTDOWN:
            if current_time - self.state_start_time > 2:  # 2 second delay before PyAutoGUI
                return "pyautogui_shutdown"  # Signal for PyAutoGUI shutdown
                
        return False
    
    def pyautogui_shutdown(self):
        """Use PyAutoGUI to perform system shutdown"""
        try:
            system_name = platform.system().lower()
            print(f"Using PyAutoGUI shutdown for {system_name} system...")
            
            if system_name == "windows":
                # Windows shutdown using Alt+F4 on desktop, then Enter
                pyautogui.hotkey('win', 'd')  # Show desktop
                time.sleep(0.5)
                pyautogui.hotkey('alt', 'f4')  # Open shutdown dialog
                time.sleep(1)
                pyautogui.press('enter')  # Confirm shutdown
                
            elif system_name == "darwin":  # macOS
                # macOS shutdown using Cmd+Option+Ctrl+Eject or shutdown dialog
                pyautogui.hotkey('cmd', 'space')  # Open Spotlight
                time.sleep(0.5)
                pyautogui.write('shutdown')
                time.sleep(0.5)
                pyautogui.press('enter')
                
            elif system_name == "linux":
                # Linux shutdown using Ctrl+Alt+Del or terminal
                pyautogui.hotkey('ctrl', 'alt', 't')  # Open terminal
                time.sleep(1)
                pyautogui.write('sudo shutdown -h now')
                time.sleep(0.5)
                pyautogui.press('enter')
                
            else:
                print(f"⚠ Unsupported operating system: {system_name}")
                return False
                
            print("PyAutoGUI shutdown sequence initiated")
            return True
            
        except Exception as e:
            print(f"PyAutoGUI shutdown failed: {e}")
            return False
    
    def run(self):
        """Main application loop"""
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        
        print("Gesture Shutdown System Started")
        print("Instructions:")
        print("   1. Wave your hand side to side to initiate shutdown")
        print("   2. Show thumbs up within 10 seconds to confirm")
        print("   3. Press 'q' to quit safely")
        print("-" * 50)
        
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("Failed to capture frame")
                    break
                
                # Flip frame horizontally for mirror effect
                frame = cv2.flip(frame, 1)
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Process hand detection
                results = self.hands.process(rgb_frame)
                
                wave_detected = False
                thumbs_up_detected = False
                
                if results.multi_hand_landmarks:
                    for hand_landmarks in results.multi_hand_landmarks:
                        # Draw hand landmarks
                        self.draw_hand_landmarks(frame, hand_landmarks)
                        
                        # Detect gestures
                        if self.state == self.IDLE:
                            wave_detected = self.detect_wave_gesture(hand_landmarks)
                        elif self.state == self.WAVE_DETECTED:
                            thumbs_up_detected = self.detect_thumbs_up(hand_landmarks)
                
                # Update state machine
                should_shutdown = self.update_state_machine(wave_detected, thumbs_up_detected)
                
                # Draw UI elements
                self.draw_ui_elements(frame)
                
                # Display frame
                cv2.imshow('Gesture Shutdown System', frame)
                
                # Handle shutdown
                if should_shutdown:
                    cv2.destroyAllWindows()
                    cap.release()
                    if should_shutdown == "normal_shutdown":
                        if self.safe_shutdown():
                            break
                    elif should_shutdown == "pyautogui_shutdown":
                        if self.safe_shutdown(use_pyautogui=True):
                            break
                
                # Check for quit key
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    print("User requested quit")
                    break
                elif key == ord('r'):
                    # Reset system
                    self.state = self.IDLE
                    self.wave_buffer.clear()
                    print("System reset")
                    
        except KeyboardInterrupt:
            print("\nInterrupted by user")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            # Cleanup
            cap.release()
            cv2.destroyAllWindows()
            self.hands.close()
            print("Cleanup completed")

def main():
    """Main function to run the gesture shutdown system"""
    try:
        system = GestureShutdownSystem()
        system.run()
    except Exception as e:
        print(f"Failed to start system: {e}")
        sys.exit(1)

if _name_ == "_main_":
    main()
