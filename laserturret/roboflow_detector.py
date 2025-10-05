import time
from typing import List, Dict, Any, Optional

import numpy as np
import logging

try:
    from inference_sdk import InferenceHTTPClient
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

    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        start = time.time()
        try:
            params: Dict[str, Any] = {"confidence": float(self.confidence)}
            if self.class_filter:
                params["class_filter"] = list(self.class_filter)
            result = self.client.infer(frame, model_id=self.model_id, **params)
            preds = result.get("predictions", [])
        except Exception as e:
            logger.error(f"Roboflow inference error: {e}")
            preds = []
        detections: List[Dict[str, Any]] = []
        if isinstance(preds, list):
            h, w = frame.shape[:2]
            for p in preds:
                try:
                    cx = float(p.get("x", 0))
                    cy = float(p.get("y", 0))
                    bw = float(p.get("width", 0))
                    bh = float(p.get("height", 0))
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
        }
