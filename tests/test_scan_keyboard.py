from bot.keyboards.menu_keyboard import MenuKeyboardFactory


def test_scan_keyboard_disables_slots_without_items():
    keyboard = MenuKeyboardFactory().build_scan_page_keyboard(
        selected_slots=set(),
        page=1,
        total_pages=1,
        has_prev=False,
        has_next=False,
        item_count=1,
    )

    first_row = keyboard.inline_keyboard[0]

    assert first_row[0].callback_data == "scan:select:1"
    assert first_row[1].callback_data == "scan:noop"
    assert first_row[2].callback_data == "scan:noop"
