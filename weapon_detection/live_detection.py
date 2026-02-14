import cv2
import argparse
from ultralytics import YOLO

def find_camera():
    for i in range(5):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            # Only print if not in headless mode or if we want to log camera info
            cap.release()
            return i
    return None

def run_live_detection(headless=False):
    model_path = './runs/detect/Normal_Compressed/weights/best.pt'
    try:
        yolo_model = YOLO(model_path)
    except Exception as e:
        print(f"Error loading model from {model_path}: {e}")
        return

    camera_index = find_camera()
    if camera_index is None:
        print("Error: No available camera found.")
        return

    video_capture = cv2.VideoCapture(camera_index)

    if not headless:
        print(f"Live detection started using camera {camera_index}. Press 'q' to quit.")

    try:
        while True:
            ret, frame = video_capture.read()
            if not ret:
                if not headless:
                    print("Error: Failed to capture frame.")
                break

            results = yolo_model(frame, stream=True, verbose=False)

            weapon_detected = False
            for result in results:
                cls = result.boxes.cls
                conf = result.boxes.conf
                detections = result.boxes.xyxy

                for pos, detection in enumerate(detections):
                    if conf[pos] >= 0.6:
                        weapon_detected = True
                        
                        if not headless:
                            xmin, ymin, xmax, ymax = detection
                            label_name = result.names[int(cls[pos])]
                            label = f"{label_name} {conf[pos]:.2f}" 
                            color = (0, 0, 255) # Red
                            cv2.rectangle(frame, (int(xmin), int(ymin)), (int(xmax), int(ymax)), color, 2)
                            cv2.putText(frame, label, (int(xmin), int(ymin) - 10), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
            
            if weapon_detected:
                print("weapon", flush=True)

            if not headless:
                cv2.imshow('YOLOv8 Live Weapon Detection', frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        video_capture.release()
        if not headless:
            cv2.destroyAllWindows()
            print("Live detection stopped.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YOLOv8 Live Weapon Detection")
    parser.add_argument("--headless", action="store_true", help="Run without displaying the video feed")
    args = parser.parse_args()
    
    run_live_detection(headless=args.headless)
