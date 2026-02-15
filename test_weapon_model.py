#!/usr/bin/env python3
"""Test script to analyze the weapon detection model."""

import os
from pathlib import Path
from ultralytics import YOLO

# Check model info
model_path = Path("weapon_detection/runs/detect/Normal_Compressed/weights/best.pt")

if not model_path.exists():
    print(f"❌ Model not found at {model_path}")
    exit(1)

print(f"✓ Model found at {model_path}")
print(f"File size: {model_path.stat().st_size / (1024*1024):.2f} MB\n")

try:
    yolo_model = YOLO(str(model_path))
    print("✓ Model loaded successfully\n")
    
    # Print model info
    print("Model Information:")
    print(f"  Task: {yolo_model.task}")
    print(f"  Model type: {yolo_model.model}")
    
    # Get model class names
    if hasattr(yolo_model, 'model') and yolo_model.model is not None:
        if hasattr(yolo_model.model, 'names'):
            print(f"\n📊 Model Classes ({len(yolo_model.model.names)} total):")
            for cls_id, cls_name in yolo_model.model.names.items():
                print(f"    [{cls_id}] {cls_name}")
        else:
            print("  No class names found in model")
    
    # Test detection on a sample image
    test_image = None
    for img_path in [
        "data/snaps",
        "captures"
    ]:
        if Path(img_path).exists():
            for img_file in Path(img_path).glob("*.jpg"):
                test_image = str(img_file)
                break
    
    if test_image:
        print(f"\n🔍 Running inference on: {test_image}")
        results = yolo_model.predict(
            source=test_image,
            imgsz=640,
            conf=0.25,
            device="cpu",
            verbose=False
        )
        
        if results and len(results) > 0:
            result = results[0]
            print(f"✓ Inference completed")
            print(f"  Detections found: {len(result.boxes)}")
            
            if len(result.boxes) > 0:
                for i, box in enumerate(result.boxes):
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    cls_name = result.names.get(cls_id, "unknown")
                    print(f"    [{i+1}] {cls_name}: {conf:.3f}")
    else:
        print("\n⚠️  No test image found in data/snaps or captures")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
