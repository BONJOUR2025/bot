def test_payout_handlers_import_and_offer_bonus():
    """Все три точки выбора типа выплаты должны знать про «Премия».

    Раньше список был скопирован в четырёх местах, и новый тип появлялся не
    везде — этот тест ловит расхождение.
    """
    from app.core.constants import PAYOUT_TYPES
    assert "Премия" in PAYOUT_TYPES

    from app.handlers.user import payout as user_payout
    from app.handlers.admin import manual_payout
    from app.vk.handlers import payout as vk_payout

    assert user_payout.PAYOUT_TYPES is PAYOUT_TYPES
    assert manual_payout.PAYOUT_TYPES is PAYOUT_TYPES
    assert vk_payout.PAYOUT_TYPES == set(PAYOUT_TYPES)
