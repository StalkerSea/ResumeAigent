from settings.localizations.manager import LocalizationManager


@staticmethod
def get_current_time():
    """Get the current time in seconds since the epoch."""
    import time
    return time.time()

@staticmethod
def get_current_date():
    """Get the current date in YYYY-MM-DD format."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d")

@staticmethod
def get_current_time_formatted():
    """Get the current time in HH:MM:SS format."""
    from datetime import datetime
    return datetime.now().strftime("%H:%M:%S")

@staticmethod
def format_execution_time(seconds: float) -> str:
    """Format execution time into hours, minutes, and seconds."""
    localization_manager = LocalizationManager()
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remaining_seconds = seconds % 60

    time_parts = []
    if hours > 0:
        time_parts.append(f"{hours} {localization_manager.get_string('time/hour') if hours == 1 else localization_manager.get_string('time/hours')}")
    if minutes > 0:
        time_parts.append(f"{minutes} {localization_manager.get_string('time/minute') if minutes == 1 else localization_manager.get_string('time/minutes')}")
    if remaining_seconds > 0 or not time_parts:  # Include seconds if no larger units or if there are remaining seconds
        time_parts.append(f"{remaining_seconds:.2f localization_manager.get_string('time/seconds')}")

    return " ".join(time_parts)