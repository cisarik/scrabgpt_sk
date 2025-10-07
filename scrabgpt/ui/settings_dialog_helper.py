"""Helper method for settings dialog - language fetch animation."""


def update_lang_status_animation(dialog) -> None:
    """Update language fetch status with animated dots.
    
    Args:
        dialog: SettingsDialog instance
    """
    if not hasattr(dialog, 'lang_fetch_status') or not dialog.lang_fetch_status.isVisible():
        return
    
    # Cycle through 1-3 dots
    dialog._lang_dot_count = (dialog._lang_dot_count + 1) % 3
    dots = "." * (dialog._lang_dot_count + 1)
    
    # Get current status or use default
    status = getattr(dialog, '_lang_current_status', 'Získavam jazyky')
    
    # Update text with animation
    dialog.lang_fetch_status.setText(f"🤖 {status}{dots}")
