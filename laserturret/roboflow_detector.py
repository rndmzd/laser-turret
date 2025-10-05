import time
from typing import List, Dict, Any, Optional

import numpy as np
import cv2
import logging

try:
    from inference_sdk import InferenceHTTPClient, InferenceConfiguration
    ROBOFLOW_CLIENT_AVAILABLE = True
except Exception:
    ROBOFLOW_CLIENT_AVAILABLE = False


logger = logging.getLogger(__name__)


class RoboflowDetector:
    def __init__(
        self,
        server_url: str,
        model_id: str,
        api_key: Optional[str] = None,
        confidence: float = 0.5,
        class_filter: Optional[List[str]] = None,
    ) -> None:
        if not ROBOFLOW_CLIENT_AVAILABLE:
            raise RuntimeError("inference-sdk not available. Install with: pip install inference-sdk")
        self.client = InferenceHTTPClient(api_url=server_url, api_key=api_key or None)
        self.model_id = model_id
        self.confidence = confidence
        self.class_filter = class_filter or []
        self.inference_times: List[float] = []
        self.frame_count = 0
        self.server_url = server_url
        self.api_key = api_key or None
        # Try to select API v1 and model for future infer() calls without model_id
        try:
            if hasattr(self.client, "select_api_v1"):
                self.client.select_api_v1()
        except Exception:
            pass
        try:
            if hasattr(self.client, "select_model"):
                self.client.select_model(self.model_id)
        except Exception:
            pass
        # Apply initial configuration
        self.apply_config()

    def apply_config(self) -> None:
        try:
            if 'InferenceConfiguration' in globals():
                cfg = InferenceConfiguration(
                    confidence_threshold=float(self.confidence),
                    class_filter=list(self.class_filter) if self.class_filter else None,
                )
                if hasattr(self.client, "configure"):
                    self.client.configure(cfg)
        except Exception as e:
            logger.warning(f"Failed to apply Roboflow configuration: {e}")

    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        start = time.time()
        try:
            # Ensure configuration is applied (cheap op even if repeated)
            self.apply_config()
            # Downscale to ~720p height (preserve aspect ratio) for inference to reduce bandwidth/latency
            orig_h, orig_w = frame.shape[:2]
            infer_frame = frame
            infer_h, infer_w = orig_h, orig_w
            if orig_h > 720:
                scale = 720.0 / float(orig_h)
                infer_w = max(1, int(round(orig_w * scale)))
                infer_h = 720
                infer_frame = cv2.resize(frame, (infer_w, infer_h), interpolation=cv2.INTER_AREA)

            # Prefer calling without kwargs; pass model_id explicitly for compatibility
            result = self.client.infer(infer_frame, model_id=self.model_id)
            preds = result.get("predictions", [])
        except Exception as e:
            logger.error(f"Roboflow inference error: {e}")
            preds = []
        detections: List[Dict[str, Any]] = []
        if isinstance(preds, list):
            # Scale predictions back to original resolution
            w, h = orig_w, orig_h
            sx = float(w) / float(infer_w) if infer_w else 1.0
            sy = float(h) / float(infer_h) if infer_h else 1.0
            for p in preds:
                try:
                    cx = float(p.get("x", 0)) * sx
                    cy = float(p.get("y", 0)) * sy
                    bw = float(p.get("width", 0)) * sx
                    bh = float(p.get("height", 0)) * sy
                    conf = float(p.get("confidence", 0))
                    label = str(p.get("class", "object"))
                    x1 = int(max(0, min(w - 1, cx - bw / 2)))
                    y1 = int(max(0, min(h - 1, cy - bh / 2)))
                    ww = int(max(1, min(w - x1, bw)))
                    hh = int(max(1, min(h - y1, bh)))
                    detections.append({
                        "type": label,
                        "rect": (x1, y1, ww, hh),
                        "confidence": conf,
                    })
                except Exception:
                    continue
        t = time.time() - start
        self.inference_times.append(t)
        if len(self.inference_times) > 30:
            self.inference_times.pop(0)
        self.frame_count += 1
        return detections

    def get_avg_inference_time(self) -> float:
        if not self.inference_times:
            return 0.0
        return (sum(self.inference_times) / len(self.inference_times)) * 1000.0

    def get_fps(self) -> float:
        ms = self.get_avg_inference_time()
        if ms <= 0:
            return 0.0
        return 1000.0 / ms

    def get_stats(self) -> Dict[str, Any]:
        return {
            "server_url": self.server_url,
            "model_id": self.model_id,
            "avg_inference_ms": round(self.get_avg_inference_time(), 2),
            "estimated_fps": round(self.get_fps(), 1),
            "frame_count": self.frame_count,
            "confidence": self.confidence,
            "class_filter": list(self.class_filter),
            "api_key_set": bool(self.api_key),
        }
