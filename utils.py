from __future__ import annotations


def display_result_value(score: dict, value) -> str:
    if value is None or value == "":
        return ""

    score_type = score.get("type")

    if score_type == "time":
        try:
            total_seconds = int(float(value))
        except (TypeError, ValueError):
            return str(value)

        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02d}"

    if score_type == "weight":
        try:
            num = float(value)
            if num.is_integer():
                return str(int(num))
            return str(num)
        except (TypeError, ValueError):
            return str(value)

    if score_type == "reps":
        try:
            num = float(value)
            if num.is_integer():
                return str(int(num))
            return str(num)
        except (TypeError, ValueError):
            return str(value)

    return str(value)