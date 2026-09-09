from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .models import Equipment
from .schemas import HealthOut, HealthMetric

# type_id -> (warning_threshold, critical_threshold) for temp/vibration, plus the
# recommended maintenance interval in days. These are indicative industrial defaults
# (loosely based on common motor/pump condition-monitoring guidance), not a
# certified standard - tune them for real equipment specs when available.
THRESHOLDS = {
    "pump": {"temp": (70, 85), "vib": (2.8, 4.5), "interval_days": 180},
    "motor": {"temp": (80, 100), "vib": (2.8, 4.5), "interval_days": 365},
    "compressor": {"temp": (90, 110), "vib": (2.8, 4.5), "interval_days": 180},
    "generator": {"temp": (90, 110), "vib": (2.8, 4.5), "interval_days": 365},
    "fan": {"temp": (60, 75), "vib": (4.5, 7.1), "interval_days": 180},
    "conveyor": {"temp": (55, 70), "vib": (4.5, 7.1), "interval_days": 180},
    "valve": {"temp": (60, 80), "vib": None, "interval_days": 365},
    "tank": {"temp": None, "vib": None, "interval_days": 730},
    "sensor": {"temp": None, "vib": None, "interval_days": 365},
    "panel": {"temp": (45, 60), "vib": None, "interval_days": 365},
}

DEFAULT_THRESHOLD = {"temp": (75, 95), "vib": (2.8, 4.5), "interval_days": 365}

LABELS_TH = {
    "pump": "ปั๊ม",
    "motor": "มอเตอร์",
    "valve": "วาล์ว",
    "tank": "ถัง",
    "conveyor": "สายพานลำเลียง",
    "sensor": "เซนเซอร์",
    "fan": "พัดลม",
    "compressor": "เครื่องอัดอากาศ",
    "generator": "เครื่องกำเนิดไฟฟ้า",
    "panel": "ตู้ควบคุม",
}


def _band_for(value: float, warn: float, crit: float) -> str:
    if value < warn:
        return "good"
    if value < crit:
        return "warning"
    return "critical"


@dataclass
class HealthScoreResult:
    score: int
    band: str
    summary: str
    metrics: list[HealthMetric] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


def compute_health_score(
    *,
    asset_type: str,
    temperature_c: Optional[float],
    vibration_mm_s: Optional[float],
    status: str,
    last_maintenance_date: Optional[date],
    install_date: Optional[date],
) -> HealthScoreResult:
    """FR-PDM-001's interim implementation contract: a rule-based score/band/
    recommendation engine, expected to be replaced by a real ML model behind
    this same output shape (Phase 15), not rewritten from scratch. Takes
    plain values rather than an ORM object so both the legacy `Equipment`
    table (`compute_health` below) and Phase 12's asset-twin `HealthAssessment`
    (`app.asset.health_engine`) share the one engine instead of each having
    its own copy."""
    cfg = THRESHOLDS.get(asset_type, DEFAULT_THRESHOLD)
    label = LABELS_TH.get(asset_type, asset_type)
    score = 100
    recommendations: list[str] = []
    metrics: list[HealthMetric] = []

    temp_cfg = cfg.get("temp")
    if temp_cfg:
        if temperature_c is not None:
            warn, crit = temp_cfg
            band = _band_for(temperature_c, warn, crit)
            metrics.append(HealthMetric(label="อุณหภูมิ", value=temperature_c, unit="°C", band=band))
            if band == "warning":
                score -= 15
                recommendations.append(
                    f"อุณหภูมิของ{label} ({temperature_c:.1f}°C) สูงกว่าเกณฑ์ปกติ "
                    "ควรตรวจสอบระบบระบายความร้อนและการหล่อลื่น"
                )
            elif band == "critical":
                score -= 35
                recommendations.append(
                    f"อุณหภูมิของ{label} ({temperature_c:.1f}°C) สูงถึงระดับวิกฤต ควรหยุดตรวจสอบโดยด่วน"
                )
        else:
            metrics.append(HealthMetric(label="อุณหภูมิ", value=None, unit="°C", band="unknown"))

    vib_cfg = cfg.get("vib")
    if vib_cfg:
        if vibration_mm_s is not None:
            warn, crit = vib_cfg
            band = _band_for(vibration_mm_s, warn, crit)
            metrics.append(HealthMetric(label="การสั่นสะเทือน", value=vibration_mm_s, unit="mm/s", band=band))
            if band == "warning":
                score -= 15
                recommendations.append(
                    f"ค่าการสั่นสะเทือนของ{label} ({vibration_mm_s:.1f} mm/s) สูงกว่าเกณฑ์ปกติ "
                    "ควรตรวจสอบความสมดุลและตลับลูกปืน (bearing)"
                )
            elif band == "critical":
                score -= 35
                recommendations.append(
                    f"ค่าการสั่นสะเทือนของ{label} ({vibration_mm_s:.1f} mm/s) อยู่ในระดับวิกฤต "
                    "เสี่ยงต่อความเสียหาย ควรหยุดเครื่องตรวจสอบ"
                )
        else:
            metrics.append(HealthMetric(label="การสั่นสะเทือน", value=None, unit="mm/s", band="unknown"))

    interval_days = cfg.get("interval_days") or 365
    ref_date = last_maintenance_date or install_date
    if ref_date:
        days_since = (date.today() - ref_date).days
        ratio = days_since / interval_days
        if ratio <= 1:
            m_band = "good"
        elif ratio <= 1.5:
            m_band = "warning"
            score -= 10
            recommendations.append(
                f"{label}เลยกำหนดบำรุงรักษามาแล้ว {days_since} วัน (รอบปกติทุก {interval_days} วัน) "
                "ควรวางแผนเข้าบำรุงรักษาเร็วๆ นี้"
            )
        else:
            m_band = "critical"
            score -= 25
            recommendations.append(
                f"{label}เลยกำหนดบำรุงรักษามานาน {days_since} วัน ควรเข้าบำรุงรักษาโดยด่วน"
            )
        metrics.append(HealthMetric(label="วันบำรุงรักษาล่าสุด", value=float(days_since), unit="วันที่แล้ว", band=m_band))
    else:
        metrics.append(HealthMetric(label="วันบำรุงรักษาล่าสุด", value=None, unit="วัน", band="unknown"))
        recommendations.append(f"ยังไม่มีข้อมูลวันบำรุงรักษาของ{label} กรุณาบันทึกวันที่บำรุงรักษาล่าสุด")

    if status == "fault":
        score = min(score, 20)
        recommendations.insert(0, f"{label}อยู่ในสถานะ Fault ควรหยุดใช้งานและตรวจสอบทันที")
    elif status == "maintenance":
        recommendations.insert(0, f"{label}กำลังอยู่ระหว่างการบำรุงรักษา")

    score = max(0, min(100, round(score)))

    if score >= 85:
        overall_band = "good"
        summary = f"{label}อยู่ในสภาพดี"
    elif score >= 60:
        overall_band = "warning"
        summary = f"{label}ควรได้รับการตรวจสอบ"
    else:
        overall_band = "critical"
        summary = f"{label}อยู่ในสภาพวิกฤต ควรดำเนินการโดยด่วน"

    if not recommendations:
        recommendations.append(f"{label}อยู่ในสภาพดี ไม่มีคำแนะนำเพิ่มเติมในขณะนี้")

    return HealthScoreResult(
        score=score, band=overall_band, summary=summary, metrics=metrics, recommendations=recommendations
    )


def compute_health(eq: Equipment) -> HealthOut:
    """Legacy call site (`routers/equipment.py`, `routers/dashboard.py`) -
    unchanged behavior/signature, now a thin wrapper over the shared engine."""
    result = compute_health_score(
        asset_type=eq.type,
        temperature_c=eq.temperature_c,
        vibration_mm_s=eq.vibration_mm_s,
        status=eq.status,
        last_maintenance_date=eq.last_maintenance_date,
        install_date=eq.install_date,
    )
    return HealthOut(
        equipment_id=eq.id,
        score=result.score,
        band=result.band,
        summary=result.summary,
        metrics=result.metrics,
        recommendations=result.recommendations,
    )
