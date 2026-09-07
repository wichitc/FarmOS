from datetime import date

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


def compute_health(eq: Equipment) -> HealthOut:
    cfg = THRESHOLDS.get(eq.type, DEFAULT_THRESHOLD)
    label = LABELS_TH.get(eq.type, eq.type)
    score = 100
    recommendations: list[str] = []
    metrics: list[HealthMetric] = []

    temp_cfg = cfg.get("temp")
    if temp_cfg:
        if eq.temperature_c is not None:
            warn, crit = temp_cfg
            band = _band_for(eq.temperature_c, warn, crit)
            metrics.append(HealthMetric(label="อุณหภูมิ", value=eq.temperature_c, unit="°C", band=band))
            if band == "warning":
                score -= 15
                recommendations.append(
                    f"อุณหภูมิของ{label} ({eq.temperature_c:.1f}°C) สูงกว่าเกณฑ์ปกติ "
                    "ควรตรวจสอบระบบระบายความร้อนและการหล่อลื่น"
                )
            elif band == "critical":
                score -= 35
                recommendations.append(
                    f"อุณหภูมิของ{label} ({eq.temperature_c:.1f}°C) สูงถึงระดับวิกฤต ควรหยุดตรวจสอบโดยด่วน"
                )
        else:
            metrics.append(HealthMetric(label="อุณหภูมิ", value=None, unit="°C", band="unknown"))

    vib_cfg = cfg.get("vib")
    if vib_cfg:
        if eq.vibration_mm_s is not None:
            warn, crit = vib_cfg
            band = _band_for(eq.vibration_mm_s, warn, crit)
            metrics.append(HealthMetric(label="การสั่นสะเทือน", value=eq.vibration_mm_s, unit="mm/s", band=band))
            if band == "warning":
                score -= 15
                recommendations.append(
                    f"ค่าการสั่นสะเทือนของ{label} ({eq.vibration_mm_s:.1f} mm/s) สูงกว่าเกณฑ์ปกติ "
                    "ควรตรวจสอบความสมดุลและตลับลูกปืน (bearing)"
                )
            elif band == "critical":
                score -= 35
                recommendations.append(
                    f"ค่าการสั่นสะเทือนของ{label} ({eq.vibration_mm_s:.1f} mm/s) อยู่ในระดับวิกฤต "
                    "เสี่ยงต่อความเสียหาย ควรหยุดเครื่องตรวจสอบ"
                )
        else:
            metrics.append(HealthMetric(label="การสั่นสะเทือน", value=None, unit="mm/s", band="unknown"))

    interval_days = cfg.get("interval_days") or 365
    ref_date = eq.last_maintenance_date or eq.install_date
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

    if eq.status == "fault":
        score = min(score, 20)
        recommendations.insert(0, f"{label}อยู่ในสถานะ Fault ควรหยุดใช้งานและตรวจสอบทันที")
    elif eq.status == "maintenance":
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

    return HealthOut(
        equipment_id=eq.id,
        score=score,
        band=overall_band,
        summary=summary,
        metrics=metrics,
        recommendations=recommendations,
    )
