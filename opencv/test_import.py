import sys
import traceback

print("Python version:", sys.version)

try:
    print("Attempting to import mediapipe...")
    import mediapipe as mp
    print("Basic import successful!")
    print("Mediapipe file path:", mp.__file__)
    
    print("\nAttempting to import solutions directly to catch the underlying error...")
    from mediapipe.python.solutions import pose
    print("Pose import successful!")
except Exception as e:
    print("\n--- ERROR DETECTED ---")
    traceback.print_exc()
    print("----------------------")
